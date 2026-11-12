#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_REPOSITORY:-}" = anselmoads83/anselmo-schema-validation
test "${GITHUB_EVENT_NAME:-}" = workflow_dispatch
# Identificacao explicita, sem transmitir tokens ao processo privilegiado.
# O supervisor valida novamente politica, revisao e precondicoes antes de usar o Docker.
exec sudo -- /usr/bin/python3 -I "$PWD/supervise-validation.py" \
  --workspace "$PWD" --revision "${GITHUB_SHA:?}" \
  --approved-revision "${SCHEMA_APPROVED_REVISION:?}" \
  --repository "$GITHUB_REPOSITORY" --event "$GITHUB_EVENT_NAME"
