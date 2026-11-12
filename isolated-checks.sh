#!/usr/bin/env bash
set -euo pipefail
# A antiga execucao direta no host foi removida. Somente o supervisor da imagem restrita.
if test "${SCHEMA_CONTAINER_CONTRACT:-}" != phase7d-v1; then
  echo 'BLOCKED_CONTAINER_CONTRACT' >&2
  exit 78
fi
exec /usr/bin/python3 -I /control/runtime-supervisor.py
