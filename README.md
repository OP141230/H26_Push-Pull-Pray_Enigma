# Enigma — Evidence-Driven Repository Maintenance Agent Skill

> **Hacktoberfest 2026 · Track 2: Maintenance Agent Skill**  
> **Team**: Push-Pull-Pray  
> **Event**: Hacktoberfest Hack Day Mumbai × ISTE KJSSE — 15 October 2026

---

## What Enigma Does

Enigma is a reusable, AI-powered maintenance capability that performs evidence-driven dependency maintenance on any Python repository. It was built for the **LinkWatch** repository provided by the hackathon organisers.

Enigma runs a structured, fully traceable workflow:

```
INSPECT → FINDING → MODEL RECOMMENDATION → REVIEW → APPLY → VERIFY → CAPSULE
```

Every output is labelled with its evidence status:

| Label | Meaning |
|-------|---------|
| `OBSERVED` | Directly read from repository files |
| `AI_RECOMMENDATION` | Produced by a real Gemma model invocation |
| `VERIFIED_BY_EXECUTION` | Confirmed by a recorded command result |
| `NOT_VERIFIED` | Not yet demonstrated |
| `BLOCKED` | Could not proceed due to a concrete blocker |

---

## The LinkWatch Finding

**OBSERVED** — Evidence from repository inspection:

### Finding: Pydantic v1/v2 Version Conflict and Deprecated API Usage

| Field | Value |
|-------|-------|
| Finding ID | `FND-1A2D3433` |
| Classification | `DEPENDENCY_VERSION_CONFLICT` |
| Severity | `HIGH` |
| Confidence | 97% |

**Evidence** (`OBSERVED` — `linkwatch` commit `f52f3930`):

| File | Line | Evidence |
|------|------|----------|
| `pyproject.toml` | 12 | `"pydantic>=2"` — v2 required |
| `requirements.txt` | 1 | `pydantic==1.10.13` — v1 pinned (contradicts pyproject) |
| `linkwatch/config.py` | 5 | `@validator("name")` — Pydantic v1 API removed in v2 |
| `linkwatch/config.py` | 8 | `class Config:` / `anystr_strip_whitespace` — v1 inner Config |
| `linkwatch/config.py` | 14 | `@validator("url")` — Pydantic v1 API removed in v2 |

**Why it matters**: Installing `pydantic>=2` (as declared in `pyproject.toml`) breaks the application at import time because `config.py` uses `@validator`, `class Config`, and `anystr_strip_whitespace` — all removed in Pydantic v2. Installing `pydantic==1.10.13` contradicts the `pyproject.toml` constraint.

**Pre-existing baseline failure** (`OBSERVED`): `tests/test_report.py` fails with `ImportError: cannot import name 'soft_unicode' from 'markupsafe'` — caused by `Jinja2==2.11.3` being incompatible with the installed `markupsafe`. This failure existed **before** Enigma's change and was not introduced by it.

---

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         ENIGMA WORKFLOW                         │
├──────────┬───────────┬──────────┬──────────┬──────────┬─────────┤
│ INSPECT  │  FINDING  │  MODEL   │  REVIEW  │  VERIFY  │ CAPSULE │
│ (Stage A)│ (Stage B) │ (Stage C)│ (Stage D)│ (Stage E)│(Stage F)│
├──────────┴───────────┴──────────┴──────────┴──────────┴─────────┤
│ inspector.py  finding.py  model_adapter.py  reviewer.py         │
│ verifier.py   capsule.py  schema.py  workflow.py  cli.py        │
└─────────────────────────────────────────────────────────────────┘
```

- **Stage A** (`inspector.py`): Reads `pyproject.toml`, `requirements*.txt`, `.python-version`, scans source for Pydantic v1 API patterns. Never raises — all errors captured.
- **Stage B** (`finding.py`): Builds a structured `Finding` dataclass with deterministic ID, evidence refs, severity, and proposed action.
- **Stage C** (`model_adapter.py`): Detects Ollama + Gemma, submits bounded evidence, validates JSON response against strict schema. Graceful fallback if unavailable.
- **Stage D** (`reviewer.py`): Displays finding + recommendation, computes diff preview, applies smallest justified change only after approval. Creates `.bak` backups.
- **Stage E** (`verifier.py`): Runs import check, pytest, syntax check before and after change. Arg-list subprocess — no shell injection.
- **Stage F** (`capsule.py` + `schema.py`): Generates `reports/dependency_exit_capsule.json` and `reports/dependency_exit_capsule.md` from single in-memory object. Validates against JSON Schema.

---

## Prerequisites

- **Python 3.12** (required — Python 3.14 is not supported by LinkWatch)
- **Python 3.13** (optional — for extended coverage testing)
- **Git**
- **Ollama** (optional — for Gemma AI recommendations)

---

## Installation

```bash
# Clone this repository
git clone https://github.com/OP141230/H26_Push-Pull-Pray_Enigma.git
cd H26_Push-Pull-Pray_Enigma

# Install Enigma with Python 3.12
py -3.12 -m pip install -e ".[dev]"

# Clone LinkWatch (organizer-provided target)
git clone https://github.com/rishrek/LinkWatch linkwatch
```

---

## Usage

### Inspect only (read-only, no changes)
```bash
py -3.12 -m enigma.cli inspect --target ./linkwatch
```

### Dry-run (preview changes — no files modified)
```bash
py -3.12 -m enigma.cli run --target ./linkwatch --dry-run
```

### Apply the maintenance change
```bash
py -3.12 -m enigma.cli run --target ./linkwatch --auto-approve
```

### Validate the generated capsule
```bash
py -3.12 -m enigma.cli validate --capsule reports/dependency_exit_capsule.json
```

### Run the test suite
```bash
py -3.12 -m pytest tests/ -v
```

---

## AI Model Setup

Enigma uses **Gemma** (Google DeepMind open-weight model) via **Ollama** for local inference.

| Field | Value |
|-------|-------|
| Model name | Gemma |
| Model version | `gemma:2b` or `gemma3:1b` (any Gemma model in Ollama) |
| Model source | Google DeepMind — open-weight, Apache 2.0 |
| Access method | Local inference via Ollama (`localhost:11434`) — **no paid APIs** |
| License | Gemma Terms of Use (Apache-compatible for non-commercial use) |
| Role | Provides structured `proposed_change` + `rationale` grounded in evidence |

```bash
# Install Ollama: https://ollama.com
# Then pull a Gemma model:
ollama pull gemma:2b

# Re-run Enigma — model recommendation will be performed:
py -3.12 -m enigma.cli run --target ./linkwatch --dry-run
```

Without Ollama/Gemma, the deterministic workflow completes fully with status `BLOCKED` for the model step. The finding and capsule are still generated correctly.

---

## Hermes Agent Integration

**Status**: `NOT_VERIFIED` — Hermes Agent was not installed in this environment.

This skill is structured to follow the [Agent Skills Open Standard](https://agentskills.io/home). See `skills/enigma-maintainer/skill.md` for the full skill definition.

```bash
# When Hermes is installed:
# hermes run enigma-maintainer --repo_path ./linkwatch
```

---

## Generated Capsules

| File | Description |
|------|-------------|
| `reports/dependency_exit_capsule.json` | Structured JSON — all findings, evidence, results |
| `reports/dependency_exit_capsule.md` | Human-readable Markdown version |

Both are generated from the same in-memory `EnigmaCapsule` object. Schema validation is run automatically using `jsonschema/Draft7`.

---

## Test Results — `VERIFIED_BY_EXECUTION`

```
Platform : Windows, Python 3.12.0, pytest-8.4.2
Command  : py -3.12 -m pytest tests/ -v
Result   : 75/75 passed ✅
```

Python 3.13 coverage: `NOT_VERIFIED` — not installed in this environment.

---

## Baseline and Post-Change Verification — `VERIFIED_BY_EXECUTION`

| Check | Baseline | Post-Change |
|-------|----------|-------------|
| `import_check` | ✅ PASS (exit=0) | ✅ PASS (exit=0) |
| `pytest` | ❌ FAIL (pre-existing: Jinja2==2.11.3 incompatible with markupsafe) | ❌ FAIL (same pre-existing failure — not caused by Enigma) |
| `syntax_check_config` | ✅ PASS (exit=0) | ✅ PASS (exit=0) |

The pre-existing `pytest` failure (`ImportError: soft_unicode`) was present before Enigma's change and is caused by `Jinja2==2.11.3` — a second evidence-backed maintenance issue in LinkWatch.

---

## Known Limitations and Blockers

| Item | Status | Reason |
|------|--------|--------|
| Gemma model inference | `BLOCKED` | Ollama installed but no model pulled yet. Run `ollama pull gemma:2b` |
| Python 3.13 testing | `NOT_VERIFIED` | Not installed in development environment |
| Hermes Agent integration | `NOT_VERIFIED` | Hermes not installed |
| LinkWatch `pytest` suite | Pre-existing `FAIL` | `Jinja2==2.11.3` incompatible with installed `markupsafe` — not introduced by Enigma |

---

## Architecture

```
Enigma/
├── enigma/
│   ├── inspector.py      # Stage A: deterministic repo inspection
│   ├── finding.py        # Stage B: structured Finding model
│   ├── model_adapter.py  # Stage C: Gemma/Ollama adapter
│   ├── reviewer.py       # Stage D: safe review + apply
│   ├── verifier.py       # Stage E: before/after command execution
│   ├── capsule.py        # Stage F: JSON + MD capsule generation
│   ├── schema.py         # JSON Schema validator
│   ├── workflow.py       # Orchestrator
│   └── cli.py            # Click CLI
├── skills/
│   └── enigma-maintainer/
│       └── skill.md      # Agent Skills Open Standard definition
├── tests/                # 75 pytest tests
├── reports/              # Generated capsules (gitignored except .gitkeep)
├── linkwatch/            # Organizer-provided target repository
└── pyproject.toml
```

---

## License

MIT — see `LICENSE` file.

---

## Dependencies

| Package | Version | Role |
|---------|---------|------|
| `click` | >=8.1,<9 | CLI interface |
| `jsonschema` | >=4.21,<5 | Capsule schema validation |
| `requests` | >=2.32,<3 | Ollama API calls |
| `pytest` | >=8,<9 | Test runner (dev) |
| `pytest-cov` | >=5,<6 | Coverage (dev) |

---

## Original Contribution

Enigma is not a prompt change or UI modification. It adds:
- A new **deterministic inspector** for Python dependency metadata
- A **structured Finding model** with traceable evidence references
- A **Gemma-backed model adapter** with response validation and graceful fallback
- A **safe reviewer** with dry-run, approval gate, and `.bak` recovery
- A **bounded verifier** running real pytest suites with before/after comparison
- A **dual-format capsule generator** (JSON + Markdown) from a single source object
- A **JSON Schema validator** for capsule integrity
- A complete **75-test pytest suite** covering all stages
