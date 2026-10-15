"""Bounded evolution of LinkWatch tools/dependency_evidence.py (MIT).

Retains manifest and AST evidence collection; never infers unused dependencies.
Only the narrow Pydantic manifest conflict has an automated maintenance action.
"""
import ast
import hashlib
import os
from pathlib import Path
import re
import tomllib

MAX_FILE = 128 * 1024
MAX_FILES = 300
SKIP_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', 'build',
             'dist', 'node_modules', 'models', 'reports', '.cache', '.hermes'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def redact(text):
    text = re.sub(r'(https?://)[^/\s@]+@', r'\1[REDACTED]@', str(text))
    text = re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[REDACTED]', text)
    text = re.sub(r'(?i)\b(token|password|secret|api[_-]?key)(\s*[=:]\s*)[^\s,;]+',
                  r'\1\2[REDACTED]', text)
    text = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})\b', '[REDACTED]', text)
    text = text.replace(str(Path.home()), '~')
    return text


def safe_read(root, relative):
    path = root / relative
    # Reject symlinks/junctions, including parents, before reading or modifying.
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink() or parent.is_junction():
            raise ValueError('linked paths are not supported')
    if not path.resolve().is_relative_to(root):
        raise ValueError('path escapes repository')
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise ValueError('file exceeds 128 KiB bound')
    return raw, raw.decode('utf-8-sig')


def inspect_repository(root):
    root = Path(root).resolve()
    result = {'label': 'OBSERVED', 'dependencies': [], 'imports': {}, 'evidence': [],
              'findings': [], 'issues': [], 'requires_python': None, 'hashes': {}}
    if not root.is_dir():
        result['issues'].append({'path': '.', 'status': 'BLOCKED', 'reason': 'Repository directory missing'})
        return result
    texts = {}

    def read(relative, required=False):
        try:
            raw, source = safe_read(root, relative)
            result['hashes'][relative] = digest(raw)
            texts[relative] = source
            return source
        except (OSError, UnicodeError, ValueError) as exc:
            if required or (root / relative).exists():
                result['issues'].append({'path': relative, 'status': 'NOT_VERIFIED', 'reason': redact(exc)[:300]})
            return None

    def evidence(path, line, text):
        item = {'id': f'E{len(result["evidence"]) + 1}', 'path': path, 'line': line,
                'text': redact(text)[:300], 'label': 'OBSERVED'}
        result['evidence'].append(item)
        return item['id']

    source = read('pyproject.toml', required=True)
    project = {}
    if source is not None:
        try:
            project = tomllib.loads(source).get('project', {})
            if not isinstance(project, dict):
                raise ValueError('project must be a table')
            floor = project.get('requires-python')
            if floor is not None and not isinstance(floor, str):
                raise ValueError('requires-python must be a string')
            result['requires_python'] = floor
            deps = project.get('dependencies', [])
            if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
                raise ValueError('dependencies must be a list of strings')
            for dep in deps[:100]:
                line = next((i for i, s in enumerate(source.splitlines(), 1) if dep in s), 1)
                ref = evidence('pyproject.toml', line, dep)
                result['dependencies'].append({'declaration': redact(dep), 'evidence': ref})
            if len(deps) > 100 or project.get('dynamic') or project.get('optional-dependencies'):
                result['issues'].append({'path': 'pyproject.toml', 'status': 'NOT_VERIFIED',
                                         'reason': 'Optional/dynamic dependencies or declarations beyond 100 are outside scope'})
        except (ValueError, TypeError) as exc:
            result['issues'].append({'path': 'pyproject.toml', 'status': 'BLOCKED', 'reason': redact(exc)[:300]})
            project = {}
    req = read('requirements.txt', required=True)
    if req is not None:
        for i, line in enumerate(req.splitlines()[:300], 1):
            value = line.strip()
            if value and not value.startswith('#'):
                ref = evidence('requirements.txt', i, value)
                result['dependencies'].append({'declaration': redact(value), 'evidence': ref})
                if value.startswith('-') or '://' in value or ';' in value or '[' in value:
                    result['issues'].append({'path': 'requirements.txt', 'status': 'NOT_VERIFIED',
                                             'reason': f'Complex declaration at line {i} recorded, not resolved'})
        if len(req.splitlines()) > 300:
            result['issues'].append({'path': 'requirements.txt', 'status': 'NOT_VERIFIED', 'reason': '300 line limit reached'})

    count = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')
                         and not (Path(directory) / d).is_symlink() and not (Path(directory) / d).is_junction())
        for name in sorted(files):
            if not name.endswith('.py'):
                continue
            count += 1
            if count > MAX_FILES:
                break
            relative = (Path(directory) / name).relative_to(root).as_posix()
            text = read(relative)
            if text is None:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError as exc:
                result['issues'].append({'path': relative, 'status': 'NOT_VERIFIED', 'reason': f'Syntax error at line {exc.lineno}'})
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split('.')[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module.split('.')[0]]
                for module in names:
                    result['imports'].setdefault(module, [])
                    if len(result['imports'][module]) < 10:
                        result['imports'][module].append({'path': relative, 'line': node.lineno})
        if count > MAX_FILES:
            result['issues'].append({'path': '.', 'status': 'NOT_VERIFIED', 'reason': '300 Python file limit reached'})
            break

    # A deliberately narrow rule; not a general PEP 440 resolver.
    deps = project.get('dependencies', [])
    if isinstance(deps, list) and deps.count('pydantic>=2') == 1 and req:
        match = re.search(r'^pydantic==(1\.\d+\.\d+)\s*$', req, re.M)
        if match:
            old, new = 'pydantic>=2', 'pydantic==' + match.group(1)
            refs = [e['id'] for e in result['evidence'] if e['text'] in (old, new)]
            config = texts.get('linkwatch/config.py', '')
            for i, line in enumerate(config.splitlines(), 1):
                if 'anystr_strip_whitespace' in line or 'from pydantic import' in line:
                    refs.append(evidence('linkwatch/config.py', i, line.strip()))
            result['findings'].append({
                'id': 'ENIGMA-PYDANTIC-001', 'label': 'OBSERVED', 'status': 'REVIEW_REQUIRED',
                'description': 'Installation paths declare incompatible Pydantic major versions.',
                'evidence_refs': refs, 'affected_files': ['pyproject.toml', 'requirements.txt'],
                'expected_outcome': 'Both installation paths select the existing requirements.txt Pydantic version.',
                'uncertainty': 'This aligns declarations only; it does not prove fresh installation or Python 3.13 compatibility.',
                'proposed_action': {'path': 'pyproject.toml', 'old': old, 'new': new,
                                    'sha256': result['hashes']['pyproject.toml']}})
    result['limitations'] = ['No unused-dependency conclusions; alternate imports, plugins and dynamic loading are not resolved.',
                            'Only pyproject.toml and requirements.txt declarations are parsed; other manifest formats are outside scope.',
                            'No package registry, vulnerability scanning, dependency installation, or compatibility solver.']
    return result
