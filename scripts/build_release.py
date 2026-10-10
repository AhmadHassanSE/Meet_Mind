"""Build a source + tested frontend ZIP from an explicit Git-tracked allowlist."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('meetmind/backend/app/', 'meetmind/backend/nlp/',
               'meetmind/backend/scripts/', 'meetmind/backend/configs/',
               'meetmind/frontend/src/')
FILES = {'meetmind/README.md', 'meetmind/backend/pyproject.toml', 'meetmind/backend/uv.lock',
         'meetmind/backend/.python-version', 'meetmind/backend/BERT.md',
         'meetmind/backend/COMMITMENTS.md', 'meetmind/backend/PREPROCESSING.md',
         'meetmind/frontend/package.json', 'meetmind/frontend/package-lock.json',
         'meetmind/frontend/index.html', 'meetmind/frontend/tsconfig.json',
         'meetmind/frontend/vite.config.ts', 'docs/ci-cd.md'}


def build(output):
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    selected = sorted(p for p in tracked if p in FILES or p.startswith(DIRECTORIES))
    dist = ROOT / 'meetmind/frontend/dist'
    if not (dist / 'index.html').is_file():
        raise ValueError('Build the frontend before packaging: npm run build')
    # Only include regular generated build files, never follow links out of dist.
    built = sorted(p for p in dist.rglob('*') if p.is_file())
    if any(p.is_symlink() or not p.resolve().is_relative_to(dist.resolve()) for p in built):
        raise ValueError('Frontend build contains a symlink or file outside dist')
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = {'commit': revision, 'contents': [], 'model_weights_included': False,
                'note': 'Install dependencies and provide a trained BERT checkpoint and local Ollama separately. See meetmind/README.md.'}
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in selected + [p.relative_to(ROOT).as_posix() for p in built]:
            if any(part in {'__pycache__', 'node_modules', '.env', 'data', 'models', 'runs'} for part in PurePosixPath(relative).parts):
                raise ValueError(f'Unexpected private/generated path: {relative}')
            data = (ROOT / relative).read_bytes()
            archive.writestr(relative, data)
            manifest['contents'].append({'path': relative, 'sha256': hashlib.sha256(data).hexdigest()})
        archive.writestr('release-manifest.json', json.dumps(manifest, indent=2))
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{checksum}  {output.name}\n', encoding='utf-8')
    print(f'Built {output.name}: {len(manifest["contents"])} files; commit {revision}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
