"""The live Airflow OpenLineage provider smoke NG-0.2 requires.

A passing DagBag proves the image builds and DAGs import with the provider
installed. It does not prove the provider is *active*: a provider that fails to
load, or whose transport is misconfigured, leaves Airflow running perfectly and
emitting nothing. This asks the running scheduler instead of the lock file.

Deliberately not asserted here: that an Airflow task emitted an event. DAGs are
paused at creation, so no task runs in CI, and triggering one would mutate stack
state that the surrounding tests depend on. What that leaves unproven is
recorded in the change's evidence rather than papered over with a weaker claim.
"""

from __future__ import annotations

import json
import subprocess

import pytest

CONTAINER = "de-demo-airflow"
PROVIDER = "apache-airflow-providers-openlineage"
EXPECTED_LOG_PATH = "/opt/airflow/lineage/events.jsonl"


def _airflow_is_running() -> bool:
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name=^{CONTAINER}$",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and CONTAINER in result.stdout


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _airflow_is_running(),
        reason=(
            f"{CONTAINER} is not running: this stack has no Airflow, so the "
            "provider cannot be interrogated. Runs in the H1 clean-stack "
            "workflow."
        ),
    ),
]


def _in_container(script: str) -> str:
    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "python", "-"],
        input=script,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"docker exec failed rc={result.returncode}: {result.stderr}"
        )
    return result.stdout


# Each signal is collected independently. A probe that dies on the first
# unexpected API returns no information at all, and this runs at the far end of
# a twenty-minute stack build - the cost of a blind failure is a whole cycle.
PROBE = """
import json

state = {}


def record(name, fn):
    try:
        state[name] = fn()
    except Exception as exc:
        state[name] = f"ERROR: {type(exc).__name__}: {exc}"


def provider_registered():
    from airflow.providers_manager import ProvidersManager
    return any("openlineage" in name for name in ProvidersManager().providers)


def listener_names():
    # Airflow 3.x registers listeners as pluggy plugins on the manager's `pm`.
    # They are modules, not instances, so the name is `__name__` rather than
    # anything derived from a type.
    from airflow.listeners.listener import get_listener_manager

    manager = get_listener_manager()
    return sorted(
        getattr(plugin, "__name__", None) or type(plugin).__module__
        for plugin in manager.pm.get_plugins()
    )


def transport():
    from airflow.providers.openlineage import conf
    return conf.transport()


def namespace():
    from airflow.providers.openlineage import conf
    return conf.namespace()


def disabled():
    from airflow.providers.openlineage import conf
    return conf.is_disabled()


record("provider_registered", provider_registered)
record("listener_names", listener_names)
record("transport", transport)
record("namespace", namespace)
record("disabled", disabled)

print(json.dumps(state, default=str))
"""


@pytest.fixture(scope="module")
def provider_state() -> dict:
    output = _in_container(PROBE)
    for line in reversed(output.splitlines()):
        if line.strip().startswith("{"):
            return json.loads(line)
    raise ValueError(f"no JSON payload in probe output: {output[:400]!r}")


def test_the_openlineage_provider_is_loaded_by_the_running_scheduler(provider_state):
    """Installed is not the same as active."""
    assert provider_state["provider_registered"] is True, (
        f"{PROVIDER} is installed but the running Airflow did not register it: "
        f"{provider_state['provider_registered']!r}"
    )


def test_the_provider_registers_its_lineage_listener(provider_state):
    """The listener is the mechanism: without it the provider is inert.

    Airflow emits OpenLineage through a listener hooked into task and DAG state
    changes, so a registered provider with no registered listener would leave
    every other assertion here true and nothing emitted. The provider registers
    it only when the OpenLineage config is present, which makes this a check on
    the deployed configuration and not merely on the installed package.
    """
    names = provider_state["listener_names"]
    assert isinstance(names, list), f"could not enumerate listeners: {names!r}"
    assert any(
        "openlineage" in name.lower() for name in names
    ), f"no OpenLineage listener among the registered listeners: {names}"


def test_the_provider_is_not_disabled(provider_state):
    """`AIRFLOW__OPENLINEAGE__DISABLED` silences emission without any other
    visible symptom, so it is asserted rather than assumed."""
    assert provider_state["disabled"] is False, provider_state


def test_the_provider_transport_points_at_the_shared_lineage_volume(provider_state):
    """A transport that resolves elsewhere would emit into a path nothing reads.

    The receipt reads one file; every producer must be configured to write it,
    and Airflow's config is expressed as JSON in an environment variable, which
    is exactly the kind of thing that silently parses into something else.
    """
    transport = provider_state["transport"]
    assert isinstance(transport, dict), transport
    assert transport.get("type") == "file", transport
    assert transport.get("log_file_path") == EXPECTED_LOG_PATH, transport
    assert transport.get("append") is True, transport


def test_the_provider_uses_the_platform_lineage_namespace(provider_state):
    """One namespace across producers, or the graphs do not join."""
    assert provider_state["namespace"] == "de-practicum", provider_state
