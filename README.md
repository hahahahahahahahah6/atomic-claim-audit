# atomic-claim-audit

Offline audit of documented atomic-write claims against Python source.
Version 0.1.0; Python 3.9 or newer; MIT; no runtime dependencies.

The CLI reads documentation and parses Python ASTs. It never executes audited
code, uses no network, never reads `.env` file contents, and never writes to
the audited tree. Symlinked files and directories are skipped.

## Usage

```sh
python3 -m pip install .
atomic-claim-audit /path/to/project
python3 -m atomic_claim_audit /path/to/project --json
atomic-claim-audit . --ignore 'vendor/*' --ignore 'generated.py' --verbose
atomic-claim-audit tests/fixtures/testonly --fail-on HIGH
atomic-claim-audit --version
```

The path defaults to the current directory. `--ignore` is repeatable and matches
case-sensitive relative-path globs. `--verbose` also shows verified families.
`--json` returns `findings`, `verified_claims`, and `errors` arrays; findings
include `rule`, `severity`, `family`, `claims`, and all `evidence` records
(`path`, `line`, `kind`). Verified records include `family` and `claims`.
Unreadable, invalid UTF-8, and syntactically invalid input files are reported
as errors, with exit 1, rather than silently treated as clean scans.

## Rules

| Condition | Rule | Severity |
| --- | --- | --- |
| Claim and production direct writes | documented-atomic-claim-false | HIGH |
| Claim and no production Python source | documented-atomic-claim-false (`no-source`) | HIGH |
| Claim, production source, only test/fixture writes | documented-atomic-claim-false-test-only | MEDIUM |
| Claim and no direct-write evidence | verified atomic-write family | PASS |
| No claim | no finding, regardless of writes | PASS |

One finding contains every relevant evidence item; multiple phrases still form
one `atomic-write` family. Exit codes are 0 for PASS, 2 for findings at the
threshold, and 1 for usage/input errors. The default `--fail-on MEDIUM` includes
both severities. `--fail-on HIGH` retains MEDIUM findings but exits 0 for them.

Claims come only from root `README.md` and `docs/**/*.md`. Fenced code is
excluded; inline code counts. A sentence containing no, not, never, without,
doesn't, don't, or isn't suppresses every claim in that sentence.
The exact case-insensitive phrases are: atomic write(s), atomically writes,
atomically saves, atomically updates, atomic save(s), atomic update(s),
crash-safe write(s), crash safe write(s), all-or-nothing write(s), and atomic
file write(s). Parenthetical `(s)` here means the singular and plural forms.

Direct-write evidence consists of `open`, `io.open`, or any `.open` call with
a literal mode containing `w`, `a`, `x`, or `+`; any `.write_text` or
`.write_bytes` call; and `shutil.copy`, `shutil.copy2`, or `shutil.move`.
Production excludes tests/ and fixtures/ directories, test_*.py, *_test.py,
docs/, and examples/. Test/fixture evidence is collected separately; docs and
examples never contribute source evidence.

## Differentiation

| Neighbour | Different question |
| --- | --- |
| readonly-claim-audit | Whether writes exist, never their atomicity |
| determinism-claim-audit | Run-to-run stability, never write safety |
| security-claim-audit | eval/shell/pickle hazards, never write patterns |
| bandit / ruff | Code issues, never documentation promises |
| atomicwrites / filelock | Runtime helpers that perform writes or locking; this tool statically audits promises |

## Honest limitations

Only the exact listed phrases count: bare “atomic”, “atomic operations”,
“atomic config writes”, and “atomic JSON writes” do not. Sentence splitting
uses `.`, `!`, and `?`; this is a heuristic, not natural-language understanding.
Static evidence is not a crash-safety proof. Dead code counts. Receiver types,
import aliases, dynamic calls, and descriptor provenance are not inferred.
Variable modes and absent modes are skipped as UNKNOWN, never evidence.

`print(..., file=...)`, `os.replace`, `os.rename`, deletion and directory
operations (`remove`, `unlink`, `mkdir`, `rmdir`), and `os.write` are excluded.
Replace/rename are the atomic step themselves; descriptor writes are untracked.

Temp-var tracking is per-file and by variable name, without scope or order
analysis. Names assigned from `tempfile.NamedTemporaryFile`, `mkstemp`,
`TemporaryFile`, or `SpooledTemporaryFile` (including with bindings and tuple
unpacking) are tracked. A write whose target is such a name or an attribute
based on it is excluded. Other direct writes in the same function still count.
This can miss writes after reassignment or name reuse. No replace-step proof
is required: a temp write with no replace can leak a file, but does not corrupt
a final path, so this deliberate leniency is outside the corruption audit.
Filesystem durability, fsync, cross-filesystem rename, concurrency, and locking
are not proven. Copy/move destinations count unless they are tracked temp vars.

## Development

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m build
```

The build produces a wheel and sdist under `dist/`. Fixtures ship in the sdist.
If isolated builds are unavailable offline, use `python3 -m build --no-isolation`.
