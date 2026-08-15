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

for dag_id, dag in db.dags.items():
    schedule = getattr(dag, "schedule", None)
    if schedule is None:
        schedule = getattr(dag, "schedule_interval", None)
    out["dags"][dag_id] = {
        "display_name": getattr(dag, "dag_display_name", None),
        "description": dag.description,
        "has_doc_md": bool(dag.doc_md),
        "schedule": str(schedule),
        "catchup": bool(dag.catchup),
        "max_active_runs": dag.max_active_runs,
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
            }
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
