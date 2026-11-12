"""Preparacao futura: extracao restrita e verificacao do manifesto original."""
import hashlib
import json
import pathlib
import shutil
import zipfile

root = pathlib.Path(__file__).resolve().parent
archive = root / 'material-recuperado.zip'
expected_archive = (root / 'MATERIAL-SHA256.txt').read_text().split()[0]
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected_archive, 'ZIP divergente'
allowed = {
    'HASHES-SHA256.json', 'ALTERACOES.diff',
    'originais/src/routes/index.tsx',
    'originais/src/routes/politica-de-privacidade.tsx',
    'proposta/src/routes/index.tsx',
    'proposta/src/routes/politica-de-privacidade.tsx',
    'proposta/src/components/StructuredData.tsx',
    'proposta/src/lib/serialize-json-ld.ts',
    'proposta/src/lib/structured-data.ts',
    'jsonld/home.json', 'jsonld/politica-de-privacidade.json',
}
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist()) == allowed, 'Conteudo inesperado no ZIP'
    manifest = json.loads(z.read('HASHES-SHA256.json'))
    assert set(manifest) == allowed - {'HASHES-SHA256.json', 'ALTERACOES.diff'}
    for name, digest in manifest.items():
        assert hashlib.sha256(z.read(name)).hexdigest() == digest, name
    assert hashlib.sha256(z.read('ALTERACOES.diff')).hexdigest() == 'e41ffbe494ae3b4950f3deb75348e9b8a80e3620b9221dbd5c5befe2e6b2c5c5'
    base = root / 'comparison/base'
    for name in manifest:
        if name.startswith('originais/'):
            assert (base / name.removeprefix('originais/')).read_bytes() == z.read(name), 'Base diferente do original documentado'
    proposal = root / 'comparison/proposta'
    assert not proposal.exists(), 'Nao sobrescrever comparacao existente'
    shutil.copytree(base, proposal, ignore=shutil.ignore_patterns('.git', 'node_modules'))
    for name in manifest:
        if name.startswith('proposta/'):
            target = proposal / name.removeprefix('proposta/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(name))
    material = root / 'comparison/material'
    material.mkdir()
    for name in allowed:
        target = material / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(z.read(name))
for target in [root / 'comparison/base', root / 'comparison/proposta']:
    assert not (target / '.npmrc').exists(), 'Configuracao npm inesperada'
    assert not list(target.glob('.env')) and not list(target.glob('.env.local')), 'Arquivo de ambiente nao permitido'
    lock = json.loads((target / 'package-lock.json').read_text())
    for package in lock.get('packages', {}).values():
        resolved = package.get('resolved')
        if resolved:
            assert resolved.startswith('https://registry.npmjs.org/'), 'Origem fora do registry aprovado'
            assert package.get('integrity'), 'Dependencia sem integridade'
print('Base e proposta preparadas; manifesto e diff correspondentes.')
