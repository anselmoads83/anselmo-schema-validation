"""Validacao explicita; nenhuma aquisicao, instalacao ou execucao de proposta."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
BASE_SHA = '97632988b7c9f1ffca113f9ddaaa1b801cc76259'
ZIP_SHA = 'd9456a739e69e9e5559300de11a47d2eaa1ddc10c9edd35c4e125906faa9f43f'
DIFF_SHA = 'e41ffbe494ae3b4950f3deb75348e9b8a80e3620b9221dbd5c5befe2e6b2c5c5'
MANIFEST = {
 'originais/src/routes/index.tsx': '1fd701ac7fd7c1aef255f5f3b1443fbc3f7907cdf903bdf27652e97177071526',
 'originais/src/routes/politica-de-privacidade.tsx': '3a8ffc4ec07809c26d2e33357f6fbffae5363b9e0d68e26ed3cdc943a1c96a0b',
 'proposta/src/components/StructuredData.tsx': '1394c68ba3a641053228fd403cd7cc858f1601682bb85cdd05615740d9ef9459',
 'proposta/src/lib/serialize-json-ld.ts': '68cb0aad8a802bf066370f7e81f2f05138ea0d9f64185b5af9f13bdf22cc3eb7',
 'proposta/src/lib/structured-data.ts': 'de96cad69fc1a843e5d27d330a3618a0d64445cb64a375d0a3f5e2c9affe4f6e',
 'proposta/src/routes/index.tsx': '91ca6889aab3f1cf3c1d20d1b8fc9e20a79df02c7be0cff24f10e03963f7e8f6',
 'proposta/src/routes/politica-de-privacidade.tsx': '55ae3e3f6eeee2b2474a43213ba36fbd87b24affb1692b0a0eaf332befb64b1c',
 'jsonld/home.json': '30f022d25ed6d9318ffde14f6e6e432b63424e47b2470d69ed361c0930bb5c6e',
 'jsonld/politica-de-privacidade.json': 'ad8b36d36d49814f998b5848f7b56d133ff6255f49d849a7ee88592eae38e585',
}

def require(condition, code):
    if not condition:
        raise ValueError(code)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def unique_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)

def validate_policy():
    policy = unique_json((ROOT / 'EXECUTION-POLICY.json').read_text())
    require(policy.get('schema_version') == 1, 'POLICY_VERSION')
    require(policy.get('phase8_authorized') is True, 'PHASE8_NOT_AUTHORIZED')
    require(policy.get('requires_reviewed_revision_input') is True, 'REVIEWED_REVISION_REQUIRED')
    require(re.fullmatch(r'[a-z0-9][a-z0-9./_-]*@sha256:[0-9a-f]{64}', policy.get('runtime_image') or ''), 'AUDITED_IMAGE_MISSING')
    require(re.fullmatch(r'[0-9a-f]{64}', policy.get('offline_cache_sha256') or ''), 'OFFLINE_CACHE_MISSING')
    return policy

def validate_tree(tree):
    for item in tree.rglob('*'):
        require(not item.is_symlink(), 'SOURCE_SYMLINK')
        if not item.is_file():
            continue
        name = item.name.lower()
        require(not (name == '.env' or name.startswith('.env.')) or name == '.env.example', 'ENV_FILE_FORBIDDEN')
        require(name not in {'.npmrc', 'npm-shrinkwrap.json', '.yarnrc', '.yarnrc.yml', '.netrc', '.git-credentials'}, 'CONFIG_FILE_FORBIDDEN')
        if name == '.env.example':
            # Nenhum arquivo de ambiente, nem exemplo, sera disponibilizado ao runtime.
            continue
        if name.endswith(('.pem', '.key', '.p12', '.pfx')):
            raise ValueError('CREDENTIAL_FILE_FORBIDDEN')

def validate_lock(tree):
    package_bytes = (tree / 'package.json').read_bytes()
    lock_bytes = (tree / 'package-lock.json').read_bytes()
    package = unique_json(package_bytes)
    lock = unique_json(lock_bytes)
    require(lock.get('lockfileVersion') == 3, 'LOCK_VERSION_NOT_REVIEWED')
    packages = lock.get('packages')
    require(isinstance(packages, dict) and '' in packages and len(packages) > 1, 'LOCK_STRUCTURE')
    for section in ('dependencies', 'devDependencies', 'optionalDependencies'):
        require(package.get(section, {}) == packages[''].get(section, {}), 'LOCK_PACKAGE_MISMATCH')
    require(not package.get('workspaces'), 'WORKSPACES_NOT_REVIEWED')
    for name, entry in packages.items():
        require(isinstance(entry, dict), 'LOCK_ENTRY')
        if not name:
            continue
        require(name.startswith('node_modules/') and '..' not in name.split('/'), 'LOCK_PATH')
        require(not entry.get('link') and not entry.get('inBundle'), 'LOCAL_OR_BUNDLED_DEPENDENCY')
        require(isinstance(entry.get('version'), str) and entry['version'], 'DEPENDENCY_VERSION')
        url = entry.get('resolved', '')
        require(isinstance(url, str) and re.fullmatch(r'https://registry\.npmjs\.org/[A-Za-z0-9@%._+~/-]+\.tgz', url), 'DEPENDENCY_ORIGIN')
        require(re.fullmatch(r'sha512-[A-Za-z0-9+/]+={0,2}', entry.get('integrity', '')), 'DEPENDENCY_INTEGRITY')
    return {'package_sha256': digest(package_bytes), 'lock_sha256': digest(lock_bytes)}

def prepare():
    policy = validate_policy()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, timeout=10).strip()
    require(re.fullmatch(r'[0-9a-f]{40}', os.environ.get('SCHEMA_APPROVED_REVISION', '')), 'APPROVED_REVISION_MISSING')
    require(revision == os.environ['SCHEMA_APPROVED_REVISION'], 'UNAPPROVED_VALIDATION_REVISION')
    base = ROOT / 'comparison/base'
    base_revision = subprocess.check_output(['git', '-C', str(base), 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
    require(base_revision == BASE_SHA, 'BASE_REVISION')
    require(not subprocess.check_output(['git', '-C', str(base), 'status', '--porcelain', '--untracked-files=all'], text=True, timeout=10).strip(), 'BASE_WORKTREE_CHANGED')
    # .git nao faz parte da superficie da carga; fonte fixa verificada antes da copia.
    with zipfile.ZipFile(ROOT / 'material-recuperado.zip') as archive:
        require(digest((ROOT / 'material-recuperado.zip').read_bytes()) == ZIP_SHA, 'ARCHIVE_HASH')
        require((ROOT / 'MATERIAL-SHA256.txt').read_text().split()[0] == ZIP_SHA, 'ARCHIVE_HASH_FILE')
        allowed = set(MANIFEST) | {'HASHES-SHA256.json', 'ALTERACOES.diff'}
        names = archive.namelist()
        require(len(names) == len(set(names)) and set(names) == allowed, 'ZIP_ENTRIES')
        require(sum(i.file_size for i in archive.infolist()) < 2_000_000, 'ZIP_SIZE')
        require(all(not (i.flag_bits & 1) and i.file_size < 500_000 for i in archive.infolist()), 'ZIP_ENTRY_LIMIT')
        require(unique_json(archive.read('HASHES-SHA256.json')) == MANIFEST, 'MANIFEST_REFERENCE')
        for name, expected in MANIFEST.items():
            require(digest(archive.read(name)) == expected, 'MATERIAL_HASH')
            if name.startswith('originais/'):
                require((base / name.removeprefix('originais/')).read_bytes() == archive.read(name), 'ORIGINAL_ROUTE_HASH')
        require(digest(archive.read('ALTERACOES.diff')) == DIFF_SHA, 'DIFF_HASH')
        variants = ROOT / 'comparison/verified'
        require(not variants.exists(), 'COMPARISON_ALREADY_EXISTS')
        variants.mkdir()
        for variant in ('base', 'proposta'):
            target = variants / variant
            shutil.copytree(base, target, ignore=shutil.ignore_patterns('.git', 'node_modules'))
            validate_tree(target)
            # Exemplos de ambiente nao entram na carga, sem modificar o original recuperado.
            for example in target.rglob('.env.example'):
                example.unlink()
            if variant == 'proposta':
                for name in MANIFEST:
                    if name.startswith('proposta/'):
                        destination = target / name.removeprefix('proposta/')
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(archive.read(name))
            validate_tree(target)
        fingerprints = {v: validate_lock(variants / v) for v in ('base', 'proposta')}
        require(fingerprints['base'] == fingerprints['proposta'], 'VARIANT_LOCK_DIVERGENCE')
        reference = variants / 'reference'
        reference.mkdir()
        for name in ('jsonld/home.json', 'jsonld/politica-de-privacidade.json'):
            (reference / Path(name).name).write_bytes(archive.read(name))
        (variants / 'integrity.json').write_text(json.dumps(fingerprints, sort_keys=True))
    print('MATERIAL_VERIFIED_NO_DEPENDENCIES_EXECUTED')

if __name__ == '__main__':
    try:
        prepare()
    except Exception as error:
        # Sem dump de caminhos, conteudo ou credenciais em logs publicos.
        code = str(error) if isinstance(error, ValueError) and re.fullmatch(r'[A-Z0-9_]{1,80}', str(error)) else 'MATERIAL_OR_POLICY_INVALID'
        print('BLOCKED_' + code, file=sys.stderr)
        raise SystemExit(78)
