#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_REPOSITORY:-}" = anselmoads83/anselmo-schema-validation
test "${GITHUB_EVENT_NAME:-}" = workflow_dispatch
# Nenhum npm, download ou lifecycle no host. A politica bloqueia antes de preparar cargas.
python3 -I prepare-material.py
