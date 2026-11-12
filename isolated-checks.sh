#!/usr/bin/env bash
set -euo pipefail
# Todos os filhos (build, servidor, navegador e driver) herdam este mesmo namespace.
test "$(ip -o link show | wc -l)" -eq 1
test -z "$(ip route show default)"
test -z "$(ip -6 route show default)"
python3 - <<'PY'
import http.server, socket, threading, urllib.request
class Fixture(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'local-only')
    def log_message(self, *args): pass
server = http.server.HTTPServer(('127.0.0.1', 0), Fixture)
threading.Thread(target=server.serve_forever, daemon=True).start()
assert urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}', timeout=2).read() == b'local-only'
for family, address in [(socket.AF_INET, ('192.0.2.1', 443)), (socket.AF_INET6, ('2001:db8::1', 443))]:
    s = socket.socket(family); s.settimeout(2)
    try:
        s.connect(address)
    except OSError:
        pass
    else:
        raise AssertionError('Saida externa possivel: interromper')
    finally:
        s.close()
server.shutdown()
print('Fixture local acessivel; saida IPv4 e IPv6 bloqueada antes do runtime.')
PY
root="$PWD"
mkdir -p comparison/results
status=0
for variant in base proposta; do
  cd "$root/comparison/$variant"
  # node_modules/.bin evita npx/download automatico. Nenhum script de instalacao e habilitado.
  node_modules/.bin/tsc --noEmit >"$root/comparison/results/$variant-typecheck.log" 2>&1 || status=1
  npm run lint >"$root/comparison/results/$variant-lint.log" 2>&1 || status=1
  npm run build >"$root/comparison/results/$variant-build.log" 2>&1 || status=1
done
cd "$root"
if test "$status" -ne 0; then
  echo 'Build/typecheck/lint nao aprovados. Comparar logs locais por variante; nao aprovar integracao.'
  exit 1
fi
node validate-runtime.mjs
