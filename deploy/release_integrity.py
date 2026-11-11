"""Create/verify a release inventory without needing third-party packages."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def release_files(root: Path):
    for folder in ('Noise Survey Analysis', 'SLM Parsers/src', 'SD Card Import', '_lib',
                   'runtime/wheelhouse/cp313', 'runtime/installers'):
        for path in (root / folder).rglob('*'):
            if (path.is_file() and not any(part in ('__pycache__', '.git', '.pytest_cache') for part in path.parts)
                    and path.name not in ('config.json', 'parse_log.txt') and path.suffix not in ('.pyc', '.log')):
                yield path
    for path in root.iterdir():
        if path.is_file() and path.suffix.lower() in ('.ps1', '.bat', '.txt'):
            yield path
    yield root / 'runtime/bootstrap.json'
    yield root / 'runtime/manifest.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['create', 'verify', 'backup'])
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    inventory = root / 'runtime/release-integrity.json'
    if args.mode == 'backup':
        output = root / 'runtime' / 'previous-releases' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip')
        output.parent.mkdir(parents=True, exist_ok=True)
        candidates = [p for folder in ('Noise Survey Analysis', 'SLM Parsers', 'SD Card Import', '_lib')
                      for p in (root / folder).rglob('*') if p.is_file()
                      and not any(part in ('.git', '__pycache__', '.pytest_cache') for part in p.parts)]
        candidates += [p for p in root.iterdir() if p.is_file()]
        candidates += [p for p in (root / 'runtime').glob('*.json') if p.is_file()]
        with ZipFile(output, 'x', compression=ZIP_DEFLATED) as archive:
            for path in candidates:
                archive.write(path, path.relative_to(root).as_posix())
        print(f'Previous release backed up: {output}')
    elif args.mode == 'create':
        files = {path.relative_to(root).as_posix(): digest(path) for path in sorted(release_files(root))}
        inventory.write_text(json.dumps({'algorithm': 'sha256', 'files': files}, indent=2) + '\n', encoding='utf-8')
        print(f'Recorded {len(files)} release files.')
    else:
        files = json.loads(inventory.read_text(encoding='utf-8-sig'))['files']
        failures = []
        for name, expected in files.items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or digest(path) != expected:
                failures.append(name)
        if failures:
            raise SystemExit('Missing or changed release files: ' + ', '.join(failures))
        print(f'Verified {len(files)} release files.')


if __name__ == '__main__':
    main()
