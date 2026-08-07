"""Dump Airflow DAG structure + maintenance DAG config as JSON.

Run inside the airflow container (python -). Purely diagnostic: no side effects.
"""

import importlib
import json
import sys

sys.path.insert(0, "/opt/airflow/dags")

from airflow.models import DagBag

db = DagBag(dag_folder="/opt/airflow/dags", include_examples=False)

out = {
    "import_errors": {k: str(v) for k, v in db.import_errors.items()},
    "dags": {},
}

for dag_id, dag in db.dags.items():
    out["dags"][dag_id] = {
        "schedule": str(dag.schedule),
        "catchup": bool(dag.catchup),
        "max_active_runs": dag.max_active_runs,
        "tasks": {
            tid: sorted(t.get_direct_relative_ids(upstream=True))
            for tid, t in dag.task_dict.items()
        },
        "default_retries": dag.default_args.get("retries"),
        "execution_timeout": str(dag.default_args.get("execution_timeout")),
    }

maint = importlib.import_module("lakehouse_maintenance")
out["maintenance_config"] = {
    "MAINTENANCE_TABLES": [list(t) for t in maint.MAINTENANCE_TABLES],
    "RETENTION": maint.RETENTION,
    "RETAIN_LAST": maint.RETAIN_LAST,
    "FILE_SIZE_THRESHOLD": maint.FILE_SIZE_THRESHOLD,
}

print(json.dumps(out, sort_keys=True))
