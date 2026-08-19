"""Capture evidence when a progress object reads back as non-JSON.

Two M5 gate tests have failed with garbage immediately after a valid JSON
prefix - once `Extra data` at char 237, once an undecodable `0xc0` at byte 240 -
on an object that only ever holds a small JSON document. The cause is not
established, and the shapes that would explain it are distinguishable only by
the bytes themselves.

This module does not make a failing read succeed. It captures what the read
returned and re-raises. Nothing here retries, sleeps, backs off, truncates to
the first `}`, or relaxes what the caller expects: a corrupted read stays a
failure, it just stops being an unexplained one.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

DIAGNOSTIC_DIR = Path(
    os.getenv("MEDALLION_READ_DIAGNOSTICS_DIR", "artifacts/read-corruption")
)
_MAX_TAIL_BYTES = 512


class ProgressReadCorruption(Exception):
    """Raised in place of the decode error, carrying the captured evidence path."""


def _longest_valid_json_prefix(raw: bytes) -> dict[str, Any]:
    """How much of the payload is a complete JSON document, and what follows."""

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        # The undecodable byte is itself the boundary we want to report.
        return {
            "decodable_as_utf8": False,
            "first_bad_byte_offset": exc.start,
            "first_bad_byte": f"0x{raw[exc.start]:02x}",
            "valid_json_prefix_chars": None,
        }
    decoder = json.JSONDecoder()
    try:
        _, end = decoder.raw_decode(text)
    except json.JSONDecodeError:
        return {
            "decodable_as_utf8": True,
            "valid_json_prefix_chars": None,
            "note": "no complete JSON document at offset 0",
        }
    return {
        "decodable_as_utf8": True,
        "valid_json_prefix_chars": end,
        "trailing_chars": len(text) - end,
    }


def _describe(raw: bytes) -> dict[str, Any]:
    return {
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "boundary": _longest_valid_json_prefix(raw),
    }


def _file_info(filesystem, object_path: str) -> dict[str, Any]:
    try:
        info = filesystem.get_file_info(object_path)
    except Exception as exc:  # noqa: BLE001 - diagnostics must not mask the failure
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "type": str(info.type),
        "size": info.size,
        "mtime": str(getattr(info, "mtime", None)),
    }


def read_progress_json(
    filesystem,
    object_path: str,
    *,
    context: Callable[[], dict[str, Any]] | None = None,
) -> dict:
    """Read and parse a progress object, capturing the bytes if it will not parse.

    `context` supplies writer- or cycle-side state to record alongside the bytes;
    it is called only on failure, so a healthy poll costs nothing.
    """

    info_before = _file_info(filesystem, object_path)
    # Sequential, matching the medallion's own `_read_json`. A random-access read
    # is sized from a HEAD taken at open and returns that many bytes even when
    # the body since became shorter; the capture below exists because that is
    # what produced the corruption this module was written for.
    with filesystem.open_input_stream(object_path) as source:
        raw = source.read()
        size_at_open = len(raw)

    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report = _capture(
            filesystem,
            object_path,
            raw=raw,
            size_at_open=size_at_open,
            info_before=info_before,
            error=exc,
            context=context,
        )
        raise ProgressReadCorruption(
            f"{object_path} did not read back as JSON: {type(exc).__name__}: {exc}. "
            f"Evidence: {report}"
        ) from exc


def _capture(
    filesystem,
    object_path: str,
    *,
    raw: bytes,
    size_at_open: int,
    info_before: dict[str, Any],
    error: Exception,
    context: Callable[[], dict[str, Any]] | None,
) -> str:
    stamp = f"{time.time_ns()}-{os.getpid()}"
    directory = DIAGNOSTIC_DIR / stamp
    directory.mkdir(parents=True, exist_ok=True)

    # The undecoded bytes are the evidence. Written first, before anything else
    # can fail, and never decoded on the way to disk.
    (directory / "first-read.bin").write_bytes(raw)

    # A second, independent read of the same object. If the object on the server
    # is intact, this one parses and the fault is in the first read; if it is
    # corrupt, this one fails the same way.
    second: dict[str, Any] = {}
    try:
        info_after = _file_info(filesystem, object_path)
        with filesystem.open_input_file(object_path) as source:
            second_size_at_open = source.size()
            second_raw = source.read()
        (directory / "second-read.bin").write_bytes(second_raw)
        second = {
            "file_info": info_after,
            "size_at_open": second_size_at_open,
            **_describe(second_raw),
            "identical_to_first": second_raw == raw,
        }
        try:
            json.loads(second_raw.decode("utf-8"))
            second["parses"] = True
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            second["parses"] = False
            second["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        second = {"error": f"{type(exc).__name__}: {exc}"}

    # A different read path over the same bytes. `open_input_file` is random
    # access and sizes itself from a HEAD; `open_input_stream` is sequential.
    # If one returns the object and the other returns the object plus a tail,
    # the fault is in the read, not in the stored object.
    sequential: dict[str, Any] = {}
    try:
        with filesystem.open_input_stream(object_path) as source:
            sequential_raw = source.read()
        (directory / "sequential-read.bin").write_bytes(sequential_raw)
        sequential = {
            **_describe(sequential_raw),
            "identical_to_first": sequential_raw == raw,
        }
        try:
            json.loads(sequential_raw.decode("utf-8"))
            sequential["parses"] = True
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            sequential["parses"] = False
            sequential["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        sequential = {"error": f"{type(exc).__name__}: {exc}"}

    boundary = _longest_valid_json_prefix(raw)
    cut = boundary.get("valid_json_prefix_chars")
    if cut is None:
        cut = boundary.get("first_bad_byte_offset") or 0
    tail = raw[cut : cut + _MAX_TAIL_BYTES]

    report = {
        "object_path": object_path,
        "error": f"{type(error).__name__}: {error}",
        "file_info_before_read": info_before,
        "size_reported_at_open": size_at_open,
        "first_read": _describe(raw),
        "bytes_after_valid_prefix": {
            "offset": cut,
            "length": len(tail),
            "hex": tail.hex(),
            "repr": repr(tail[:200]),
        },
        "second_read": second,
        "sequential_read": sequential,
        "context": (context() if context is not None else None),
        "captured_at": stamp,
    }
    (directory / "report.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return str(directory)
