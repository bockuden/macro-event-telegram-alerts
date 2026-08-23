[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot

try {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    }
    else {
        throw "Python 3.12 or newer was not found."
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the virtual environment."
    }

    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }

    & .\.venv\Scripts\python.exe -m pip install --editable ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install the project."
    }

    Write-Host "Environment ready: .venv\Scripts\python.exe"
}
finally {
    Pop-Location
}
