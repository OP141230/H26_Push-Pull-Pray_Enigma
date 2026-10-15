import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

from . import capsule
from .evidence import inspect_repository, redact
from .maintenance import apply, proposal
from .model import recommend
from .runner import run_command


def provenance(root):
    result = {'path': redact(root), 'branch': None, 'commit': None, 'initial_status': None,
              'final_status': None, 'remotes': None}
    for key, args in [('branch', ['branch', '--show-current']), ('commit', ['rev-parse', 'HEAD']),
                      ('initial_status', ['status', '--short']), ('remotes', ['remote', '-v'])]:
        check = run_command(['git', '-C', str(root), *args], root, timeout=10)
        result[key] = check['output'].strip() if check['status'] == 'PASS' else 'NOT_VERIFIED: ' + check['output'][:300]
    result['final_status'] = result['initial_status']
    return result


def verify(root, interpreter, temp_root):
    if interpreter is None:
        return [{'command': [], 'cwd': redact(root), 'exit_code': None, 'status': 'SKIPPED',
                 'label': 'NOT_VERIFIED', 'output': 'No --check-python supplied; no tests run'}]
    version = run_command([interpreter, '--version'], root, timeout=10)
    if version['status'] != 'PASS':
        return [version]
    if not version['output'].startswith(('Python 3.12.', 'Python 3.13.')):
        return [{'command': [interpreter, '--version'], 'cwd': redact(root), 'exit_code': None,
                 'status': 'BLOCKED', 'label': 'BLOCKED', 'output': 'Verification requires Python 3.12 or 3.13'}]
    # Randomized workspace-local temp directories avoid overwriting other pytest runs.
    import uuid
    scratch = Path(temp_root).resolve() / ('pytest-' + uuid.uuid4().hex[:12])
    scratch.parent.mkdir(parents=True, exist_ok=True)
    command = [interpreter, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--tb=short', '--basetemp=' + str(scratch)]
    check = run_command(command, root, timeout=90, limit=10000)
    check['interpreter'] = {'executable': redact(interpreter), 'version': version['output'].strip()}
    check['warning'] = 'Tests execute repository code; run only against a trusted checkout.'
    return [check]


def workflow(root, output, interpreter=None, model=None, approval=None, expected_hash=None, do_apply=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError('Reports must be outside and separate from the target repository')
    inspection = inspect_repository(root)
    repo = provenance(root) if root.is_dir() else {'path': redact(root), 'branch': None, 'commit': None,
                                                   'initial_status': None, 'final_status': None, 'remotes': None}
    baseline = verify(root, interpreter, output.parent / 'work') if root.is_dir() else []
    model_result = recommend(inspection, model)
    hermes_exe = shutil.which('hermes')
    hermes = {'status': 'BLOCKED', 'reason': 'Hermes executable not found; discovery and invocation unavailable'}
    if hermes_exe:
        check = run_command([hermes_exe, 'skills', 'list'], root, timeout=15)
        hermes = {'status': 'NOT_VERIFIED', 'reason': 'Discovery attempted; actual skill invocation not demonstrated', 'discovery': check}
    report = {'schema_version': 1, 'scope': 'Pydantic declaration consistency in the existing checkout; full repository tests when requested.',
              'created_at': datetime.now(timezone.utc).isoformat(), 'repository': repo, 'inspection': inspection,
              'model': model_result, 'hermes': hermes, 'baseline': baseline, 'post_change': [],
              'change': {'status': 'NOT_APPLIED' if inspection['findings'] else 'NO_ACTION', 'approval': None, 'changed_files': []},
              'python_coverage': {'3.12': 'NOT_VERIFIED', '3.13': 'NOT_VERIFIED'},
              'limitations': inspection['limitations'] + ['Handbook unavailable: event eligibility and submission compliance NOT_VERIFIED.',
                  'Hermes invocation and model eligibility require independent evidence.',
                  'Existing worktree edits predate this run; no clean historical baseline is inferred.'],
              'next_steps': ['Review the finding and proposed.patch before approving.',
                             'Resolve pre-existing baseline failures separately; no automatic unrelated repairs.',
                             'Provide handbook, install Hermes and an eligible local Gemma model, then rerun.',
                             'Test using Python 3.13 before claiming that compatibility.']}
    output.mkdir(parents=True, exist_ok=True)
    finding = inspection['findings'][0] if inspection['findings'] else None
    if finding:
        try:
            _, diff = proposal(root, finding)
            (output / 'proposed.patch').write_text(diff, encoding='utf-8', newline='\n')
            report['change']['proposed_diff'] = diff
            report['change']['review_sha256'] = finding['proposed_action']['sha256']
            if do_apply:
                if expected_hash != finding['proposed_action']['sha256']:
                    raise ValueError('--expected-sha256 must match the previously reviewed file hash')
                if not baseline or any(c['status'] != 'PASS' for c in baseline):
                    raise ValueError('Apply blocked until the requested baseline passes')
                report['change'] = apply(root, finding, approval, output / 'backups')
                report['change']['backup'] = redact(report['change']['backup'])
                report['post_change'] = verify(root, interpreter, output.parent / 'work')
                report['repository']['final_status'] = provenance(root)['initial_status']
        except (OSError, ValueError, PermissionError) as exc:
            report['change'].update(status='FAILED' if do_apply else 'NOT_APPLIED', reason=redact(exc), approval=approval)
    elif do_apply:
        report['change']['reason'] = 'No current finding; nothing changed'
    for c in report['baseline'] + report['post_change']:
        version = c.get('interpreter', {}).get('version', '')
        for minor in ('3.12', '3.13'):
            if version.startswith('Python ' + minor + '.'):
                report['python_coverage'][minor] = 'VERIFIED_BY_EXECUTION: ' + version + '; repository suite ' + c['status']
    report['status'] = capsule.aggregate(report)
    capsule.write(report, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='ENIGMA — evidence-driven repository maintenance')
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='Inspect, recommend, review, optionally apply, verify and emit capsules')
    run.add_argument('repository', type=Path)
    run.add_argument('--output', type=Path, default=Path('reports'))
    run.add_argument('--check-python', help='Interpreter for trusted repository pytest checks')
    run.add_argument('--model', help='Already installed local Gemma tag, e.g. gemma3:1b')
    run.add_argument('--apply', action='store_true')
    run.add_argument('--approve', help='Exact reviewed finding ID; supply only after explicit human approval')
    run.add_argument('--expected-sha256', help='Hash from the previously reviewed capsule')
    check = commands.add_parser('validate', help='Validate capsule structure, references, statuses and Markdown consistency')
    check.add_argument('capsule', type=Path)
    check.add_argument('--markdown', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            report = json.loads(args.capsule.read_text(encoding='utf-8'))
            capsule.validate(report)
            if args.markdown and args.markdown.read_text(encoding='utf-8') != capsule.markdown(report):
                raise ValueError('Markdown differs from canonical data')
            print('VERIFIED_BY_EXECUTION: capsule validation passed')
            return 0
        if (args.approve or args.expected_sha256) and not args.apply:
            parser.error('--approve and --expected-sha256 require --apply')
        if args.apply and (not args.approve or not args.expected_sha256 or not args.check_python):
            parser.error('--apply requires --approve, --expected-sha256 and --check-python')
        report = workflow(args.repository, args.output, args.check_python, args.model, args.approve,
                          args.expected_sha256, args.apply)
        print('ENIGMA: ' + report['status'])
        for f in report['inspection']['findings']:
            print(f['label'] + ': ' + f['id'] + ' — ' + f['description'])
        print('Model: ' + report['model']['status'] + ' — ' + report['model']['reason'])
        print('Change: ' + report['change']['status'])
        print('Capsules: ' + str(args.output.resolve()))
        return 1 if report['status'] == 'FAIL' else 2 if report['status'] == 'BLOCKED' else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print('BLOCKED: ' + redact(exc), file=sys.stderr)
        return 2
