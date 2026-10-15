# ENIGMA

**Evidence-driven Python repository maintenance, with explicit approval and reproducible capsules.**

`INSPECT → FINDING → RECOMMEND → REVIEW → APPLY IF APPROVED → VERIFY → CAPSULE`

This is a working command-line MVP. It extends the manifest and AST evidence approach
from the existing LinkWatch `tools/dependency_evidence.py`; that checkout and its prior
changes are preserved. No standalone Enigma or DepExit implementation was found in
the inspected Documents workspace. The original MIT notice is retained in LICENSE.

## Latest integration check

Presentation update: **26 Enigma tests pass**. Every run now generates an offline
`reports/dependency_exit_capsule.html` presentation, plus JSON and Markdown. The
console and both human-facing reports separate workflow completion, repository
baseline, model inference, approval, changes, post-change checks, Hermes discovery
and Hermes agent execution. A completed review is not a repository PASS.

Open the presentation in PowerShell with:

```powershell
Start-Process .\reports\dependency_exit_capsule.html
```

To display the existing recorded run and regenerate its views without running
tests, inference or edits:

```powershell
python -m enigma show reports/dependency_exit_capsule.json --output reports
python -m enigma validate reports/dependency_exit_capsule.json --markdown reports/dependency_exit_capsule.md --html reports/dependency_exit_capsule.html
```

`show` exits 0 when reading/rendering succeeds, even if the saved repository result
is FAIL. `run` retains its existing aggregation and exit codes. These presentation
states are derived from the canonical report; they do not replace recorded outcomes.
The HTML uses no external assets or JavaScript, escapes all dynamic content, and
includes command logs, the model recommendation, the separate deterministic patch,
limitations and links to canonical data. See DEPENDENCY_EXPLANATION.md for the
observed LinkWatch dependency failure and Enigma's editing boundary.

After local setup, `gemma4:latest` produced an actual validated recommendation:
**Model PASS**, with 21 Enigma tests passing. Both capsules were regenerated from the
live run. Overall remains FAIL because LinkWatch still has its pre-existing test failure.
The Markdown capsule now presents the model's suggested action, rationale, risks,
future verification steps and cited evidence in a dedicated Gemma recommendation
section. The CLI prints its suggested action too. The text comes from inference;
only the schema and presentation are predefined. Input evidence and prompt/response
hashes are recorded for traceability, not as a cryptographic attestation of inference.

Hermes discovery succeeds, but skill invocation remains NOT_VERIFIED. Direct Python
CLI runs are orchestrated by Enigma, not Hermes. A Hermes-driven demonstration must
show Hermes loading the skill, invoking Enigma, reading the report and presenting
the recommendation/approval request. Listing an installed skill is not proof of that.
The table below records the initial delivery, before the user's local model setup.

## Initial delivery result, 15 October 2026

| Item | Evidence/status |
|---|---|
| Enigma test suite | **18 tests passed**, Python 3.12.10 |
| Real LinkWatch inspection | `ENIGMA-PYDANTIC-001`: incompatible Pydantic declarations |
| LinkWatch baseline | **14 passed, 1 failed**, exit 1; existing Jinja2/MarkupSafe import failure |
| LinkWatch modifications | **None**; prior changes preserved; no approval granted |
| Capsules | Structural/semantic validation and JSON/Markdown consistency passed |
| Skill | Frontmatter/name validator passed; Hermes invocation unavailable |
| Local inference | Ollama responds, but `ollama list` is empty; requested Gemma tag unavailable |
| Python 3.13 | NOT_VERIFIED; no installed interpreter found |
| Event handbook | Not found in accessible Documents, attachments, Downloads or Desktop search |

**The real capsule's overall result is FAIL**, because a requested repository check
failed. This does not mean the Enigma test suite failed. No real model recommendation
was generated at initial delivery; later live inference is recorded above. This
project is not claimed to satisfy event submission requirements.

## Run without installing

For slow local inference or first model loading, add `--model-timeout 300`.
The default is 180 seconds; allowed values are 1–900 seconds. The selected timeout
is recorded in new capsules. This replaces the original 20-second inference timeout.
The adapter requests schema-constrained JSON with thinking disabled and a 1,200-token
output limit. Empty or truncated final responses remain BLOCKED; reasoning text is
never treated as the recommendation. Regression coverage now totals 21 passing tests.

Use Python 3.12 or 3.13. Enigma itself uses only the standard library. Its test suite
uses unittest; one end-to-end fixture also invokes an already-installed pytest.
Target-repository checks require that repository's dependencies and pytest.

From this directory, in PowerShell:

```powershell
python -m enigma --help
$repo = 'C:\Users\aryuk\Documents\Codex\2026-10-15\referenced-chatgpt-conversation-this-is-an\work\LinkWatch'
$targetPython = Join-Path $repo '.venv\Scripts\python.exe'
python -m enigma run $repo --output reports --check-python $targetPython --model gemma3:1b
python -m enigma validate reports/dependency_exit_capsule.json --markdown reports/dependency_exit_capsule.md
```

The first command above runs real repository tests; it returns exit 1 with the current
LinkWatch baseline. Validation returns exit 0. Omitting `--model` explicitly records
inference as NOT_VERIFIED. Omitting `--check-python` records tests as SKIPPED and cannot
produce PASS. On another machine, substitute the repository and interpreter paths.
`~` in recorded paths is a privacy redaction; the README commands contain actual paths.

Optional local package installation: `python -m pip install -e .`. No installation
is necessary for the tested module commands. Packaging installation was not tested.
Git is used for provenance. Reports must be outside the inspected repository.

## Real finding and review

The existing checkout is `rishrek/LinkWatch`, branch `main`, commit
`f52f3930c8e7c33d934ccf614955a38e26984bd5`, with pre-existing uncommitted work.

`pyproject.toml:16` declares `pydantic>=2`, while `requirements.txt:4` declares
`pydantic==1.10.13`. `linkwatch/config.py:4` imports Pydantic's v1 validator and
line 12 uses `anystr_strip_whitespace`. The conflicting major-version declarations
are directly observable regardless of whether either environment happens to pass tests.

The proposed one-line change aligns pyproject.toml with the existing requirements pin.
It preserves the earlier tomllib migration and Python metadata changes. It proves only
declaration consistency, not a fresh package install or complete v1/v2 compatibility.
No dependency is declared unused from import-name matching.

Read [reports/proposed.patch](reports/proposed.patch) and the evidence in the capsules.
Approval has **not** been supplied for LinkWatch. The real baseline also fails:
Jinja2 2.11.3 imports `markupsafe.soft_unicode`, absent from the installed MarkupSafe.
That separate issue must be investigated and explicitly authorized before repair.
Enigma deliberately does not hide it or automatically change unrelated dependencies.

After the baseline passes and a human explicitly approves the displayed patch:

```powershell
$review = Get-Content reports/dependency_exit_capsule.json -Raw | ConvertFrom-Json
python -m enigma run $repo --output reports --check-python $targetPython --apply --approve ENIGMA-PYDANTIC-001 --expected-sha256 $review.change.review_sha256
```

The approval ID and previously reviewed hash are mandatory. Current evidence is
recomputed before applying; changed evidence is rejected. Only the whitelisted
dependency string in pyproject.toml can be changed. Original bytes are backed up
outside the checkout, preserving BOM/newlines and unrelated edits. Post-change tests
use the same command shape and interpreter, with separate disposable temp paths.
Recovery instructions and backup hashes are recorded. There is no automatic rollback
or concurrent-writer transaction; avoid editing the target during apply.

## Architecture

| Module | Responsibility |
|---|---|
| `evidence.py` | Bounded manifests, AST imports, references, file hashes and narrow conflict rule |
| `model.py` | Local Ollama adapter, output limits, JSON/reference validation, unavailable path |
| `maintenance.py` | Human approval, stale-evidence guard, small edit and backup |
| `runner.py` | Shell-free argv execution, bounded capture, timeout, exit status |
| `capsule.py` | Canonical data, focused structural/semantic validator and Markdown rendering |
| `cli.py` | Provenance, orchestration, verification and CLI exit codes |

The inspector limits files to 128 KiB and Python sources to 300; it skips virtual
environments, caches, model directories and Git internals. Only pyproject.toml and
requirements.txt dependencies are parsed; extras, dynamic dependencies and complex
requirement syntax are reported as outside scope. It does not resolve package versions.

Only `http://127.0.0.1:11434` is used for model inference; proxies and redirects are
disabled. The adapter requires an installed Gemma tag, rejects cloud tags, sends only
bounded finding evidence, and never pulls weights. It cannot attest the internals of
a user-modified inference server or certify model licensing. A valid model response is
an AI_RECOMMENDATION, not proof. Mock responses in unit tests are not real inference.

Tests execute trusted repository code with the current user's permissions. The command
runner is not a sandbox; it bounds captured output and kills its direct child on timeout.
It does not guarantee termination of descendants launched by arbitrary test programs.
Common credentials and home-directory names are redacted; no general-purpose redactor
can guarantee removal of every possible secret from arbitrary repository test output.
Review capsules before publishing them. No weights, venvs, caches or credentials are
included in the delivery archive.

## Status rules and validation

Evidence labels: OBSERVED, AI_RECOMMENDATION, VERIFIED_BY_EXECUTION, NOT_VERIFIED,
BLOCKED. These are distinct from overall outcomes:

1. **FAIL** if a requested check fails/times out or an attempted change fails.
2. **BLOCKED** if a necessary inspection/check cannot run, with no higher-priority FAIL.
3. **PARTIAL** for skipped checks, unverified integrations, incomplete inspection or limitations.
4. **PASS** only when all declared checks/integrations succeed and no limitations remain.

CLI run exit codes: 0 for PASS/PARTIAL, 1 for FAIL, 2 for BLOCKED/invalid invocation.
Always inspect the status field; exit 0 alone is not an assertion of complete success.
Handbook/compatibility limitations keep this delivery from an overall PASS.

`capsule.validate` is the focused structural validator: required fields/types, enum
values, evidence IDs, finding references, inference provenance, approvals, command
outcomes and aggregation are checked. Tests demonstrate rejection of invalid data.
Markdown embeds the entire canonical JSON and its SHA-256, and `validate --markdown`
checks exact generated-view consistency. Reports overwrite the previous run; copy
them elsewhere before rerunning if you need an archive.

## Tests and demo

```powershell
# Use a writable local temp directory if the sandbox's default temp is restricted.
$env:TEMP = 'C:\Users\aryuk\Documents\Codex\2026-10-15\make\work'
$env:TMP = $env:TEMP
python -m unittest discover -s tests -v
```

The 18 tests include malformed/missing files, bounds, evidence references, invalid
model output, unavailable runtime, approval refusal, stale evidence, no-op behavior,
backup preservation, command success/failure/timeout, invalid capsules, and a real
approved disposable-fixture workflow with pytest before and after. Fixture evidence
is never used as the real LinkWatch report. See [DEMO.md](DEMO.md) for a live demo.

## Hermes skill and remaining submission work

The canonical skill is [skills/enigma-maintainer/SKILL.md](skills/enigma-maintainer/SKILL.md).
Hermes is not installed here, so no discovery/invocation success is claimed. Copy that
folder into `~/.hermes/skills/enigma-maintainer/` on an existing Hermes installation,
without overwriting a prior skill, start a fresh session, run `hermes skills list`,
then invoke `/enigma-maintainer` with the Enigma project and repository paths.
The older skill in the LinkWatch checkout was preserved and was not renamed.

Before submission: obtain and audit the authoritative handbook, establish eligible
local Gemma inference and genuine Hermes invocation, resolve the baseline failure
with explicit approval, test Python 3.13, review exported data, and follow the event's
actual submission instructions. Nothing was committed, pushed or submitted.

Interface references checked during implementation:
[Agent Skills specification](https://agentskills.io/specification),
[Hermes skill discovery](https://hermes-agent.nousresearch.com/docs/guides/work-with-skills),
[Ollama generate API](https://docs.ollama.com/api/generate).
