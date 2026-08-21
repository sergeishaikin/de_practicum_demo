"""Dump Airflow DAG structure + maintenance DAG config as JSON.

Run inside the airflow container (python -). Purely diagnostic: no side effects.
"""

import importlib
import json
import logging
import sys

from airflow.models import DagBag

logging.disable(logging.CRITICAL)

sys.path.insert(0, "/opt/airflow/dags")

db = DagBag(dag_folder="/opt/airflow/dags")

out = {
    "import_errors": {k: str(v) for k, v in db.import_errors.items()},
    "dags": {},
}


def asset_uris(expression):
    if expression is None:
        return []
    uri = getattr(expression, "uri", None)
    if uri is not None:
        return [uri]
    return [
        uri
        for nested in getattr(expression, "objects", ())
        for uri in asset_uris(nested)
    ]


def lineage_uris(entries):
    """Sorted URIs of a task's inlets/outlets, so Asset identity is observable.

    Counts alone cannot answer which Assets a rendered dbt task group produces,
    which is the whole question when Cosmos emits datasets of its own.
    """

    return sorted(
        getattr(entry, "uri", None) or str(entry) for entry in (entries or [])
    )


for dag_id, dag in db.dags.items():
    schedule = getattr(dag, "schedule", None)
    if schedule is None:
        schedule = getattr(dag, "schedule_interval", None)
    asset_expression = getattr(dag, "asset_expression", None) or getattr(
        dag.timetable, "asset_condition", None
    )
    scheduled_asset_uris = sorted(asset_uris(asset_expression))
    out["dags"][dag_id] = {
        "display_name": getattr(dag, "dag_display_name", None),
        "description": dag.description,
        "has_doc_md": bool(dag.doc_md),
        "schedule": str(schedule),
        "catchup": bool(dag.catchup),
        "max_active_runs": dag.max_active_runs,
        "dagrun_timeout": str(dag.dagrun_timeout),
        "tags": sorted(dag.tags),
        "owner": dag.default_args.get("owner"),
        "scheduled_asset_uris": scheduled_asset_uris,
        "tasks": {
            tid: sorted(t.get_direct_relative_ids(upstream=True))
            for tid, t in dag.task_dict.items()
        },
        "mapped_tasks": sorted(
            tid
            for tid, task_instance in dag.task_dict.items()
            if type(task_instance).__name__ == "DecoratedMappedOperator"
        ),
        "map_index_templates": {
            tid: task_instance.map_index_template
            for tid, task_instance in dag.task_dict.items()
            if task_instance.map_index_template
        },
        "task_max_active_tis_per_dagrun": {
            tid: task_instance.max_active_tis_per_dagrun
            for tid, task_instance in dag.task_dict.items()
        },
        "task_assets": {
            tid: {
                "inlets": len(task_instance.inlets or []),
                "outlets": len(task_instance.outlets or []),
                "inlet_uris": lineage_uris(task_instance.inlets),
                "outlet_uris": lineage_uris(task_instance.outlets),
            }
            for tid, task_instance in dag.task_dict.items()
        },
        "task_groups": {
            tid: task_instance.task_group.group_id
            for tid, task_instance in dag.task_dict.items()
        },
        "default_retries": dag.default_args.get("retries"),
        "execution_timeout": str(dag.default_args.get("execution_timeout")),
    }

maint = importlib.import_module("lakehouse_maintenance")
out["maintenance_config"] = {
    "MAINTENANCE_TABLES": [list(t) for t in maint.MAINTENANCE_TABLES],
    "RETENTION": maint.RETENTION,
    "RECOVERY_HORIZON": maint.RECOVERY_HORIZON,
    "RECOVERY_SAFETY_MARGIN": maint.RECOVERY_SAFETY_MARGIN,
    "RETENTION_CONTRACT": {
        "retention_seconds": maint.RETENTION_CONTRACT.retention_seconds,
        "recovery_horizon_seconds": maint.RETENTION_CONTRACT.recovery_horizon_seconds,
        "safety_margin_seconds": maint.RETENTION_CONTRACT.safety_margin_seconds,
    },
    "RETAIN_LAST": maint.RETAIN_LAST,
    "FILE_SIZE_THRESHOLD": maint.FILE_SIZE_THRESHOLD,
}

print(json.dumps(out, sort_keys=True))
