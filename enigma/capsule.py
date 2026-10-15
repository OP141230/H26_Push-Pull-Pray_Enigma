"""Canonical report, focused structural/semantic validator and Markdown view."""
import hashlib
import json
from pathlib import Path

LABELS = {'OBSERVED', 'AI_RECOMMENDATION', 'VERIFIED_BY_EXECUTION', 'NOT_VERIFIED', 'BLOCKED'}
CHECKS = {'PASS', 'FAIL', 'TIMEOUT', 'SKIPPED', 'BLOCKED'}


def aggregate(report):
    checks = report['baseline'] + report['post_change']
    if any(c['status'] in {'FAIL', 'TIMEOUT'} for c in checks) or report['change']['status'] == 'FAILED':
        return 'FAIL'
    if any(i['status'] == 'BLOCKED' for i in report['inspection']['issues']):
        return 'BLOCKED'
    if any(c['status'] == 'BLOCKED' for c in checks):
        return 'BLOCKED'
    if (not checks or any(c['status'] == 'SKIPPED' for c in checks)
            or report['inspection']['issues'] or report['model']['status'] != 'PASS'
            or report['hermes']['status'] != 'PASS' or report['limitations']):
        return 'PARTIAL'
    return 'PASS'


def require(condition, message):
    if not condition:
        raise ValueError('Invalid capsule: ' + message)


def validate(report):
    require(isinstance(report, dict), 'root must be an object')
    required = {'schema_version', 'scope', 'created_at', 'repository', 'inspection', 'model', 'hermes',
                'change', 'baseline', 'post_change', 'python_coverage', 'limitations', 'next_steps', 'status'}
    require(required <= report.keys(), 'missing top-level fields')
    require(report['schema_version'] == 1, 'unsupported schema version')
    for key in ('scope', 'created_at'):
        require(isinstance(report[key], str) and bool(report[key]), key)
    for key in ('repository', 'inspection', 'model', 'hermes', 'change', 'python_coverage'):
        require(isinstance(report[key], dict), key + ' must be an object')
    for key in ('baseline', 'post_change', 'limitations', 'next_steps'):
        require(isinstance(report[key], list), key + ' must be an array')
    for key in ('limitations', 'next_steps'):
        require(all(isinstance(x, str) for x in report[key]), key + ' must contain strings')
    repo = report['repository']
    require({'path', 'branch', 'commit', 'initial_status', 'final_status', 'remotes'} <= repo.keys(), 'repository provenance')
    inspection = report['inspection']
    require({'evidence', 'findings', 'issues', 'hashes', 'label'} <= inspection.keys(), 'inspection fields')
    require(inspection['label'] == 'OBSERVED', 'inspection label')
    for key in ('evidence', 'findings', 'issues'):
        require(isinstance(inspection[key], list), 'inspection ' + key)
    ids = set()
    for e in inspection['evidence']:
        require(isinstance(e, dict) and {'id', 'path', 'line', 'text', 'label'} <= e.keys(), 'evidence fields')
        require(isinstance(e['id'], str) and e['id'] not in ids, 'duplicate evidence ID')
        require(type(e['line']) is int and e['line'] > 0 and e['label'] == 'OBSERVED', 'evidence location/label')
        require(isinstance(e['path'], str) and isinstance(e['text'], str), 'evidence types')
        ids.add(e['id'])
    finding_ids = set()
    for f in inspection['findings']:
        require(isinstance(f, dict) and {'id', 'description', 'evidence_refs', 'label', 'proposed_action',
                                       'affected_files', 'uncertainty', 'expected_outcome'} <= f.keys(), 'finding fields')
        require(isinstance(f['id'], str) and f['id'] not in finding_ids, 'finding ID')
        finding_ids.add(f['id'])
        require(f['label'] == 'OBSERVED' and isinstance(f['evidence_refs'], list) and bool(f['evidence_refs']), 'finding evidence')
        require(all(isinstance(r, str) and r in ids for r in f['evidence_refs']), 'dangling evidence reference')
    for item in inspection['issues']:
        require(isinstance(item, dict) and {'path', 'status', 'reason'} <= item.keys(), 'inspection issue')
        require(item['status'] in {'NOT_VERIFIED', 'BLOCKED'}, 'issue status')
    for key in ('model', 'hermes'):
        item = report[key]
        require({'status', 'reason'} <= item.keys() and item['status'] in {'PASS', 'NOT_VERIFIED', 'BLOCKED'}, key + ' status')
    model = report['model']
    require(model.get('label') in LABELS and 'recommendation' in model, 'model fields')
    if model['status'] == 'PASS':
        from .model import validate_recommendation
        require(model['label'] == 'AI_RECOMMENDATION', 'successful model label')
        require(isinstance(model['recommendation'], dict), 'model recommendation')
        finding = next((f for f in inspection['findings'] if f['id'] == model['recommendation'].get('finding_id')), None)
        require(finding is not None, 'model finding reference')
        validate_recommendation(model['recommendation'], finding, inspection['evidence'])
    else:
        require(model['recommendation'] is None, 'unavailable model cannot contain inference')
    for check in report['baseline'] + report['post_change']:
        require(isinstance(check, dict) and {'command', 'cwd', 'exit_code', 'status', 'label', 'output'} <= check.keys(), 'check fields')
        require(isinstance(check['command'], list) and all(isinstance(a, str) for a in check['command']), 'command argv')
        require(check['status'] in CHECKS and check['label'] in LABELS, 'check status/label')
        require(check['exit_code'] is None or type(check['exit_code']) is int, 'exit code type')
        if check['status'] == 'PASS':
            require(check['exit_code'] == 0 and check['label'] == 'VERIFIED_BY_EXECUTION', 'pass without execution')
        if check['status'] == 'FAIL':
            require(check['exit_code'] not in (None, 0), 'failure without nonzero exit')
    change = report['change']
    require({'status', 'approval', 'changed_files'} <= change.keys(), 'change fields')
    require(change['status'] in {'NOT_APPLIED', 'APPLIED', 'FAILED', 'NO_ACTION'}, 'change status')
    require(isinstance(change['changed_files'], list), 'changed files')
    if change['status'] == 'APPLIED':
        require(change['approval'] in finding_ids and change['changed_files'] == ['pyproject.toml'], 'unapproved change')
        require(bool(report['post_change']), 'applied change lacks post verification')
    else:
        require(not change['changed_files'], 'unapplied change has changed files')
    require(set(report['python_coverage']) == {'3.12', '3.13'}, 'Python coverage')
    require(all(isinstance(v, str) for v in report['python_coverage'].values()), 'Python coverage types')
    require(report['status'] == aggregate(report), 'incorrect overall aggregation')
    return True


def canonical(report):
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + '\n'


def markdown(report):
    validate(report)
    from .presentation import markdown_summary
    payload = canonical(report)
    checksum = hashlib.sha256(payload.encode()).hexdigest()
    lines = ['# ENIGMA — Dependency Exit Capsule', '', '**Overall status: ' + report['status'] + '**',
             '', report['scope'], '', 'JSON SHA-256: `' + checksum + '`', '',
             'The complete canonical data is embedded below; the JSON and Markdown contain identical claims.', '',
             markdown_summary(report), '', '## Findings', '']
    for finding in report['inspection']['findings']:
        lines.extend(['- **' + finding['id'] + ' · OBSERVED**: ' + finding['description'],
                      '  Expected: ' + finding['expected_outcome'], '  Uncertainty: ' + finding['uncertainty']])
    if not report['inspection']['findings']:
        lines.append('No actionable finding established by the implemented rule.')
    model = report['model']
    lines.extend(['', '## Gemma recommendation', ''])
    if model['status'] == 'PASS':
        rec = model['recommendation']
        lines.extend(['**AI_RECOMMENDATION — actual local model output, not a verified fix.**', '',
                      'Model: `' + str(model.get('model')) + '`', '',
                      '**Summary:** ' + rec['summary'], '',
                      '**Suggested action:** ' + rec['recommendation'], ''])
        if 'rationale' in rec:
            lines.extend(['**Model rationale:** ' + rec['rationale'], '', '**Model-identified risks:**', ''])
            lines.extend('- ' + item for item in rec['risks'])
            lines.extend(['', '**Model-proposed verification (not executed by the model):**', ''])
            lines.extend(str(i) + '. ' + item for i, item in enumerate(rec['verification_steps'], 1))
        lines.extend(['', '**Cited repository evidence:**', ''])
        for item in report['inspection']['evidence']:
            if item['id'] in rec['evidence_refs']:
                lines.append('- ' + item['id'] + ' — `' + item['path'] + ':' + str(item['line']) + '` — `' + item['text'] + '`')
        lines.extend(['', 'The finding and executable patch are deterministic Enigma logic. '
                      'The model independently reviews supplied evidence; its text does not control edits or commands.'])
    else:
        lines.append('No model recommendation available: ' + model['status'] + ' — ' + model['reason'])
    lines.extend(['', '## Deterministic patch for separate review', '',
                  'This patch is produced by Enigma, not by Gemma. It may differ from the model suggestion. '
                  'Review both before approving; the apply command only supports this displayed patch.', '',
                  'Change status: **' + report['change']['status'] + '**', ''])
    if report['change'].get('proposed_diff'):
        lines.extend(['````diff', report['change']['proposed_diff'].rstrip(), '````'])
    lines.extend(['', '## Execution', ''])
    for stage in ('baseline', 'post_change'):
        for check in report[stage]:
            lines.append('- ' + stage + ': **' + check['status'] + '** — `' + ' '.join(check['command']) + '`')
    lines.extend(['', '## Integrations', '', '- Model: ' + report['model']['status'] + ' — ' + report['model']['reason'],
                  '- Hermes: ' + report['hermes']['status'] + ' — ' + report['hermes']['reason'],
                  '', '## Canonical report', '', '````json', payload.rstrip(), '````', ''])
    return '\n'.join(lines)


def write(report, directory):
    validate(report)
    from .presentation import html_report
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'dependency_exit_capsule.json').write_text(canonical(report), encoding='utf-8', newline='\n')
    (directory / 'dependency_exit_capsule.md').write_text(markdown(report), encoding='utf-8', newline='\n')
    (directory / 'dependency_exit_capsule.html').write_text(html_report(report), encoding='utf-8', newline='\n')
