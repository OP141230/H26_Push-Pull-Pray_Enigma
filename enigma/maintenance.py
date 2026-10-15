"""One whitelisted change, explicit approval, stale-evidence guard and backup."""
import difflib
from pathlib import Path

from .evidence import digest, inspect_repository, safe_read


def proposal(root, finding):
    action = finding['proposed_action']
    raw, source = safe_read(Path(root).resolve(), 'pyproject.toml')
    if action['path'] != 'pyproject.toml' or digest(raw) != action['sha256']:
        raise ValueError('Proposal is stale or path is not allowed')
    old, new = action['old'], action['new']
    # Match the quoted dependency only; never replace arbitrary substrings.
    candidates = [(q + old + q, q + new + q) for q in ('"', "'") if source.count(q + old + q) == 1]
    if len(candidates) != 1:
        raise ValueError('Dependency is not an unambiguous quoted value')
    before, after = candidates[0]
    # Byte replacement preserves BOM and newline conventions.
    changed = raw.replace(before.encode(), after.encode(), 1)
    diff = ''.join(difflib.unified_diff(source.replace('\r\n', '\n').splitlines(True),
                                        changed.decode('utf-8-sig').replace('\r\n', '\n').splitlines(True),
                                        fromfile='a/pyproject.toml', tofile='b/pyproject.toml'))
    return changed, diff


def apply(root, finding, approval, backup_dir):
    if approval != finding['id']:
        raise PermissionError('Explicit approval of the finding ID is required')
    root = Path(root).resolve()
    current = inspect_repository(root)
    fresh = next((f for f in current['findings'] if f['id'] == finding['id']), None)
    if fresh != finding:
        raise ValueError('Repository evidence changed; inspect and review again')
    changed, diff = proposal(root, finding)
    original, _ = safe_read(root, 'pyproject.toml')
    folder = Path(backup_dir).resolve()
    if folder.is_relative_to(root):
        raise ValueError('Backup directory must be outside the inspected repository')
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / ('pyproject.' + digest(original)[:16] + '.toml.bak')
    if backup.exists() and backup.read_bytes() != original:
        raise ValueError('Existing backup does not match')
    if not backup.exists():
        with backup.open('xb') as stream:
            stream.write(original)
    # Recheck immediately before writing. This is not a concurrent filesystem transaction.
    if safe_read(root, 'pyproject.toml')[0] != original:
        raise ValueError('File changed during review')
    (root / 'pyproject.toml').write_bytes(changed)
    return {'status': 'APPLIED', 'approval': approval, 'changed_files': ['pyproject.toml'],
            'before_sha256': digest(original), 'after_sha256': digest(changed),
            'backup': str(backup), 'diff': diff,
            'recovery': 'Compare the backup with the current file; restore only the dependency line if later edits exist. Never git reset.'}
