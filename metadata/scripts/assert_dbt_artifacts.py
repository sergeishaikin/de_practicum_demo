"""Fail-fast compatibility guard for the repository's real dbt artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--expected-model", action="append", required=True)
    parser.add_argument("--expected-source", action="append", default=[])
    args = parser.parse_args()
    target = args.target_dir
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((target / "catalog.json").read_text(encoding="utf-8"))
    run_results = json.loads((target / "run_results.json").read_text(encoding="utf-8"))
    version = manifest.get("metadata", {}).get("dbt_version")
    if version != "1.12.2":
        raise SystemExit(f"expected repository dbt 1.12.2 artifacts, got {version!r}")

    model_nodes = {
        node["name"]: node
        for node in manifest.get("nodes", {}).values()
        if node.get("resource_type") == "model"
    }
    catalog_nodes = catalog.get("nodes", {})
    for name in args.expected_model:
        node = next((value for key, value in model_nodes.items() if key == name), None)
        if not node or not node.get("compiled_code"):
            raise SystemExit(f"model {name} has no compiled_code in generated manifest")
        unique_id = node["unique_id"]
        catalog_node = catalog_nodes.get(unique_id)
        if not catalog_node or not catalog_node.get("columns"):
            raise SystemExit(f"model {name} has no catalog columns")
        if not node.get("depends_on", {}).get("nodes"):
            raise SystemExit(f"model {name} has no manifest lineage dependencies")

    source_names = {
        node.get("name")
        for node in manifest.get("sources", {}).values()
        if node.get("resource_type") == "source"
    }
    for name in args.expected_source:
        if name not in source_names:
            raise SystemExit(f"source {name} is missing from generated manifest")

    if not run_results.get("results"):
        raise SystemExit("generated run_results.json has no result records")
    if not any(
        result.get("unique_id", "").startswith("test.")
        for result in run_results["results"]
    ):
        raise SystemExit("generated run_results.json has no dbt test result")
    print(
        f"dbt artifact guard passed: version={version} models={len(model_nodes)} "
        f"results={len(run_results['results'])}"
    )


if __name__ == "__main__":
    main()
