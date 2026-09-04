"""Report what this machine can actually run, right now.

The repository documents a *contract* about the local environment; this reports
the *facts*. Keeping them apart is the point: a document that hardcodes "12 CPUs
and 27 images" is a lie within a month, while a document that says "Docker
Desktop is an available runtime and a stopped daemon is not an unavailable
dependency" stays true until someone deliberately changes it.

Strictly read-only. It starts nothing, stops nothing, pulls nothing and writes
only the report file it is asked for. That matters because the repository treats
Docker, Kafka, Spark, MinIO, Postgres and Iceberg as stateful, and a diagnostic
that mutates state cannot be run freely while deciding whether to run anything.

    uv run python scripts/local_runtime_inventory.py
    uv run python scripts/local_runtime_inventory.py --json artifacts/local-environment/runtime-inventory.json

Exit code is 0 whenever the inventory was produced, including when Docker is
stopped -- "Docker is not running" is a finding to report, not an error. Use
``--require-docker`` to make an unreachable engine a failure instead.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.extended.yml")

# Values that would leak if a report were shared. Matched case-insensitively
# against environment keys before anything from `.env` is recorded.
SECRET_KEY_PATTERN = re.compile(
    r"(PASSWORD|SECRET|TOKEN|KEY|CREDENTIAL)", re.IGNORECASE
)
# `*_IMAGE` keys are the exception: an image reference is not a secret, and
# comparing them is the whole point of the drift check below.
IMAGE_KEY_PATTERN = re.compile(r"^[A-Z0-9_]*IMAGE$")


def _run(command: list[str], timeout: int = 60) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        return 127, "", f"{command[0]} not found on PATH"
    except subprocess.SubprocessError as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _docker_format(fields: dict[str, str]) -> dict[str, Any]:
    """One `docker info` call per field, so one unsupported field cannot blank
    the whole report."""
    out: dict[str, Any] = {}
    for name, template in fields.items():
        code, stdout, stderr = _run(["docker", "info", "--format", template])
        out[name] = stdout if code == 0 else f"unavailable: {stderr or code}"
    return out


def host_facts() -> dict[str, Any]:
    facts: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "logical_cpus": None,
        "ram_gb": None,
        "cpu_model": None,
    }
    try:
        import os as _os

        facts["logical_cpus"] = _os.cpu_count()
    except Exception:
        pass

    if platform.system() == "Windows":
        code, stdout, _ = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "$cs=Get-CimInstance Win32_ComputerSystem;"
                "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1;"
                "Write-Output ($cpu.Name.Trim() + '|' + "
                "[math]::Round($cs.TotalPhysicalMemory/1GB,2))",
            ],
            timeout=90,
        )
        if code == 0 and "|" in stdout:
            model, ram = stdout.rsplit("|", 1)
            facts["cpu_model"] = model.strip()
            try:
                facts["ram_gb"] = float(ram)
            except ValueError:
                pass
    return facts


def docker_facts() -> dict[str, Any]:
    """Docker's readiness and resource envelope.

    `docker --version` answers only whether the CLI exists; the engine is a
    separate question, and conflating them is precisely how a stopped daemon
    gets mistaken for an absent one.
    """
    facts: dict[str, Any] = {
        "cli_present": shutil.which("docker") is not None,
        "engine_reachable": False,
    }
    if not facts["cli_present"]:
        facts["note"] = "docker CLI is not on PATH"
        return facts

    code, stdout, _ = _run(["docker", "--version"])
    facts["cli_version"] = stdout if code == 0 else None

    code, stdout, stderr = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    facts["engine_reachable"] = code == 0 and bool(stdout)
    if not facts["engine_reachable"]:
        facts["engine_error"] = stderr or f"exit {code}"
        facts["note"] = (
            "Docker CLI is installed but the engine is not responding. On this "
            "host that usually means Docker Desktop is stopped, which is a "
            "startable state, not an unavailable dependency."
        )
        return facts

    facts["engine_version"] = stdout
    facts.update(
        _docker_format(
            {
                "server_os": "{{.OperatingSystem}}",
                "server_architecture": "{{.Architecture}}",
                "kernel": "{{.KernelVersion}}",
                "os_type": "{{.OSType}}",
                "storage_driver": "{{.Driver}}",
                "docker_root_dir": "{{.DockerRootDir}}",
                "cpus": "{{.NCPU}}",
                "memory_bytes": "{{.MemTotal}}",
            }
        )
    )
    try:
        facts["memory_gb"] = round(int(facts["memory_bytes"]) / (1024**3), 2)
    except (TypeError, ValueError):
        facts["memory_gb"] = None

    code, stdout, _ = _run(["docker", "compose", "version", "--short"])
    facts["compose_version"] = stdout if code == 0 else None

    code, stdout, _ = _run(["docker", "system", "df", "--format", "json"])
    if code == 0 and stdout:
        facts["disk_usage"] = [
            json.loads(line) for line in stdout.splitlines() if line.strip()
        ]
    return facts


def _compose_command(env_file: str, *args: str) -> list[str]:
    command = ["docker", "compose", "--env-file", env_file]
    for name in COMPOSE_FILES:
        command += ["-f", name]
    return command + ["--profile", "*"] + list(args)


def compose_facts(env_file: str) -> dict[str, Any]:
    """The declared runtime graph, taken from Compose rather than transcribed.

    Any list of services or images maintained by hand drifts from the Compose
    files it claims to describe, so nothing here is written down twice.
    """
    facts: dict[str, Any] = {"env_file": env_file}
    if not (REPO_ROOT / env_file).exists():
        facts["error"] = f"{env_file} does not exist"
        return facts

    code, stdout, stderr = _run(
        _compose_command(env_file, "config", "--services"), timeout=180
    )
    if code != 0:
        facts["error"] = stderr or f"exit {code}"
        return facts
    facts["services"] = sorted(
        line.strip() for line in stdout.splitlines() if line.strip()
    )

    code, stdout, _ = _run(
        _compose_command(env_file, "config", "--images"), timeout=180
    )
    images = sorted({line.strip() for line in stdout.splitlines() if line.strip()})
    facts["images"] = images
    facts["locally_built_images"] = [
        image for image in images if image.startswith("de-practicum-demo-")
    ]
    facts["floating_images"] = [
        image
        for image in images
        if image.endswith(":latest")
        or ("@" not in image and ":" not in image.rsplit("/", 1)[-1])
    ]
    return facts


def _image_pins(path: Path) -> dict[str, str]:
    """`*_IMAGE` assignments from an env file. Nothing else is read."""
    pins: dict[str, str] = {}
    if not path.exists():
        return pins
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if IMAGE_KEY_PATTERN.match(key) and not SECRET_KEY_PATTERN.search(
            key.replace("IMAGE", "")
        ):
            pins[key] = value.strip()
    return pins


def image_pin_drift() -> dict[str, Any]:
    """Where the local `.env` disagrees with the committed `.env.example`.

    This is the difference between a local run and a CI run, and it is invisible
    from the Compose files because they reference variables. A local result
    obtained against a floating tag is not comparable to a CI result obtained
    against a digest, so the drift is reported rather than assumed away.
    """
    committed = _image_pins(REPO_ROOT / ".env.example")
    local = _image_pins(REPO_ROOT / ".env")
    if not local:
        return {"local_env_present": False, "differences": [], "floating_locally": []}

    differences = [
        {"variable": key, "committed": committed[key], "local": local[key]}
        for key in sorted(set(committed) & set(local))
        if committed[key] != local[key]
    ]
    floating = sorted(
        key
        for key, value in local.items()
        if value.endswith(":latest")
        or ("@" not in value and ":" not in value.rsplit("/", 1)[-1])
    )
    return {
        "local_env_present": True,
        "differences": differences,
        "floating_locally": floating,
    }


def running_containers() -> list[dict[str, str]]:
    code, stdout, _ = _run(
        [
            "docker",
            "ps",
            "--all",
            "--format",
            "{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Status}}",
        ]
    )
    if code != 0 or not stdout:
        return []
    rows = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            rows.append(
                {
                    "name": parts[0],
                    "image": parts[1],
                    "state": parts[2],
                    "status": parts[3],
                }
            )
    return rows


def collect(env_file: str) -> dict[str, Any]:
    docker = docker_facts()
    inventory: dict[str, Any] = {
        "host": host_facts(),
        "docker": docker,
        "image_pin_drift": image_pin_drift(),
    }
    if docker.get("engine_reachable"):
        inventory["compose"] = compose_facts(env_file)
        inventory["containers"] = running_containers()
    else:
        inventory["compose"] = {
            "skipped": "the Docker engine is not reachable; start Docker Desktop"
        }
        inventory["containers"] = []
    return inventory


def render(inventory: dict[str, Any]) -> str:
    host = inventory["host"]
    docker = inventory["docker"]
    lines = [
        "Local runtime inventory",
        "=======================",
        "",
        "Host",
        f"  OS            {host['os']} ({host['os_version']})",
        f"  CPU           {host.get('cpu_model') or 'unknown'}",
        f"  Logical CPUs  {host.get('logical_cpus')}",
        f"  RAM           {host.get('ram_gb')} GB",
        f"  Architecture  {host['architecture']}",
        "",
        "Docker",
        f"  CLI present   {docker.get('cli_present')}",
        f"  Engine ready  {docker.get('engine_reachable')}",
    ]
    if not docker.get("engine_reachable"):
        lines += [
            f"  {docker.get('note', '')}",
            "",
            "  ACTION: start Docker Desktop and re-run. A stopped daemon is not",
            "  an unavailable dependency - see docs/LOCAL-ENVIRONMENT.md.",
        ]
    else:
        lines += [
            f"  Engine        {docker.get('engine_version')}",
            f"  Compose       {docker.get('compose_version')}",
            f"  Backend       {docker.get('server_os')} / {docker.get('kernel')}",
            f"  CPUs          {docker.get('cpus')}",
            f"  Memory        {docker.get('memory_gb')} GB",
            f"  Storage       {docker.get('storage_driver')} at "
            f"{docker.get('docker_root_dir')}",
        ]
        compose = inventory.get("compose", {})
        if "error" in compose:
            lines += ["", f"Compose       unavailable: {compose['error']}"]
        else:
            lines += [
                "",
                "Compose",
                f"  Services      {len(compose.get('services', []))}",
                f"  Images        {len(compose.get('images', []))}",
                f"  Built locally {len(compose.get('locally_built_images', []))}",
            ]
            if compose.get("floating_images"):
                lines.append(f"  FLOATING      {', '.join(compose['floating_images'])}")
        running = [
            c for c in inventory.get("containers", []) if c["state"] == "running"
        ]
        lines += [
            "",
            f"Containers    {len(running)} running "
            f"({len(inventory.get('containers', []))} total)",
        ]

    drift = inventory["image_pin_drift"]
    if drift.get("floating_locally") or drift.get("differences"):
        lines += ["", "Image pin drift (.env vs .env.example)"]
        for name in drift.get("floating_locally", []):
            lines.append(f"  FLOATING      {name} is not pinned by digest locally")
        for diff in drift.get("differences", []):
            lines.append(f"  DIFFERS       {diff['variable']}")
        lines += [
            "  Local live results are therefore not directly comparable to CI,",
            "  which resolves images from the committed .env.example digests.",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--json",
        dest="json_path",
        help="also write the machine-readable inventory to this path",
    )
    parser.add_argument(
        "--require-docker",
        action="store_true",
        help="exit non-zero when the Docker engine is not reachable",
    )
    args = parser.parse_args(argv)

    inventory = collect(args.env_file)
    print(render(inventory))

    if args.json_path:
        destination = Path(args.json_path)
        if not destination.is_absolute():
            destination = REPO_ROOT / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8"
        )
        print(f"\nWrote {destination}")

    if args.require_docker and not inventory["docker"].get("engine_reachable"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
