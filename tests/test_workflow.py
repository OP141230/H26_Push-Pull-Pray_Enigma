import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from enigma import capsule
from enigma.cli import main, workflow
from enigma.evidence import inspect_repository, MAX_FILE, redact
from enigma.maintenance import apply, proposal
from enigma.model import recommend, validate_recommendation
from enigma.runner import run_command


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = self.base / 'fixture'
        self.repo.mkdir()
        self.manifest = self.repo / 'pyproject.toml'
        self.manifest.write_text('[project]\nname="fixture"\nrequires-python=">=3.12,<3.14"\ndependencies=["pydantic>=2"]\n', encoding='utf-8')
        (self.repo / 'requirements.txt').write_text('pydantic==1.10.13\n', encoding='utf-8')
        (self.repo / 'linkwatch').mkdir()
        (self.repo / 'linkwatch/config.py').write_text('from pydantic import BaseModel\n', encoding='utf-8')
        self.out = self.base / 'reports'

    def tearDown(self):
        self.temp.cleanup()

    def inspect(self):
        return inspect_repository(self.repo)

    def report(self):
        return workflow(self.repo, self.out)

    def test_evidence_has_real_lines_and_stable_id(self):
        result = self.inspect()
        self.assertEqual(result['findings'][0]['id'], 'ENIGMA-PYDANTIC-001')
        for e in result['evidence']:
            actual = (self.repo / e['path']).read_text().splitlines()[e['line'] - 1]
            self.assertIn(e['text'], actual)
        self.assertEqual(result['imports']['pydantic'][0]['line'], 1)

    def test_no_unused_inference(self):
        self.manifest.write_text('[project]\ndependencies=["unused-looking-package"]\n')
        self.assertFalse(self.inspect()['findings'])

    def test_missing_and_malformed(self):
        self.manifest.unlink()
        self.assertTrue(self.inspect()['issues'])
        self.manifest.write_text('[project')
        self.assertEqual(self.inspect()['issues'][0]['status'], 'BLOCKED')
        self.manifest.write_text('[project]\ndependencies=123\n')
        self.assertFalse(self.inspect()['findings'])
        self.assertTrue(self.inspect()['issues'])
        self.assertEqual(inspect_repository(self.base / 'absent')['issues'][0]['status'], 'BLOCKED')

    def test_bound_and_skip(self):
        (self.repo / '.venv').mkdir()
        (self.repo / '.venv/hidden.py').write_text('import should_not_scan\n')
        (self.repo / 'huge.py').write_bytes(b'x' * (MAX_FILE + 1))
        (self.repo / 'broken.py').write_text('def (')
        result = self.inspect()
        self.assertNotIn('should_not_scan', result['imports'])
        self.assertEqual(len(result['issues']), 2)

    def test_recommendation_validation(self):
        inspection = self.inspect()
        finding = inspection['findings'][0]
        value = {'finding_id': finding['id'], 'summary': 'Fixture only',
                 'recommendation': 'Review declarations', 'evidence_refs': finding['evidence_refs']}
        self.assertEqual(validate_recommendation(value, finding, inspection['evidence']), value)
        for bad in [[], {}, {**value, 'evidence_refs': ['missing']}, {**value, 'finding_id': 'unknown'},
                    {**value, 'summary': 2}, {**value, 'command': 'evil'}, {**value, 'evidence_refs': []}]:
            with self.assertRaises(ValueError):
                validate_recommendation(bad, finding, inspection['evidence'])

    def test_unavailable_and_malformed_model(self):
        inspection = self.inspect()
        with patch('enigma.model.request', side_effect=TimeoutError('fixture timeout')):
            result = recommend(inspection, 'gemma3:1b')
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIsNone(result['recommendation'])
        with patch('enigma.model.request', side_effect=[{'models': [{'name': 'gemma3:1b'}]},
                   {'model': 'gemma3:1b', 'done': True, 'response': 'not json'}]):
            self.assertEqual(recommend(inspection, 'gemma3:1b')['status'], 'BLOCKED')
        with patch('enigma.model.request') as request:
            self.assertEqual(recommend(inspection, 'gemma3:cloud')['status'], 'BLOCKED')
            request.assert_not_called()
        with patch('enigma.model.request', return_value={'models': []}) as request:
            self.assertEqual(recommend(inspection, 'gemma3:1b')['status'], 'BLOCKED')
            self.assertEqual(request.call_count, 1)
        with patch('enigma.model.request', return_value=[]):
            self.assertEqual(recommend(inspection, 'gemma3:1b')['status'], 'BLOCKED')

    def test_approval_staleness_backup_and_noop(self):
        finding = self.inspect()['findings'][0]
        original = self.manifest.read_bytes()
        with self.assertRaises(PermissionError):
            apply(self.repo, finding, None, self.out)
        self.assertEqual(self.manifest.read_bytes(), original)
        self.manifest.write_bytes(original + b'# unrelated edit\n')
        with self.assertRaises(ValueError):
            apply(self.repo, finding, finding['id'], self.out)
        current = self.inspect()['findings'][0]
        before = self.manifest.read_bytes()
        result = apply(self.repo, current, current['id'], self.out)
        self.assertEqual(Path(result['backup']).read_bytes(), before)
        self.assertIn(b'# unrelated edit', self.manifest.read_bytes())
        self.assertIn(b'pydantic==1.10.13', self.manifest.read_bytes())
        self.assertFalse(self.inspect()['findings'])
        report = self.report()
        self.assertEqual(report['change']['status'], 'NO_ACTION')

    def test_changed_requirements_invalidate_review(self):
        finding = self.inspect()['findings'][0]
        (self.repo / 'requirements.txt').write_text('pydantic==1.10.14\n')
        with self.assertRaises(ValueError):
            apply(self.repo, finding, finding['id'], self.out)

    def test_proposal_preserves_crlf(self):
        self.manifest.write_bytes(self.manifest.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        finding = self.inspect()['findings'][0]
        changed, diff = proposal(self.repo, finding)
        self.assertIn(b'\r\n', changed)
        self.assertIn('-dependencies=["pydantic>=2"]', diff)

    def test_runner_success_failure_timeout_and_bound(self):
        good = run_command([sys.executable, '-c', 'print("ok")'], self.repo)
        self.assertEqual((good['status'], good['exit_code']), ('PASS', 0))
        fail = run_command([sys.executable, '-c', 'raise SystemExit(4)'], self.repo)
        self.assertEqual((fail['status'], fail['exit_code']), ('FAIL', 4))
        timeout = run_command([sys.executable, '-c', 'import time; time.sleep(3)'], self.repo, timeout=0.1)
        self.assertEqual(timeout['status'], 'TIMEOUT')
        noisy = run_command([sys.executable, '-c', 'print("x"*20000)'], self.repo, limit=100)
        self.assertTrue(noisy['truncated'])
        self.assertEqual(len(noisy['output']), 100)
        missing = run_command(['this-executable-does-not-exist-enigma'], self.repo)
        self.assertEqual(missing['status'], 'BLOCKED')

    def test_end_to_end_capsule_consistency_and_no_edits(self):
        before = self.manifest.read_bytes()
        report = self.report()
        self.assertEqual(report['status'], 'PARTIAL')
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertIsNone(report['model']['recommendation'])
        path = self.out / 'dependency_exit_capsule.json'
        md = self.out / 'dependency_exit_capsule.md'
        self.assertEqual(json.loads(path.read_text()), report)
        self.assertEqual(md.read_text(encoding='utf-8'), capsule.markdown(report))
        self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), md.read_text())
        self.assertEqual(main(['validate', str(path), '--markdown', str(md)]), 0)

    def test_invalid_capsules_rejected(self):
        report = self.report()
        mutations = [lambda r: r.pop('repository'), lambda r: r.update(status='PASS'),
                     lambda r: r['inspection']['evidence'][0].update(line=0),
                     lambda r: r['inspection']['findings'][0].update(evidence_refs=['unknown']),
                     lambda r: r['baseline'][0].update(status='PASS'),
                     lambda r: r['change'].update(status='APPLIED', approval=None),
                     lambda r: r['model'].update(status='PASS')]
        for mutate in mutations:
            bad = copy.deepcopy(report)
            mutate(bad)
            with self.assertRaises(ValueError):
                capsule.validate(bad)

    def test_aggregation_failure_wins_and_blocked(self):
        report = self.report()
        report['baseline'] = [run_command([sys.executable, '-c', 'raise SystemExit(1)'], self.repo)]
        self.assertEqual(capsule.aggregate(report), 'FAIL')
        report['baseline'] = []
        report['inspection']['issues'].append({'path': '.', 'status': 'BLOCKED', 'reason': 'fixture'})
        self.assertEqual(capsule.aggregate(report), 'BLOCKED')

    def test_apply_workflow_records_baseline_and_post(self):
        finding = self.inspect()['findings'][0]
        check = {'command': [sys.executable, '-c', 'pass'], 'cwd': str(self.repo), 'exit_code': 0,
                 'status': 'PASS', 'label': 'VERIFIED_BY_EXECUTION', 'output': '',
                 'interpreter': {'version': 'Python 3.12.10'}}
        # Only orchestration is stubbed here; the real argv runner is tested separately.
        with patch('enigma.cli.verify', return_value=[check]):
            report = workflow(self.repo, self.out, sys.executable, approval=finding['id'],
                              expected_hash=finding['proposed_action']['sha256'], do_apply=True)
        self.assertEqual(report['change']['status'], 'APPLIED')
        self.assertEqual(report['baseline'], report['post_change'])
        self.assertTrue(capsule.validate(report))

    def test_apply_refuses_failed_baseline_and_wrong_hash(self):
        finding = self.inspect()['findings'][0]
        before = self.manifest.read_bytes()
        result = workflow(self.repo, self.out, approval=finding['id'], expected_hash='wrong', do_apply=True)
        self.assertEqual(result['change']['status'], 'FAILED')
        check = run_command([sys.executable, '-c', 'raise SystemExit(1)'], self.repo)
        with patch('enigma.cli.verify', return_value=[check]):
            result = workflow(self.repo, self.out, approval=finding['id'],
                              expected_hash=finding['proposed_action']['sha256'], do_apply=True)
        self.assertEqual(result['change']['status'], 'FAILED')
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_reports_cannot_mutate_target(self):
        with self.assertRaises(ValueError):
            workflow(self.repo, self.repo / 'reports')

    def test_real_approved_fixture_end_to_end(self):
        # Disposable fixture, never represented as the real LinkWatch run.
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_fixture.py').write_text(
            'from pathlib import Path\nimport tomllib\n'
            'def test_manifest_is_parseable(tmp_path):\n'
            '    (tmp_path / "test.txt").write_text("created")\n'
            '    data=tomllib.loads(Path("pyproject.toml").read_text())\n'
            '    assert data["project"]["name"] == "fixture"\n')
        finding = self.inspect()['findings'][0]
        result = workflow(self.repo, self.out, sys.executable, approval=finding['id'],
                          expected_hash=finding['proposed_action']['sha256'], do_apply=True)
        self.assertEqual(result['change']['status'], 'APPLIED')
        self.assertEqual(result['baseline'][0]['status'], 'PASS')
        self.assertEqual(result['post_change'][0]['status'], 'PASS')
        self.assertIn('1 passed', result['post_change'][0]['output'])
        self.assertTrue(capsule.validate(result))

    def test_redacts_url_credentials_query_and_tokens(self):
        value = redact('https://user:pw@example.org/repo?token=secret api_key=abcdef ghp_abcdef123')
        for secret in ('user:pw', 'token=secret', 'abcdef'):
            self.assertNotIn(secret, value)


if __name__ == '__main__':
    unittest.main()
