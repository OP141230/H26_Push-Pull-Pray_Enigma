"""Stage C: Gemma model adapter via Ollama.

Detects Ollama availability and any Gemma model.
Passes bounded evidence to the model and validates the structured response.
Never crashes the deterministic workflow if inference is unavailable.

AI_RECOMMENDATION outputs are clearly labelled and separated from OBSERVED facts.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]


OLLAMA_BASE = "http://localhost:11434"
GEMMA_PATTERN = re.compile(r"gemma", re.IGNORECASE)

# Hard cap: pass at most this many characters of evidence to the model
MAX_EVIDENCE_CHARS = 1500


@dataclass
class ModelResult:
    """Captures everything about a single model invocation attempt."""
    status: str           # "SUCCESS" | "BLOCKED" | "FAILED" | "INVALID_RESPONSE"
    model_id: Optional[str] = None
    runtime: str = "ollama"
    inference_performed: bool = False
    raw_response: Optional[str] = None
    validated_recommendation: Optional[dict] = None
    validation_errors: list[str] = field(default_factory=list)
    blocker_reason: Optional[str] = None
    elapsed_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "model_id": self.model_id,
            "runtime": self.runtime,
            "inference_performed": self.inference_performed,
            "raw_response": self.raw_response,
            "validated_recommendation": self.validated_recommendation,
            "validation_errors": self.validation_errors,
            "blocker_reason": self.blocker_reason,
            "elapsed_seconds": self.elapsed_seconds,
            "label": "AI_RECOMMENDATION" if self.inference_performed else "NOT_VERIFIED",
        }


# ── Ollama helpers ────────────────────────────────────────────────────────────

def _ollama_available() -> bool:
    if _requests is None:
        return False
    try:
        r = _requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _find_gemma_model() -> Optional[str]:
    """Return name of first available Gemma model or None."""
    if _requests is None:
        return None
    try:
        r = _requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        if r.status_code != 200:
            return None
        models = r.json().get("models", [])
        for m in models:
            name = m.get("name", "")
            if GEMMA_PATTERN.search(name):
                return name
        return None
    except Exception:
        return None


def _call_ollama(model: str, prompt: str, timeout: int = 90) -> str:
    """Call Ollama generate endpoint. Returns raw text or raises."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    r = _requests.post(
        f"{OLLAMA_BASE}/api/generate",
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("response", "")


# ── Response validation ────────────────────────────────────────────────────────

REQUIRED_KEYS = {"rationale", "proposed_change", "confidence", "warnings"}


def _validate_response(parsed: dict, evidence_excerpt: str) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors = []
    missing = REQUIRED_KEYS - set(parsed.keys())
    if missing:
        errors.append(f"Missing required keys: {sorted(missing)}")
    conf = parsed.get("confidence")
    if conf is not None:
        try:
            c = float(conf)
            if not (0.0 <= c <= 1.0):
                errors.append(f"confidence must be 0.0–1.0, got {c}")
        except (TypeError, ValueError):
            errors.append(f"confidence must be numeric, got {conf!r}")
    proposed = str(parsed.get("proposed_change", ""))
    if len(proposed) < 10:
        errors.append("proposed_change is too short to be meaningful")
    # Reject recommendations that reference paths not in the evidence
    if "../" in proposed or proposed.startswith("/"):
        errors.append("proposed_change contains unsafe path reference")
    return errors


# ── Public interface ──────────────────────────────────────────────────────────

def _build_prompt(finding_dict: dict, evidence_excerpt: str) -> str:
    return f"""You are a Python dependency maintenance assistant.
Analyse the following maintenance finding and evidence, then reply with ONLY a JSON object.

FINDING:
Title: {finding_dict.get('title', '')}
Description: {finding_dict.get('description', '')[:600]}

EVIDENCE (truncated to {MAX_EVIDENCE_CHARS} chars):
{evidence_excerpt}

Reply with this exact JSON structure (no markdown, no extra text):
{{
  "rationale": "<one paragraph explaining the issue>",
  "proposed_change": "<specific file edits needed>",
  "confidence": <0.0-1.0>,
  "warnings": ["<any caveats or risks>"]
}}"""


def get_recommendation(finding_dict: dict, evidence_excerpt: str) -> ModelResult:
    """
    Attempt to get a Gemma recommendation via Ollama.

    Always returns a ModelResult. Never raises.
    """
    if not _ollama_available():
        return ModelResult(
            status="BLOCKED",
            blocker_reason=(
                "Ollama is not running or not reachable at localhost:11434. "
                "Start Ollama and pull a Gemma model: `ollama pull gemma:2b`"
            ),
        )

    model = _find_gemma_model()
    if model is None:
        return ModelResult(
            status="BLOCKED",
            model_id=None,
            blocker_reason=(
                "Ollama is running but no Gemma model is installed. "
                "Run: `ollama pull gemma:2b` or `ollama pull gemma3:1b`"
            ),
        )

    # Truncate evidence
    excerpt = evidence_excerpt[:MAX_EVIDENCE_CHARS]
    prompt = _build_prompt(finding_dict, excerpt)

    t0 = time.monotonic()
    try:
        raw = _call_ollama(model, prompt, timeout=90)
    except Exception as exc:
        return ModelResult(
            status="FAILED",
            model_id=model,
            blocker_reason=f"Inference call failed: {exc}",
            elapsed_seconds=round(time.monotonic() - t0, 2),
        )
    elapsed = round(time.monotonic() - t0, 2)

    # Parse JSON from response
    parsed = None
    # Try to extract JSON block even if surrounded by text
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    if parsed is None:
        return ModelResult(
            status="INVALID_RESPONSE",
            model_id=model,
            inference_performed=True,
            raw_response=raw[:500],
            validation_errors=["Response is not valid JSON"],
            elapsed_seconds=elapsed,
        )

    errors = _validate_response(parsed, excerpt)
    if errors:
        return ModelResult(
            status="INVALID_RESPONSE",
            model_id=model,
            inference_performed=True,
            raw_response=raw[:500],
            validated_recommendation=None,
            validation_errors=errors,
            elapsed_seconds=elapsed,
        )

    return ModelResult(
        status="SUCCESS",
        model_id=model,
        inference_performed=True,
        raw_response=raw[:500],
        validated_recommendation=parsed,
        elapsed_seconds=elapsed,
    )
