"""PID 1 confiavel dentro de imagem auditada; aplicacao e driver com UIDs distintos."""
import errno
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

APP_UID, DRIVER_UID = 62001, 62002
PATH = '/usr/local/bin:/usr/bin:/bin'
ENV = {'PATH': PATH, 'LANG': 'C.UTF-8', 'CI': 'true', 'HOME': '/tmp/app-home',
       'HOST': '127.0.0.1', 'NITRO_HOST': '127.0.0.1', 'PORT': '3000', 'NITRO_PORT': '3000',
       'NITRO_PRESET': 'node-server', 'NODE_ENV': 'production'}
live = []

def need(value, code):
    if not value:
        raise RuntimeError(code)

def own(tree, uid):
    os.chown(tree, uid, uid)
    os.chmod(tree, 0o700)
    for item in tree.rglob('*'):
        need(not item.is_symlink(), 'UNEXPECTED_SYMLINK')
        os.chown(item, uid, uid)
        os.chmod(item, 0o700 if item.is_dir() else 0o600)

def drain(stream, label):
    # Nao emitir texto de pacotes ou aplicacao. Somente resumo de tamanho e hash.
    digest = hashlib.sha256()
    count = 0
    while True:
        chunk = stream.read(65536)
        if not chunk:
            break
        digest.update(chunk)
        count += len(chunk)
        if count > 20_000_000:
            for child in live:
                try: child.kill()
                except OSError: pass
            break
    print(json.dumps({'diagnostic': label, 'bytes': count, 'sha256': digest.hexdigest()}), flush=True)

def child(args, uid, home, stdin=None):
    clean = dict(ENV, HOME=home, SCHEMA_VARIANT=os.environ.get('SCHEMA_VARIANT', ''))
    command = ['/usr/bin/setpriv', '--reuid=' + str(uid), '--regid=' + str(uid), '--clear-groups',
               '--inh-caps=-all', '--ambient-caps=-all', '--bounding-set=-all', '--no-new-privs',
               '/usr/bin/env', '-i', *[key + '=' + value for key, value in clean.items()], *args]
    p = subprocess.Popen(command, cwd='/app/project' if uid == APP_UID else '/tmp/browser-home', stdin=stdin or subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    live.append(p)
    return p

def stop_uid(uid):
    deadline = time.monotonic() + 5
    while True:
        pids = []
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit(): continue
            try:
                lines = (entry / 'status').read_text().splitlines()
                identities = next(line for line in lines if line.startswith('Uid:')).split()[1:]
                if str(uid) in identities: pids.append(int(entry.name))
            except (OSError, StopIteration): pass
        if not pids: return
        need(time.monotonic() < deadline, 'UID_PROCESS_CLEANUP_FAILED')
        for pid in pids:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
        time.sleep(0.05)

def tool(args, label, deadline):
    p = child(args, APP_UID, '/tmp/app-home')
    pumps = [threading.Thread(target=drain, args=(stream, label + channel), daemon=True)
             for stream, channel in ((p.stdout, '-stdout'), (p.stderr, '-stderr'))]
    for pump in pumps: pump.start()
    try:
        code = p.wait(timeout=deadline)
    finally:
        stop_uid(APP_UID)
    for pump in pumps: pump.join(timeout=3)
    need(code == 0, 'TOOL_FAILED_' + label)

def source_unchanged():
    expected = {str(p.relative_to('/input')) for p in Path('/input').rglob('*') if p.is_file()}
    generated = {'node_modules', '.output', '.tanstack', '.vite'}
    for current in Path('/app/project').rglob('*'):
        relative = current.relative_to('/app/project')
        if relative.parts[0] in generated:
            continue
        need(not current.is_symlink(), 'SOURCE_SYMLINK_ADDED')
        if current.is_file():
            need(str(relative) in expected, 'SOURCE_FILE_ADDED')
    for original in Path('/input').rglob('*'):
        if not original.is_file(): continue
        current = Path('/app/project') / original.relative_to('/input')
        need(current.is_file() and not current.is_symlink(), 'SOURCE_FILE_CHANGED')
        need(hashlib.sha256(current.read_bytes()).digest() == hashlib.sha256(original.read_bytes()).digest(), 'SOURCE_BYTES_CHANGED')

def preflight():
    need(os.geteuid() == 0 and Path('/.dockerenv').is_file(), 'CONTAINER_REQUIRED')
    need(json.loads(Path('/control/EXECUTION-POLICY.json').read_text()).get('phase8_authorized') is True, 'PHASE8_NOT_AUTHORIZED')
    need(os.environ.get('SCHEMA_CONTAINER_CONTRACT') == 'phase7d-v1', 'CONTAINER_CONTRACT')
    need(os.environ.get('SCHEMA_VARIANT') in {'base', 'proposta'}, 'VARIANT_REQUIRED')
    need(set(p.name for p in Path('/sys/class/net').iterdir()) == {'lo'}, 'NETWORK_INTERFACE')
    need(not Path('/proc/net/route').read_text().splitlines()[1:], 'IPV4_ROUTE_PRESENT')
    for line in Path('/proc/net/ipv6_route').read_text().splitlines():
        need(line.split()[-1] == 'lo', 'IPV6_ROUTE_PRESENT')
    for name in ('/run/docker.sock', '/var/run/docker.sock', '/run/containerd/containerd.sock'):
        need(not Path(name).exists(), 'HOST_SOCKET_PRESENT')
    for uid in (APP_UID, DRIVER_UID):
        try: pwd.getpwuid(uid)
        except KeyError: pass
        else: raise RuntimeError('UID_ALREADY_ASSIGNED')
    for binary in ('node', 'npm', 'google-chrome', 'setpriv'):
        need(shutil.which(binary, path=PATH), 'IMAGE_BINARY_MISSING')
    version = subprocess.check_output(['node', '--version'], env={'PATH': PATH}, text=True, timeout=5)
    need(version.startswith('v22.'), 'NODE_MAJOR_MISMATCH')
    for family, endpoint in ((socket.AF_INET, ('192.0.2.1', 443)), (socket.AF_INET6, ('2001:db8::1', 443))):
        try:
            s = socket.socket(family)
        except OSError as error:
            need(family == socket.AF_INET6 and error.errno == errno.EAFNOSUPPORT, 'SOCKET_PREFLIGHT_FAILED')
            continue
        with s:
            s.settimeout(2)
            try: s.connect(endpoint)
            except OSError as error:
                need(error.errno in {errno.ENETUNREACH, errno.EHOSTUNREACH}, 'NETWORK_FAILURE_NOT_CONCLUSIVE')
            else: raise RuntimeError('EXTERNAL_CONNECTION_SUCCEEDED')
    for name, uid in (('/tmp/app-home', APP_UID), ('/tmp/browser-home', DRIVER_UID)):
        Path(name).mkdir(mode=0o700)
        os.chown(name, uid, uid)
    # Confirmar identidade, grupos, capacidades e protecoes no mesmo launcher da carga.
    check = "import os,pathlib; s=pathlib.Path('/proc/self/status').read_text(); required=('CapInh:\\t0000000000000000','CapPrm:\\t0000000000000000','CapEff:\\t0000000000000000','CapBnd:\\t0000000000000000','CapAmb:\\t0000000000000000','NoNewPrivs:\\t1'); ok=os.getuid()==int(os.environ['EXPECTED_UID']) and os.getgid()==int(os.environ['EXPECTED_UID']) and not os.getgroups() and all(x in s for x in required); raise SystemExit(0 if ok else 78)"
    for uid in (APP_UID, DRIVER_UID):
        # EXPECTED_UID somente nesta verificacao confiavel; nao expor ambiente do host.
        cmd = ['/usr/bin/setpriv', '--reuid=' + str(uid), '--regid=' + str(uid), '--clear-groups', '--inh-caps=-all', '--ambient-caps=-all', '--bounding-set=-all', '--no-new-privs', '/usr/bin/env', '-i', 'EXPECTED_UID=' + str(uid), '/usr/bin/python3', '-I', '-c', check]
        subprocess.run(cmd, check=True, timeout=5)

def main():
    preflight()
    shutil.copytree('/input', '/app/project')
    own(Path('/app/project'), APP_UID)
    shutil.copytree('/cache', '/app/npm-cache')
    own(Path('/app/npm-cache'), APP_UID)
    tool(['npm', 'ci', '--offline', '--ignore-scripts', '--no-audit', '--no-fund', '--include=dev', '--include=optional', '--cache=/app/npm-cache', '--userconfig=/dev/null', '--globalconfig=/dev/null'], 'npm-ci-offline', 300)
    source_unchanged()
    tool(['node_modules/.bin/tsc', '--noEmit'], 'typecheck', 90)
    source_unchanged()
    tool(['npm', '--ignore-scripts', 'run', 'lint'], 'lint', 90)
    source_unchanged()
    tool(['npm', '--ignore-scripts', 'run', 'build'], 'build', 300)
    source_unchanged()
    driver = child(['node', '/control/validate-runtime.mjs'], DRIVER_UID, '/tmp/browser-home', stdin=subprocess.PIPE)
    threading.Thread(target=drain, args=(driver.stderr, 'driver-stderr'), daemon=True).start()
    need(select.select([driver.stdout], [], [], 30)[0], 'DRIVER_READY_TIMEOUT')
    need(driver.stdout.readline(4096) == b'READY_FOR_LOCAL_SERVER\n', 'DRIVER_NETWORK_PREFLIGHT_FAILED')
    server = child(['node', '.output/server/index.mjs'], APP_UID, '/tmp/app-home')
    for stream, name in ((server.stdout, 'server-stdout'), (server.stderr, 'server-stderr'), (driver.stdout, 'driver-stdout')):
        threading.Thread(target=drain, args=(stream, name), daemon=True).start()
    driver.stdin.write(b'CONTINUE\n'); driver.stdin.flush(); driver.stdin.close()
    need(driver.wait(timeout=300) == 0, 'DRIVER_FAILED')
    stop_uid(APP_UID); stop_uid(DRIVER_UID)
    source_unchanged()
    print('AUTOMATED_CHECKS_COMPLETE_MANUAL_REVIEW_PENDING', flush=True)

if __name__ == '__main__':
    os.umask(0o077)
    code = 0
    try:
        main()
    except Exception as error:
        reason = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r'[A-Z0-9_]{1,80}', str(error)) else 'CONTAINER_PREFLIGHT_OR_CHECKS'
        print('BLOCKED_' + reason, flush=True)
        code = 78
    finally:
        for uid in (APP_UID, DRIVER_UID):
            try: stop_uid(uid)
            except Exception: code = 78
    raise SystemExit(code)
