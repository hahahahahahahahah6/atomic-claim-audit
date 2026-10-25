import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from atomic_claim_audit.audit import PHRASES, audit, claims_in, evidence_in
from atomic_claim_audit.__main__ import main

FIXTURES = Path(__file__).parent / 'fixtures'


class AuditTests(unittest.TestCase):
    def project(self, files, ignore=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding='utf-8')
            return audit(root, ignore)

    def test_good(self):
        report = audit(FIXTURES / 'good')
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['verified_claims'][0]['family'], 'atomic-write')

    def test_bad(self):
        findings = audit(FIXTURES / 'bad')['findings']
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]['rule'], 'documented-atomic-claim-false')
        self.assertEqual(findings[0]['severity'], 'HIGH')
        self.assertEqual(len(findings[0]['evidence']), 3)

    def test_testonly(self):
        finding = audit(FIXTURES / 'testonly')['findings'][0]
        self.assertEqual(finding['severity'], 'MEDIUM')
        self.assertEqual(finding['rule'], 'documented-atomic-claim-false-test-only')
        self.assertEqual(len(finding['evidence']), 1)

    def test_no_source(self):
        r = self.project({'README.md': 'Atomic writes.'})
        self.assertEqual(r['findings'][0]['evidence'][0]['kind'], 'no-source')

    def test_no_claim(self):
        self.assertEqual(self.project({'main.py': 'open(p,"w")'})['findings'], [])

    def test_docs_claim(self):
        r = self.project({'docs/sub/a.md': 'Atomic writes.', 'main.py': 'open(p,"w")'})
        self.assertEqual(len(r['findings']), 1)

    def test_other_docs_ignored(self):
        r = self.project({'other.md': 'Atomic writes.', 'main.py': 'open(p,"w")'})
        self.assertEqual(r['findings'], [])

    def test_ignore(self):
        r = self.project({'README.md': 'Atomic writes.', 'main.py': 'pass', 'bad.py': 'open(p,"w")'}, ['bad.py'])
        self.assertTrue(r['verified_claims'])

    def test_ignore_glob(self):
        r = self.project({'README.md': 'Atomic writes.', 'main.py': 'pass', 'vendor/a.py': 'open(p,"w")'}, ['vendor/*'])
        self.assertTrue(r['verified_claims'])

    def test_temp_and_direct(self):
        text = 't = tempfile.NamedTemporaryFile()\nopen(t.name,"w")\nopen(final,"w")'
        self.assertEqual(len(evidence_in(text, 'a.py')), 1)

    def test_temp_no_replace(self):
        text = 't = tempfile.NamedTemporaryFile()\nt.write_text("data")'
        self.assertEqual(evidence_in(text, 'a.py'), [])

    def test_dead_code(self):
        self.assertEqual(len(evidence_in('if False:\n open(p,"w")', 'a.py')), 1)

    def test_dedupe(self):
        self.assertEqual(len(evidence_in('open(p,"w"); open(q,"w")', 'a.py')), 1)

    def test_invalid_source(self):
        r = self.project({'main.py': 'def ('})
        self.assertEqual(len(r['errors']), 1)

    def test_env_not_read(self):
        r = self.project({'.env': 'secret', '.env.py': 'invalid syntax!', 'main.py': 'pass'})
        self.assertEqual(r['errors'], [])

    def test_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'README.md').write_text('Atomic writes.')
            (root / 'main.py').write_text('pass')
            (root / 'link.py').symlink_to(FIXTURES / 'bad' / 'main.py')
            (root / 'linked').symlink_to(FIXTURES / 'bad', target_is_directory=True)
            self.assertTrue(audit(root)['verified_claims'])

    def test_json(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([str(FIXTURES / 'good'), '--json'])
        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads(output.getvalue())), {'findings', 'verified_claims', 'errors'})

    def test_threshold(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(FIXTURES / 'testonly')]), 2)
            self.assertEqual(main([str(FIXTURES / 'testonly'), '--fail-on', 'HIGH']), 0)
            self.assertEqual(main([str(FIXTURES / 'bad'), '--fail-on', 'HIGH']), 2)

    def test_version(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exc:
            main(['--version'])
        self.assertEqual(exc.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), '0.1.0')

    def test_usage(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main(['--unknown'])
        self.assertEqual(exc.exception.code, 1)

    def test_missing_directory(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main(['/missing-atomic-claim-audit'])
        self.assertEqual(exc.exception.code, 1)

    def test_verbose(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main([str(FIXTURES / 'good'), '--verbose'])
        self.assertIn('Verified: atomic-write', output.getvalue())


def claim_case(text, expected):
    def test(self):
        self.assertEqual(bool(claims_in(text, 'README.md')), expected)
    return test


for index, phrase in enumerate(PHRASES):
    setattr(AuditTests, 'test_phrase_%02d' % index, claim_case('Uses ' + phrase.upper() + '.', True))
for index, text in enumerate([
    'Atomic operations.', 'Atomic counters.', 'Atomic config writes.',
    'Atomic JSON writes.', 'Atomically reads.', 'Nonatomic writes.',
    '```md\nAtomic writes.\n```', '~~~\nAtomic writes.\n~~~',
    'No atomic writes.', 'Not atomic writes.', 'Never atomic writes.',
    'Without atomic writes.', "It doesn't support atomic writes.",
    "Don't promise atomic writes.", "It isn't atomic writes.",
]):
    setattr(AuditTests, 'test_nonclaim_%02d' % index, claim_case(text, False))
setattr(AuditTests, 'test_inline_claim', claim_case('Supports `atomic writes`.', True))
setattr(AuditTests, 'test_sentence_negation', claim_case('No guarantees. Atomic writes.', True))


def evidence_case(source, count):
    def test(self):
        self.assertEqual(len(evidence_in(source, 'main.py')), count)
    return test


for index, (source, count) in enumerate([
    ('open(p,"w")', 1), ('open(p,"wb")', 1), ('open(p,"a+")', 1),
    ('open(p,"x")', 1), ('open(p,"r+")', 1), ('open(p,"r")', 0),
    ('open(p)', 0), ('open(p,mode)', 0), ('io.open(p,mode="w")', 1),
    ('open(file=p,mode="w")', 1), ('p.open("wb")', 1), ('p.open(mode="a")', 1),
    ('p.open()', 0), ('p.open(mode=m)', 0), ('p.write_text("x")', 1),
    ('Path(p).write_bytes(b"x")', 1), ('shutil.copy(a,b)', 1),
    ('shutil.copy2(a,b)', 1), ('shutil.move(a,b)', 1),
    ('os.replace(a,b)', 0), ('os.rename(a,b)', 0), ('print("x",file=f)', 0),
    ('os.write(fd,b"x")', 0), ('p.unlink()', 0), ('p.mkdir()', 0),
    ('t=tempfile.NamedTemporaryFile()\nopen(t.name,"w")', 0),
    ('fd,t=tempfile.mkstemp()\nopen(t,"wb")', 0),
    ('t=tempfile.TemporaryFile()\nt.write_bytes(b"x")', 0),
    ('t=tempfile.SpooledTemporaryFile()\nt.open("w")', 0),
    ('with tempfile.NamedTemporaryFile() as t:\n open(t.name,"w")', 0),
    ('t=tempfile.NamedTemporaryFile()\nshutil.copy2(a,t.name)', 0),
    ('def f():\n t=tempfile.NamedTemporaryFile()\n open(t.name,"w")\n os.replace(t.name,p)\n p.write_text("x")', 1),
]):
    setattr(AuditTests, 'test_evidence_%02d' % index, evidence_case(source, count))

for index, path in enumerate(['tests/a.py', 'fixtures/a.py', 'test_a.py', 'a_test.py']):
    def test(self, path=path):
        r = self.project({'README.md': 'Atomic writes.', 'main.py': 'pass', path: 'open(p,"w")'})
        self.assertEqual(r['findings'][0]['severity'], 'MEDIUM')
    setattr(AuditTests, 'test_test_path_%02d' % index, test)
for index, path in enumerate(['docs/a.py', 'examples/a.py']):
    def test(self, path=path):
        r = self.project({'README.md': 'Atomic writes.', 'main.py': 'pass', path: 'open(p,"w")'})
        self.assertTrue(r['verified_claims'])
    setattr(AuditTests, 'test_excluded_path_%02d' % index, test)

if __name__ == '__main__':
    unittest.main()
