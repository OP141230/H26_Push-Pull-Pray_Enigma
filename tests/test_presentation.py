import contextlib
import copy
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from enigma import capsule
from enigma.cli import main, workflow
from enigma.presentation import check_status, console, html_report, overview


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repo, self.out = base / 'fixture', base / 'reports'
        self.repo.mkdir()
        (self.repo / 'pyproject.toml').write_text('[project]\ndependencies=["pydantic>=2"]\n')
        (self.repo / 'requirements.txt').write_text('pydantic==1.10.13\n')
        with patch('enigma.cli.shutil.which', return_value=None):
            self.report = workflow(self.repo, self.out)

    def tearDown(self):
        self.temp.cleanup()

    def failure(self):
        return {'command': ['python', '-m', 'pytest'], 'cwd': str(self.repo),
                'status': 'FAIL', 'exit_code': 1, 'label': 'VERIFIED_BY_EXECUTION',
                'output': "E   ImportError: cannot import name 'soft_unicode'\nFAILED tests/test_report.py::test_report\n1 failed, 14 passed in 2s\n"}

    def test_completed_review_does_not_hide_repository_failure(self):
        self.report['baseline'] = [self.failure()]
        self.report['status'] = capsule.aggregate(self.report)
        rows = {label: (state, detail) for label, state, detail in overview(self.report)['rows']}
        self.assertEqual(rows['Enigma review workflow'][0], 'COMPLETED')
        self.assertEqual(rows['Repository baseline'][0], 'FAIL')
        self.assertEqual(rows['Post-change checks'][0], 'NOT_RUN')
        self.assertIn('14 passed', rows['Repository baseline'][1])
        self.assertEqual(self.report['status'], 'FAIL')
        self.assertIn('soft_unicode', console(self.report))
        self.assertIn('AUTOMATION RESULT: FAIL', console(self.report))
        self.assertIn('Repository checks need attention', html_report(self.report))

    def test_skips_blocked_checks_and_missing_models_are_not_success(self):
        rows = {label: state for label, state, _ in overview(self.report)['rows']}
        self.assertEqual(rows['Enigma review workflow'], 'PARTIAL')
        self.assertEqual(rows['Repository baseline'], 'NOT_RUN')
        self.report['inspection']['issues'] = [{'status': 'BLOCKED', 'path': '.', 'reason': 'Missing'}]
        self.assertEqual(overview(self.report)['rows'][0][1], 'BLOCKED')
        self.assertEqual(check_status([{'status': 'PASS'}, {'status': 'SKIPPED'}]), 'PARTIAL')

    def test_hermes_discovery_never_implies_agent_execution(self):
        self.report['hermes'] = {'status': 'NOT_VERIFIED', 'reason': 'Discovered only', 'discovery': {'status': 'PASS'}}
        rows = {label: state for label, state, _ in overview(self.report)['rows']}
        self.assertEqual(rows['Hermes discovery'], 'PASS')
        self.assertEqual(rows['Hermes agent workflow'], 'NOT_VERIFIED')

    def test_html_escapes_model_source_and_logs(self):
        report = copy.deepcopy(self.report)
        finding = report['inspection']['findings'][0]
        payload = '<script>alert("x")</script><img src="https://example.invalid">'
        report['model'].update(status='PASS', label='AI_RECOMMENDATION', model='fixture', recommendation={
            'finding_id': finding['id'], 'summary': payload, 'recommendation': payload,
            'evidence_refs': finding['evidence_refs']})
        report['baseline'] = [self.failure()]
        report['baseline'][0]['output'] += payload
        report['status'] = capsule.aggregate(report)
        text = html_report(report)
        self.assertNotIn('<script>', text)
        self.assertNotIn('<img ', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertIn("default-src 'none'", text)
        class Tags(HTMLParser):
            def __init__(self):
                super().__init__()
                self.external = []
            def handle_starttag(self, tag, attrs):
                self.external.extend(v for k, v in attrs if k in {'src', 'href'} and v.startswith('http'))
        parser = Tags()
        parser.feed(text)
        self.assertFalse(parser.external)

    def test_show_renders_saved_run_without_execution(self):
        path = self.out / 'dependency_exit_capsule.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        with patch('enigma.cli.workflow', side_effect=AssertionError('Must not run workflow')), contextlib.redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(main(['show', str(path), '--output', str(self.out)]), 0)
        self.assertIn('Saved run only', captured.getvalue())
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), original)
        self.assertEqual((self.out / 'dependency_exit_capsule.html').read_text(encoding='utf-8'), html_report(original))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['validate', str(path), '--html', str(self.out / 'dependency_exit_capsule.html')]), 0)
