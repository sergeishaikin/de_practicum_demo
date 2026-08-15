$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Uv {
    & uvx --from uv==0.12.5 uv --quiet @args
    if ($LASTEXITCODE -ne 0) {
        throw "uv failed with exit code $LASTEXITCODE"
    }
}

Push-Location $RepoRoot
try {
    Invoke-Uv lock
    Invoke-Uv export --locked --only-group dev --no-emit-project --output-file requirements-dev.txt
    Invoke-Uv pip compile `
        --universal `
        --generate-hashes `
        --python-version 3.12 `
        --constraint airflow.constraints.txt `
        --output-file airflow.requirements.txt `
        airflow.requirements.in

$Locks = @(
    @{ Input = "dbt/requirements.in"; Output = "dbt/requirements.txt"; Python = "3.12" },
    @{ Input = "iceberg/requirements.in"; Output = "iceberg/requirements.txt"; Python = "3.12" },
    @{ Input = "jupyter/requirements.in"; Output = "jupyter/requirements.txt"; Python = "3.10" },
    @{ Input = "kafka/producer/requirements.in"; Output = "kafka/producer/requirements.txt"; Python = "3.12" },
    @{ Input = "observability/requirements.in"; Output = "observability/requirements.txt"; Python = "3.12" },
    @{ Input = "spark/requirements.in"; Output = "spark/requirements.txt"; Python = "3.12" }
)

    foreach ($Lock in $Locks) {
        Invoke-Uv pip compile `
            --universal `
            --generate-hashes `
            --python-version $Lock.Python `
            --output-file $Lock.Output `
            $Lock.Input
    }
}
finally {
    Pop-Location
}
