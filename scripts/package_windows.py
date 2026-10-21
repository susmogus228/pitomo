"""Build a portable source ZIP with frontend, manifest and secret-boundary checks."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRS = {'.github', 'app', 'docs', 'migrations', 'scripts', 'tests', 'verification', 'frontend'}
FILES = {'.dockerignore', '.env.example', '.gitignore', 'alembic.ini', 'Dockerfile',
         'docker-compose.yml', 'docker-compose.dev.yml', 'docker-compose.frontend.yml',
         'main.py', 'pyproject.toml', 'pytest.ini', 'README.md', 'requirements.txt',
         'requirements-lock.txt', 'requirements-dev.txt', 'requirements-dev-lock.txt',
         'START.bat', 'STOP.bat', 'DIAGNOSTICS.bat', 'CREATE_ADMIN.bat', 'design-qa.md'}
EXCLUDED = {'node_modules', 'dist', '__pycache__', '.git', '.venv', 'work', 'outputs',
            '.pytest_cache', '.ruff_cache', 'coverage', '.vite'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    archive = args.output.resolve()
    if archive.exists():
        raise SystemExit('Output exists; choose a new filename to preserve the previous archive.')
    archive.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for directory, subdirs, filenames in os.walk(ROOT):
        parent = Path(directory)
        subdirs[:] = [d for d in subdirs if d not in EXCLUDED and not (parent / d).is_symlink()
                      and (parent != ROOT or d in DIRS)]
        for filename in filenames:
            p = parent / filename
            relative = p.relative_to(ROOT)
            if parent == ROOT and filename not in FILES:
                continue
            if p.is_symlink() or not p.resolve().is_relative_to(ROOT):
                raise ValueError('Unsafe package path')
            if (filename.startswith('.env') and filename != '.env.example') or filename == 'private.json':
                continue
            if p.suffix in {'.pyc', '.pyo', '.log', '.dump', '.db', '.sqlite', '.tsbuildinfo'}:
                continue
            if relative.as_posix() == 'verification/FILE_SHA256.json':
                continue
            paths.append(p)
    secret_values = []
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            key, _, value = line.partition('=')
            if any(word in key for word in ('PASSWORD', 'SECRET', 'DATABASE_URL', 'API_KEY', 'TOKEN')) and len(value) >= 16:
                secret_values.append(value.encode())
    entries = {}
    for path in sorted(paths):
        data = path.read_bytes()
        name = path.relative_to(ROOT).as_posix()
        if any(secret in data for secret in secret_values):
            raise ValueError(f'Secret found in packaged file: {name}')
        if name.endswith('.py'):
            ast.parse(data, filename=name)
        entries[name] = data
    required = {'frontend/package-lock.json', 'frontend/Dockerfile', 'frontend/nginx.conf',
                'frontend/docker-entrypoint.sh', 'docs/ONLINE_TESTING.md',
                'scripts/linux/oci-readiness.sh',
                'frontend/src/main.tsx', 'frontend/public/media/hero-cat.png',
                'frontend/public/media/pets-grid.png', 'docker-compose.frontend.yml', 'START.bat'}
    assert required <= entries.keys(), required - entries.keys()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
    entries['verification/FILE_SHA256.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    prefix = 'pitomo/'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in entries.items():
            z.writestr(prefix + name, data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(entries)
        for name, data in entries.items():
            assert z.read(prefix + name) == data, name
        assert not any('/node_modules/' in n or '/work/' in n or
                       (Path(n).name.startswith('.env') and Path(n).name != '.env.example')
                       for n in z.namelist())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    report = {'archive': str(archive), 'files': len(entries), 'bytes': archive.stat().st_size,
              'sha256': digest, 'crc': 'passed', 'source_bytes': 'passed', 'manifest': 'passed',
              'frontend_included': True, 'private_files_excluded': True,
              'secret_value_scan': 'passed', 'python_parse': 'passed'}
    archive.with_suffix('.verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
