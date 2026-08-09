#!/usr/bin/env python3
"""Generate a current Codex model catalog with Luna enabled for V2 dispatch.

The official ``models_cache.json`` is always treated as read-only input.  Only
the generated catalog is written, and an existing generated catalog is backed
up before it changes.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _default_codex_home() -> Path:
    return Path.home() / ".codex"


def _backup_path(path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(f"{path.name}.bak-{stamp}")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak-{stamp}-{suffix}")
        suffix += 1
    return candidate


def _render(catalog: Any) -> str:
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"


def _read_stable_source(source: Path) -> tuple[bytes, Any]:
    """Read an atomically-updated source catalog without accepting a torn read."""

    for _ in range(5):
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
        if (
            before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
        ):
            return raw, json.loads(raw.decode("utf-8"))
    raise RuntimeError("source catalog changed continuously; refusing a stale patch")


def patch_catalog(source: Path, destination: Path) -> dict[str, Any]:
    source_bytes, catalog = _read_stable_source(source)
    models = catalog.get("models") if isinstance(catalog, dict) else None
    if not isinstance(models, list):
        raise ValueError("catalog must contain a top-level 'models' list")

    luna_models = [
        model
        for model in models
        if isinstance(model, dict) and model.get("slug") == "gpt-5.6-luna"
    ]
    if len(luna_models) != 1:
        raise ValueError(
            "expected exactly one model with slug 'gpt-5.6-luna', "
            f"found {len(luna_models)}"
        )

    luna = luna_models[0]
    previous_version = luna.get("multi_agent_version")
    luna["multi_agent_version"] = "v2"
    rendered = _render(catalog)

    # Codex may refresh models_cache.json while this process is running.  Do
    # not write a snapshot that was derived from an older source version.
    if source.read_bytes() != source_bytes:
        raise RuntimeError("source catalog changed during patch; retrying")

    old_text: str | None = None
    backup: str | None = None
    changed = True
    if destination.exists():
        old_text = destination.read_text(encoding="utf-8")
        changed = old_text != rendered

    if changed:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            backup_path = _backup_path(destination)
            backup_path.write_bytes(destination.read_bytes())
            backup = str(backup_path)
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(rendered, encoding="utf-8", newline="\n")
        os.replace(temporary, destination)

    diff = ""
    if old_text is not None and changed:
        diff = "".join(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                rendered.splitlines(keepends=True),
                fromfile=str(destination),
                tofile=str(destination),
            )
        )

    return {
        "source": str(source),
        "destination": str(destination),
        "previous_luna_version": previous_version,
        "luna_version": "v2",
        "changed": changed,
        "backup": backup,
        "diff": diff,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()

    codex_home = _default_codex_home()
    source = (args.source or codex_home / "models_cache.json").expanduser()
    destination = (
        args.destination or codex_home / "model-catalogs" / "desktop-multi-agent.json"
    ).expanduser()
    for attempt in range(1, 6):
        try:
            result = patch_catalog(source, destination)
            result["attempt"] = attempt
            # Keep CLI output safe on Windows consoles using cp1252.
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        except RuntimeError as exc:
            if attempt == 5:
                raise
            print(f"retry {attempt}/5: {exc}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
