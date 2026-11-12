#!/usr/bin/env bash
set -euo pipefail
test "${GITHUB_REPOSITORY:-}" = anselmoads83/anselmo-schema-validation
test "${GITHUB_EVENT_NAME:-}" = workflow_dispatch
command -v ip >/dev/null
command -v setpriv >/dev/null
command -v python3 >/dev/null
command -v google-chrome >/dev/null
ns="schema-${GITHUB_RUN_ID:?}-${GITHUB_RUN_ATTEMPT:?}"
cleanup() { sudo ip netns delete "$ns"; }
sudo ip netns add "$ns"
trap cleanup EXIT
sudo ip -n "$ns" link set lo up
uid="$(id -u)"
gid="$(id -g)"
runtime_home="${RUNNER_TEMP:?}/schema-runtime-home"
mkdir -p "$runtime_home"
# Namespace novo: apenas loopback; sem veth, bridge, NAT, DNS encaminhado ou portas publicas.
# Nenhuma regra de rede do host e alterada. O processo perde privilegios e nao pode usar sudo.
sudo ip netns exec "$ns" setpriv --reuid="$uid" --regid="$gid" --init-groups \
  --bounding-set=-all --no-new-privs env -i \
  PATH="$PATH" HOME="$runtime_home" CI=true NODE_ENV=production \
  NITRO_PRESET=node-server HOST=127.0.0.1 NITRO_HOST=127.0.0.1 \
  bash isolated-checks.sh
