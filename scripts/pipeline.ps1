param([ValidateSet('staging','production')][string]$Environment = 'staging', [string]$Version = 'local')
$ErrorActionPreference = 'Stop'
$pythonExecutable = if ($env:PYTHON_EXECUTABLE) { $env:PYTHON_EXECUTABLE } else { 'python' }
& $pythonExecutable "$PSScriptRoot/release.py" pipeline --env $Environment --image "inventory:$Version" --version $Version --monitoring
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
