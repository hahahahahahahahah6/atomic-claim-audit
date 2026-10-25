"""Offline static audit of documented atomic-write promises."""
import ast
import fnmatch
import re
from pathlib import Path

PHRASES = (
    'atomic write', 'atomic writes', 'atomically writes', 'atomically saves',
    'atomically updates', 'atomic save', 'atomic saves', 'atomic update',
    'atomic updates', 'crash-safe write', 'crash-safe writes', 'crash safe write',
    'crash safe writes', 'all-or-nothing write', 'all-or-nothing writes',
    'atomic file write', 'atomic file writes',
)
CLAIM = re.compile(r'\b(?:' + '|'.join(sorted(PHRASES, key=len, reverse=True)) + r')\b', re.I)
NEGATION = re.compile(r"\b(?:no|not|never|without|doesn't|don't|isn't)\b", re.I)
TEMP_CALLS = {'tempfile.NamedTemporaryFile', 'tempfile.mkstemp',
              'tempfile.TemporaryFile', 'tempfile.SpooledTemporaryFile'}


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return dotted(node.value) + '.' + node.attr
    return ''


def base_name(node):
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def claims_in(text, path):
    """Extract one record per claiming sentence, preserving source lines."""
    lines = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if fence:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
            lines.append('')
        elif marker:
            fence = marker.group(1)
            lines.append('')
        else:
            lines.append(line)
    prose = '\n'.join(lines)
    result = []
    for match in re.finditer(r'[^.!?]+(?:[.!?]|$)', prose):
        sentence = match.group()
        phrase = CLAIM.search(sentence)
        if phrase and not NEGATION.search(sentence):
            offset = match.start() + phrase.start()
            result.append({'family': 'atomic-write', 'path': path,
                           'line': prose.count('\n', 0, offset) + 1,
                           'phrase': phrase.group()})
    return result


def evidence_in(text, path):
    tree = ast.parse(text, filename=path)
    temps = set()
    for node in ast.walk(tree):
        value = getattr(node, 'value', None)
        if isinstance(value, ast.Call) and dotted(value.func) in TEMP_CALLS:
            targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, 'target', None)]
            for target in targets:
                if target:
                    temps.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        if isinstance(node, ast.withitem) and isinstance(node.context_expr, ast.Call):
            if dotted(node.context_expr.func) in TEMP_CALLS and node.optional_vars:
                temps.update(n.id for n in ast.walk(node.optional_vars) if isinstance(n, ast.Name))
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted(node.func)
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else ''
        target = None
        kind = None
        if name in {'shutil.copy', 'shutil.copy2', 'shutil.move'}:
            kind = name
            target = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == 'dst'), None)
        elif attr in {'write_text', 'write_bytes'}:
            kind = attr
            target = node.func.value
        elif name in {'open', 'io.open'} or attr == 'open':
            builtin = name in {'open', 'io.open'}
            index = 1 if builtin else 0
            mode = node.args[index] if len(node.args) > index else next((k.value for k in node.keywords if k.arg == 'mode'), None)
            if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(c in mode.value for c in 'wax+'):
                kind = name if builtin else 'Path.open'
                target = (node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == 'file'), None)) if builtin else node.func.value
        if kind and base_name(target) not in temps:
            found[(node.lineno, kind)] = {'path': path, 'line': node.lineno, 'kind': kind}
    return sorted(found.values(), key=lambda e: (e['line'], e['kind']))


def audit(root, ignore=()):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('audit path must be a directory')
    claims, production, testonly, errors = [], [], [], []
    source_count = 0
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
            continue
        if not path.is_file() or path.name == '.env' or path.name.startswith('.env.'):
            continue
        if any(fnmatch.fnmatchcase(relative, pattern) for pattern in ignore):
            continue
        parts = path.relative_to(root).parts
        doc = relative == 'README.md' or (parts[0] == 'docs' and path.suffix == '.md')
        source = path.suffix == '.py' and not any(p in {'docs', 'examples'} for p in parts[:-1])
        if not doc and not source:
            continue
        is_test = any(p in {'tests', 'fixtures'} for p in parts[:-1]) or path.name.startswith('test_') or path.name.endswith('_test.py')
        if source and not is_test:
            source_count += 1
        try:
            text = path.read_text(encoding='utf-8')
            if doc:
                claims.extend(claims_in(text, relative))
            if source:
                (testonly if is_test else production).extend(evidence_in(text, relative))
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append({'path': relative, 'message': str(exc)})
    findings, verified = [], []
    if claims:
        evidence = production
        severity = 'HIGH'
        rule = 'documented-atomic-claim-false'
        if not source_count:
            evidence = [{'path': '.', 'line': 0, 'kind': 'no-source'}]
        elif not production and testonly:
            evidence = testonly
            severity = 'MEDIUM'
            rule += '-test-only'
        if evidence:
            findings.append({'rule': rule, 'severity': severity, 'family': 'atomic-write',
                             'claims': claims, 'evidence': evidence})
        else:
            verified = [{'family': 'atomic-write', 'claims': claims}]
    return {'findings': findings, 'verified_claims': verified, 'errors': errors}
