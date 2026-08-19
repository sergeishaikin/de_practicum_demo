"""The capture must work the first time it fires, on a runner, unattended.

A diagnostic that raises while describing a failure destroys the only copy of
the evidence it existed to keep. These check both observed corruption shapes
against a filesystem double, with no stack and no object store.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import progress_read_diagnostics as prd

GOOD = json.dumps({"completed": {"001-seed": {"sequence": 1}}}).encode("utf-8")
# The two shapes seen in CI: a complete document followed by more bytes, and a
# byte that is not valid UTF-8 at all.
TRAILING_GARBAGE = GOOD + b"/usr/local/sbin:/usr/bin:/sbin"
UNDECODABLE = GOOD + b"\xc0/usr/local/sbin"


class _File:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def size(self) -> int:
        return len(self._payload)

    def read(self) -> bytes:
        return self._payload


class _Info:
    type = "FileType.File"
    mtime = "2026-08-19T00:00:00Z"

    def __init__(self, size: int) -> None:
        self.size = size


class _FS:
    """The primary read is corrupt; every comparison read is clean.

    That is the shape the CI evidence showed: an intact object on the server and
    a single read that returned it plus a tail of process memory. The capture has
    to be able to demonstrate exactly that, so the double reproduces it - the
    first sequential read (the caller's) is corrupt, the second sequential read
    and the random-access read (both taken by the capture) are clean.
    """

    def __init__(self, good: bytes, corrupt: bytes) -> None:
        self.good = good
        self.corrupt = corrupt
        self.streams = 0

    def get_file_info(self, path: str) -> _Info:
        return _Info(len(self.good))

    def open_input_file(self, path: str) -> _File:
        return _File(self.good)

    def open_input_stream(self, path: str) -> _File:
        self.streams += 1
        return _File(self.corrupt if self.streams == 1 else self.good)


@pytest.fixture()
def diagnostics_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(prd, "DIAGNOSTIC_DIR", tmp_path)
    return tmp_path


def _capture(fs) -> dict:
    with pytest.raises(prd.ProgressReadCorruption) as excinfo:
        prd.read_progress_json(fs, "bucket/m4/run/progress.json")
    directory = Path(str(excinfo.value).rsplit("Evidence: ", 1)[1])
    return {
        "dir": directory,
        "report": json.loads((directory / "report.json").read_text(encoding="utf-8")),
    }


def test_a_clean_read_is_returned_untouched(diagnostics_dir):
    fs = _FS(GOOD, GOOD)
    assert prd.read_progress_json(fs, "bucket/m4/run/progress.json") == {
        "completed": {"001-seed": {"sequence": 1}}
    }
    assert list(diagnostics_dir.iterdir()) == []


@pytest.mark.parametrize("corrupt", [TRAILING_GARBAGE, UNDECODABLE])
def test_the_raw_bytes_survive_the_capture(diagnostics_dir, corrupt):
    """The undecoded bytes are the evidence, so they must be on disk verbatim."""

    captured = _capture(_FS(GOOD, corrupt))
    assert (captured["dir"] / "first-read.bin").read_bytes() == corrupt


@pytest.mark.parametrize("corrupt", [TRAILING_GARBAGE, UNDECODABLE])
def test_the_boundary_between_document_and_garbage_is_located(diagnostics_dir, corrupt):
    report = _capture(_FS(GOOD, corrupt))["report"]
    after = report["bytes_after_valid_prefix"]
    assert after["length"] > 0
    assert bytes.fromhex(after["hex"]) == corrupt[after["offset"] :][: after["length"]]
    assert report["first_read"]["length"] == len(corrupt)
    assert report["size_reported_at_open"] == len(corrupt)
    assert report["file_info_before_read"]["size"] == len(GOOD)


@pytest.mark.parametrize("corrupt", [TRAILING_GARBAGE, UNDECODABLE])
def test_the_two_discriminating_comparisons_are_recorded(diagnostics_dir, corrupt):
    """Second read and sequential read are what separate the hypotheses.

    Both parsing while the first read did not is the signature of a read-side
    fault over an intact object; the capture has to state that rather than leave
    it to be inferred.
    """

    report = _capture(_FS(GOOD, corrupt))["report"]
    assert report["second_read"]["parses"] is True
    assert report["second_read"]["identical_to_first"] is False
    assert report["sequential_read"]["parses"] is True
    assert report["sequential_read"]["identical_to_first"] is False


def test_a_corrupt_stored_object_is_distinguishable_from_a_bad_read(diagnostics_dir):
    """Hypothesis A: every read agrees, and all of them are corrupt."""

    fs = _FS(TRAILING_GARBAGE, TRAILING_GARBAGE)
    report = _capture(fs)["report"]
    assert report["second_read"]["parses"] is False
    assert report["second_read"]["identical_to_first"] is True
    assert report["sequential_read"]["parses"] is False


def test_context_is_captured_only_on_failure(diagnostics_dir):
    calls: list[int] = []

    def context() -> dict:
        calls.append(1)
        return {"cycle": "abc"}

    prd.read_progress_json(_FS(GOOD, GOOD), "bucket/p.json", context=context)
    assert calls == []

    with pytest.raises(prd.ProgressReadCorruption):
        prd.read_progress_json(_FS(GOOD, UNDECODABLE), "bucket/p.json", context=context)
    assert calls == [1]
