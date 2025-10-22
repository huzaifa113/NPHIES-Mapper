#!/bin/bash
set -e
python -m venv .venv || true
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
