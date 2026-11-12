"""Supervisor confiavel do host. Nenhuma carga executa diretamente no runner.

Requer imagem local por digest auditado e bundle de cache offline auditado.
Nao baixa imagens, pacotes ou ferramentas e nunca usa shell=True.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

CONTROLS = ('runtime-supervisor.py', 'validate-runtime.mjs', 'isolated-checks.sh', 'EXECUTION-POLICY.json')

def need(value, code):
    if not value:
        raise RuntimeError(code)

def sha(file):
    h = hashlib.sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def run(args, timeout=30):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout,
                          env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', 'LANG': 'C.UTF-8'})

def freeze_tree(tree):
    for item in tree.rglob('*'):
        need(not item.is_symlink(), 'SNAPSHOT_SYMLINK')
        os.chown(item, 0, 0)
        os.chmod(item, 0o555 if item.is_dir() else 0o444)
    os.chown(tree, 0, 0)
    os.chmod(tree, 0o555)

def extract_cache(archive, target, expected):
    need(archive.is_file() and not archive.is_symlink(), 'CACHE_MISSING')
    need(sha(archive) == expected, 'CACHE_HASH')
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        names = [i.filename for i in entries]
        need(len(names) == len(set(names)), 'CACHE_DUPLICATES')
        need(len(entries) < 200000 and sum(i.file_size for i in entries) < 3_000_000_000, 'CACHE_LIMIT')
        for entry in entries:
            name = entry.filename
            need(re.fullmatch(r'_cacache/[A-Za-z0-9_./-]+', name) and '..' not in name.split('/'), 'CACHE_PATH')
            need(not (entry.flag_bits & 1), 'CACHE_ENCRYPTED')
            # Escrever somente bytes regulares, nunca permissao/symlink do ZIP.
            destination = target / name
            if entry.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with z.open(entry) as source, destination.open('xb') as output:
                    shutil.copyfileobj(source, output)
    freeze_tree(target)

def main():
    p = argparse.ArgumentParser()
    for name in ('workspace', 'revision', 'approved-revision', 'repository', 'event'):
        p.add_argument('--' + name, required=True)
    args = p.parse_args()
    need(os.geteuid() == 0, 'TRUSTED_SUPERVISOR_REQUIRES_ROOT')
    need(args.repository == 'anselmoads83/anselmo-schema-validation' and args.event == 'workflow_dispatch', 'EXECUTION_CONTEXT')
    need(re.fullmatch('[0-9a-f]{40}', args.revision) and args.revision == args.approved_revision, 'REVISION_NOT_APPROVED')
    workspace = Path(args.workspace).resolve(strict=True)
    need(run(['git', '-c', 'safe.directory=' + str(workspace), '-C', str(workspace), 'rev-parse', 'HEAD']).stdout.strip() == args.revision, 'WORKSPACE_REVISION')
    policy = json.loads((workspace / 'EXECUTION-POLICY.json').read_text())
    need(policy.get('phase8_authorized') is True, 'PHASE8_NOT_AUTHORIZED')
    need(policy.get('requires_reviewed_revision_input') is True, 'REVISION_POLICY')
    image = policy.get('runtime_image')
    need(isinstance(image, str) and re.fullmatch(r'[a-z0-9][a-z0-9./_-]*@sha256:[0-9a-f]{64}', image), 'AUDITED_IMAGE_MISSING')
    need(re.fullmatch('[0-9a-f]{64}', policy.get('offline_cache_sha256') or ''), 'CACHE_REFERENCE_MISSING')
    # Somente imagem ja disponivel: --pull=never tambem e aplicado ao container.
    need(shutil.which('docker', path='/usr/bin:/bin'), 'DOCKER_UNAVAILABLE')
    image_info = json.loads(run(['docker', 'image', 'inspect', image]).stdout)[0]
    need(image in image_info.get('RepoDigests', []), 'IMAGE_DIGEST_NOT_LOCAL')
    verified = workspace / 'comparison/verified'
    need(verified.is_dir() and not verified.is_symlink(), 'VERIFIED_MATERIAL_MISSING')
    inventory = {}
    for name in CONTROLS:
        file = workspace / name
        need(file.is_file() and not file.is_symlink(), 'CONTROL_FILE')
        inventory[name] = sha(file)
    records = []
    active = None
    def remove_active():
        nonlocal active
        if active:
            run(['docker', 'rm', '-f', active])
            active = None
    try:
        with ExitStack() as stack:
            temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix='schema-validation-', dir='/var/tmp'))
            # Ordem LIFO: encerrar container antes de remover fontes/evidencias temporarias.
            stack.callback(remove_active)
            stage = Path(temporary)
            os.chmod(stage, 0o700)
            controls = stage / 'control'
            controls.mkdir()
            for name in CONTROLS:
                shutil.copyfile(workspace / name, controls / name)
                need(sha(controls / name) == inventory[name], 'CONTROL_COPY_HASH')
            freeze_tree(controls)
            cache = stage / 'cache'
            cache.mkdir()
            extract_cache(workspace / 'offline-cache.zip', cache, policy['offline_cache_sha256'])
            for variant in ('base', 'proposta'):
                variant_stage = stage / variant
                variant_stage.mkdir()
                source = variant_stage / 'input'
                need(not any(i.is_symlink() for i in (verified / variant).rglob('*')), 'SOURCE_SYMLINK')
                shutil.copytree(verified / variant, source, symlinks=False)
                freeze_tree(source)
                reference = variant_stage / 'reference'
                need(not any(i.is_symlink() for i in (verified / 'reference').rglob('*')), 'REFERENCE_SYMLINK')
                shutil.copytree(verified / 'reference', reference)
                freeze_tree(reference)
                evidence = variant_stage / 'evidence'
                evidence.mkdir(mode=0o700)
                os.chown(evidence, 62002, 62002)
                active = 'schema-' + os.urandom(12).hex()
                # Sem rede, sockets, PID/IPC do host, mounts de ferramentas do host ou privilegio amplo.
                command = ['docker', 'create', '--pull=never', '--name', active,
                    '--network=none', '--ipc=private', '--read-only', '--pids-limit=512', '--memory=6g', '--cpus=2',
                    '--cap-drop=ALL', '--cap-add=SETUID', '--cap-add=SETGID', '--cap-add=SETPCAP', '--cap-add=KILL',
                    '--security-opt=no-new-privileges=true', '--no-healthcheck', '--user=0:0', '--workdir=/app',
                    '--tmpfs=/app:rw,nosuid,nodev,size=3g,mode=0755',
                    '--tmpfs=/tmp:rw,nosuid,nodev,size=512m,mode=1777',
                    '--tmpfs=/run:rw,nosuid,nodev,noexec,size=16m,mode=0755', '--shm-size=256m',
                    '--mount', f'type=bind,src={controls},dst=/control,readonly',
                    '--mount', f'type=bind,src={source},dst=/input,readonly',
                    '--mount', f'type=bind,src={reference},dst=/reference,readonly',
                    '--mount', f'type=bind,src={cache},dst=/cache,readonly',
                    '--mount', f'type=bind,src={evidence},dst=/evidence',
                    '--env', 'SCHEMA_CONTAINER_CONTRACT=phase7d-v1',
                    '--env', 'SCHEMA_VARIANT=' + variant,
                    '--entrypoint=/usr/bin/python3', image, '-I', '/control/runtime-supervisor.py']
                run(command)
                spec = json.loads(run(['docker', 'inspect', active]).stdout)[0]
                host = spec['HostConfig']
                need(host['NetworkMode'] == 'none' and host['ReadonlyRootfs'] and not host['Privileged'], 'CONTAINER_SPEC')
                need(not host.get('PortBindings') and not host.get('Devices') and not host.get('PidMode') and not host.get('VolumesFrom'), 'HOST_RESOURCE_EXPOSURE')
                need(all(m['Destination'] in {'/control', '/input', '/reference', '/cache', '/evidence', '/app', '/tmp', '/run'} for m in spec['Mounts']), 'UNEXPECTED_MOUNT')
                need(set(host.get('CapAdd') or []) == {'SETUID', 'SETGID', 'SETPCAP', 'KILL'}, 'SUPERVISOR_CAPABILITIES')
                need('no-new-privileges=true' in host.get('SecurityOpt', []), 'NO_NEW_PRIVILEGES')
                result = run(['docker', 'start', '--attach', active], timeout=1050)
                # Nunca publicar stdout/stderr arbitrarios da carga. Somente resultado estruturado permitido.
                need((evidence / 'result.json').is_file() and not (evidence / 'result.json').is_symlink(), 'DRIVER_RESULT_MISSING')
                need((evidence / 'result.json').stat().st_size < 1_000_000, 'DRIVER_RESULT_LIMIT')
                data = json.loads((evidence / 'result.json').read_text())
                need(set(data) == {'automated_checks', 'manual_review', 'cases', 'comparison', 'diagnostics'} and data['automated_checks'] == 'passed' and data['diagnostics'] == [], 'DRIVER_CHECKS_FAILED')
                need(data['manual_review'] == 'pending', 'MANUAL_REVIEW_NOT_PROVEN')
                if records:
                    need(data['comparison'] == records[0]['comparison'], 'VARIANT_REGRESSION')
                records.append({'variant': variant, 'automated_checks': 'passed', 'manual_review': 'pending', 'comparison': data['comparison']})
                run(['docker', 'rm', '-f', active])
                active = None
            need(all(sha(workspace / name) == value for name, value in inventory.items()), 'CONTROL_MUTATION')
    finally:
        if active:
            # Docker encerra o cgroup inteiro; nao depender de grupos de processo da carga.
            try:
                run(['docker', 'rm', '-f', active])
            except Exception:
                print('CRITICAL_CONTAINER_CLEANUP_FAILED', file=sys.stderr)
                raise
    print(json.dumps({'automated_results': [{k: v for k, v in r.items() if k != 'comparison'} for r in records], 'overall': 'INCOMPLETE_MANUAL_REVIEW'}))
    return 2

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        reason = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r'[A-Z0-9_]{1,80}', str(error)) else 'SUPERVISOR_POLICY_OR_RUNTIME'
        if isinstance(error, subprocess.CalledProcessError):
            for line in (error.stdout or '')[-8192:].splitlines():
                if re.fullmatch(r'BLOCKED_[A-Z0-9_]{1,80}', line):
                    print(line, file=sys.stderr)
        print('BLOCKED_' + reason, file=sys.stderr)
        raise SystemExit(78)
