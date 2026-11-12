#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_REPOSITORY:-}" = anselmoads83/anselmo-schema-validation
test "${GITHUB_EVENT_NAME:-}" = workflow_dispatch
test "$(git -C comparison/base rev-parse HEAD)" = 97632988b7c9f1ffca113f9ddaaa1b801cc76259
python3 prepare-material.py
clean_home="${RUNNER_TEMP:?}/schema-npm-home"
mkdir -p "$clean_home"
for variant in base proposta; do
  (
    cd "comparison/$variant"
    # Nenhum codigo do projeto ou lifecycle de dependencias roda nesta etapa de rede.
    env -i PATH="$PATH" HOME="$clean_home" CI=true \
      npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org/
  )
done
