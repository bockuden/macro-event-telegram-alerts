#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")
cd "$project_root"

python_command=${PYTHON_COMMAND:-python3}
"$python_command" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --editable '.[dev]'

printf '%s\n' 'Environment ready: .venv/bin/python'
