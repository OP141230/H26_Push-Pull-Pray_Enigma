"""Human-facing views derived from a validated capsule; no inference or execution."""
from html import escape
import json
import re


def check_status(checks):
    statuses = {c['status'] for c in checks}
    for status in ('FAIL', 'TIMEOUT', 'BLOCKED'):
        if status in statuses:
            return status
    if not statuses or statuses == {'SKIPPED'}:
        return 'NOT_RUN'
    return 'PARTIAL' if 'SKIPPED' in statuses else 'PASS'


def test_summary(checks):
    summaries = []
    for check in checks:
        for line in reversed(check['output'].splitlines()):
            counts = re.findall(r'\b\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed)\b', line)
            if counts:
                summaries.append(', '.join(counts))
                break
    return '; '.join(summaries) or 'See recorded command outcomes'


def overview(report):
    baseline, post = check_status(report['baseline']), check_status(report['post_change'])
    workflow = 'COMPLETED'
    if report['change']['status'] == 'FAILED':
        workflow = 'FAILED'
    elif any(i['status'] == 'BLOCKED' for i in report['inspection']['issues']) or 'BLOCKED' in (baseline, post):
        workflow = 'BLOCKED'
    elif (report['inspection']['issues'] or baseline in {'NOT_RUN', 'PARTIAL', 'TIMEOUT'}
          or post == 'TIMEOUT' or (report['model'].get('model') and report['model']['status'] != 'PASS')):
        workflow = 'PARTIAL'
    model = report['model']
    change = report['change']
    if change['status'] == 'APPLIED':
        approval = 'RECORDED'
    elif change['status'] == 'NO_ACTION':
        approval = 'NOT_NEEDED'
    elif change.get('approval'):
        approval = 'NOT_APPLIED'
    else:
        approval = 'NOT_RECORDED'
    discovery = report['hermes'].get('discovery', {}).get('status', 'NOT_VERIFIED')
    latest = post if report['post_change'] else baseline
    if workflow in {'BLOCKED', 'FAILED'}:
        headline = 'Review needs attention'
    elif latest in {'FAIL', 'TIMEOUT', 'BLOCKED'}:
        headline = 'Review ready. Repository checks need attention.'
    elif latest in {'NOT_RUN', 'PARTIAL'}:
        headline = 'Review ready. Verification is incomplete.'
    else:
        headline = 'Review ready for a maintainer decision.'
    rows = [
        ('Enigma review workflow', workflow, 'Evidence and recorded outcomes assembled; this is not a repository health verdict.'),
        ('Repository baseline', baseline, test_summary(report['baseline'])),
        ('Gemma inference', 'GENERATED' if model['status'] == 'PASS' else model['status'],
         'Structure and evidence references validated; correctness still requires review.' if model['status'] == 'PASS' else model['reason']),
        ('Approval', approval, 'Explicit approval is required before modifying the target repository.'),
        ('Changes', change['status'], ', '.join(change['changed_files']) or 'No target files changed by this run.'),
        ('Post-change checks', post, test_summary(report['post_change']) if report['post_change'] else 'No post-change verification was performed.'),
        ('Hermes discovery', discovery, 'CLI discovery only; listing skills does not demonstrate agent orchestration.'),
        ('Hermes agent workflow', 'NOT_VERIFIED', 'This capsule does not record a Hermes agent session.'),
    ]
    failures = []
    for stage in ('baseline', 'post_change'):
        for check in report[stage]:
            if check['status'] not in {'FAIL', 'TIMEOUT', 'BLOCKED'}:
                continue
            for line in check['output'].splitlines():
                stripped = line.strip()
                if stripped.startswith(('FAILED ', 'ERROR ', 'E   ')):
                    failures.append(stage + ': ' + stripped[:600])
            if not check['output'].strip():
                failures.append(stage + ': ' + check['status'] + '; no captured output')
    return {'headline': headline, 'rows': rows, 'failures': failures[:12]}


def console(report):
    view = overview(report)
    lines = ['\nENIGMA | Maintenance review', '=' * 72, view['headline'],
             'Recorded run: ' + report['created_at'], '']
    for label, state, detail in view['rows']:
        lines.append(f'{label:<26} {state}')
        if label == 'Repository baseline':
            lines.append('  ' + detail)
    lines.extend(['', 'AUTOMATION RESULT: ' + report['status'] + ' (existing exit-code policy retained)'])
    if view['failures']:
        lines.extend(['', 'REPOSITORY CHECK EVIDENCE', *('  ' + s for s in view['failures'][:3])])
    for finding in report['inspection']['findings']:
        lines.extend(['', 'OBSERVED | ' + finding['id'], '  ' + finding['description']])
    if report['model']['status'] == 'PASS':
        rec = report['model']['recommendation']
        lines.extend(['', 'GEMMA | AI_RECOMMENDATION', '  ' + rec['recommendation']])
        if rec.get('rationale'):
            lines.append('  Why: ' + rec['rationale'])
    lines.extend(['', 'REVIEW BOUNDARY', '  Compare the model suggestion with the deterministic patch. They may differ.',
                  '  No model-generated command is executed. A Git push is not required.', ''])
    return '\n'.join(lines)


def markdown_summary(report):
    view = overview(report)
    lines = ['## Review at a glance', '', '**' + view['headline'] + '**', '',
             '| Area | State | What it means |', '|---|---|---|']
    for row in view['rows']:
        lines.append('| ' + ' | '.join(str(s).replace('|', '\\|').replace('\n', ' ') for s in row) + ' |')
    lines.extend(['', 'Automation result remains **' + report['status'] + '**. '
                  'Completing the review does not mean the repository passed its checks.', ''])
    if view['failures']:
        lines.extend(['### Recorded repository failures', ''])
        lines.extend('- `' + line.replace('`', "'") + '`' for line in view['failures'])
        lines.append('')
    return '\n'.join(lines)


def html_report(report):
    view = overview(report)
    e = lambda value: escape(str(value), quote=True)
    def badge(state):
        tone = 'good' if state in {'COMPLETED', 'PASS', 'GENERATED', 'RECORDED'} else 'bad' if state in {'FAIL', 'FAILED', 'BLOCKED', 'TIMEOUT'} else 'pending'
        return '<span class="badge ' + tone + '">' + e(state.replace('_', ' ')) + '</span>'
    cards = ''.join('<article class="card"><h3>' + e(label) + '</h3>' + badge(state) + '<p>' + e(detail) + '</p></article>'
                    for label, state, detail in view['rows'])
    findings = ''.join('<article class="finding"><span class="eyebrow">OBSERVED · ' + e(f['id']) + '</span><h3>'
                       + e(f['description']) + '</h3><p>' + e(f['uncertainty']) + '</p></article>' for f in report['inspection']['findings'])
    if not findings:
        findings = '<p>No actionable finding was established by the implemented rule.</p>'
    def bullets(items):
        return '<ul>' + ''.join('<li>' + e(item) + '</li>' for item in items) + '</ul>'
    model = report['model']
    if model['status'] == 'PASS':
        rec = model['recommendation']
        model_body = ('<p class="eyebrow">AI_RECOMMENDATION · ' + e(model.get('model')) + '</p><h3>'
                      + e(rec['recommendation']) + '</h3><p>' + e(rec.get('rationale', rec['summary'])) + '</p>')
        if 'risks' in rec:
            model_body += '<div class="columns"><div><h4>Model-identified risks</h4>' + bullets(rec['risks']) + '</div><div><h4>Suggested checks · not executed by the model</h4>' + bullets(rec['verification_steps']) + '</div></div>'
        evidence = [f"{item['id']} · {item['path']}:{item['line']} — {item['text']}" for item in report['inspection']['evidence'] if item['id'] in rec['evidence_refs']]
        model_body += '<h4>Cited repository evidence</h4>' + bullets(evidence)
    else:
        model_body = '<p>' + badge(model['status']) + ' ' + e(model['reason']) + '</p>'
    failures = '<section class="attention"><h2>Repository checks need attention</h2>' + bullets(view['failures']) + '<p>These are captured target-repository outcomes. They are not an Enigma test-suite result.</p></section>' if view['failures'] else ''
    logs = ''
    for stage in ('baseline', 'post_change'):
        for check in report[stage]:
            logs += '<details><summary>' + e(stage.replace('_', ' ')) + ' · ' + e(check['status']) + '</summary><p>Working directory: ' + e(check['cwd']) + '</p><pre>' + e(json.dumps(check['command'], ensure_ascii=False)) + '</pre><pre>' + e(check['output']) + '</pre></details>'
    patch = report['change'].get('proposed_diff') or report['change'].get('diff') or 'No executable patch recorded.'
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Enigma · Maintenance review</title><style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#1b3040;background:#f3f6f8;line-height:1.6}*{box-sizing:border-box}body{margin:0}header{background:#102b3b;color:#fff;padding:42px max(24px,calc((100vw - 1120px)/2))}header .brand{letter-spacing:.22em;font-weight:700;color:#66d8c8}h1{font-size:clamp(28px,4vw,44px);line-height:1.18;max-width:850px;margin:16px 0}header p{color:#bfd0db}.meta{font-size:13px;overflow-wrap:anywhere}main{max-width:1168px;margin:auto;padding:28px 24px 48px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card,section{background:#fff;border:1px solid #dbe4e9;border-radius:12px;padding:22px}.card h3{font-size:13px;margin:0 0 12px;color:#516574}.card p{font-size:12px;margin-bottom:0}.badge{display:inline-block;font-size:11px;letter-spacing:.04em;font-weight:700;padding:4px 9px;border-radius:5px}.good{background:#d9f3eb;color:#12604f}.bad{background:#ffe1df;color:#982f2d}.pending{background:#fff0cc;color:#725214}.context{border-left:4px solid #cc8b26;padding-left:16px;margin:22px 0}section{margin-top:20px}h2{font-size:21px;margin:0 0 14px}h3{line-height:1.4}h4{font-size:14px}.eyebrow{font-size:11px;font-weight:700;color:#187e70;letter-spacing:.07em}.finding+.finding{border-top:1px solid #ddd;padding-top:16px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:28px}li{margin:8px 0;overflow-wrap:anywhere}ul{padding-left:22px}.attention{border-left:4px solid #b64338;background:#fff9f7}pre{background:#f4f6f8;padding:18px;border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 Consolas,monospace}summary{cursor:pointer;padding:12px 0;font-weight:600}details{border-top:1px solid #dbe4e9}a{color:#12695d;font-weight:600}footer{font-size:12px;color:#526674;margin-top:28px}@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.grid,.columns{grid-template-columns:1fr}}@media print{header{background:white;color:#102b3b;padding:20px}header p{color:#526674}main{padding:0}.card,section{break-inside:avoid}.grid{grid-template-columns:1fr 1fr}details{display:block}}
</style></head><body><header><div class="brand">ENIGMA / MAINTENANCE REVIEW</div><h1>''' + e(view['headline']) + '''</h1><p>Evidence first. Model advice second. Maintainer approval before edits.</p><div class="meta">Recorded run: ''' + e(report['created_at']) + ' · Repository: ' + e(report['repository']['path']) + '''</div></header><main><div class="grid">''' + cards + '''</div><p class="context">Automation result: ''' + badge(report['status']) + ''' — retained for scripts and CI. A completed review does not mean repository checks passed. No Git push is needed to complete a review.</p>''' + failures + '<section><h2>01 / Observed finding</h2>' + findings + '</section><section><h2>02 / Gemma recommendation</h2>' + model_body + '''<p class="context">Actual model output, not a verified fix. Structure and citations are checked; factual claims and migration safety still need human review.</p></section><section><h2>03 / Deterministic patch · separate review</h2><p>The patch below is generated by Enigma. It may differ from Gemma's recommendation. The apply command only supports this patch and requires explicit approval plus a passing baseline.</p><pre>''' + e(patch) + '''</pre></section><section><h2>04 / Execution evidence</h2>''' + logs + '''</section><section><h2>05 / Scope and remaining proof</h2>''' + bullets(report['limitations']) + '<h4>Python coverage</h4>' + bullets(k + ': ' + v for k, v in report['python_coverage'].items()) + '''<p>Hermes skill discovery and Hermes agent execution are different claims. This report does not attest an external agent session.</p></section><footer>Generated from the validated canonical capsule. No external assets, scripts or network requests.<br><a href="dependency_exit_capsule.json">Canonical JSON</a> · <a href="dependency_exit_capsule.md">Markdown report</a></footer></main></body></html>'''
