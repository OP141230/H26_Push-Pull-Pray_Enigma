"""Stage C: Model recommendation adapter."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from enigma.models import Finding, ModelRecommendation


def check_model_availability() -> dict[str, Any]:
    """Check if a local model runtime and Gemma model are available."""
    result = {
        "runtime_available": False,
        "runtime_name": "",
        "model_path": "",
        "model_name": "",
        "error": "",
    }

    # Check for llama-cpp-python
    try:
        import llama_cpp  # noqa: F401
        result["runtime_available"] = True
        result["runtime_name"] = "llama-cpp-python"
    except ImportError:
        result["error"] = "llama-cpp-python not installed"
        return result

    # Check for Gemma model files in common locations
    search_dirs = [
        Path.home() / ".cache" / "models",
        Path.home() / "models",
        Path.home() / ".local" / "share" / "models",
        Path(".") / "models",
    ]
    for d in search_dirs:
        if d.is_dir():
            for f in d.rglob("*gemma*"):
                if f.suffix in (".gguf", ".bin"):
                    result["model_path"] = str(f)
                    result["model_name"] = f.stem
                    return result

    result["error"] = "No Gemma model file found in standard locations"
    result["runtime_available"] = True  # runtime exists, model doesn't
    return result


def build_prompt(finding: Finding, repo_evidence: dict[str, Any]) -> str:
    """Build a structured prompt for the model."""
    evidence_text = ""
    for ev in finding.evidence:
        evidence_text += f"\n  File: {ev.file_path}"
        if ev.line_start:
            evidence_text += f" (line {ev.line_start})"
        evidence_text += f"\n  Content: {ev.snippet}"
        evidence_text += f"\n  Note: {ev.description}"

    return f"""You are a repository maintenance assistant. Analyze this finding and provide a structured recommendation.

FINDING:
  Title: {finding.title}
  Description: {finding.description}
  Classification: {finding.classification}
  Severity: {finding.severity.value}
  Confidence: {finding.confidence}

EVIDENCE:{evidence_text}

Declared dependencies: {repo_evidence.get('declared_deps', [])}
Imports found: {repo_evidence.get('imports_found', [])}

Respond in this exact JSON format:
{{
  "recommendation": "A brief recommendation (remove, keep, or update the dependency)",
  "reasoning": "Step-by-step reasoning based only on the evidence provided",
  "proposed_changes": [
    {{
      "file": "exact file path from evidence",
      "action": "remove_line or modify_line",
      "description": "what to change"
    }}
  ],
  "confidence": 0.7
}}

Only reference files and evidence that were explicitly provided. Do not hallucinate files or imports."""


def validate_recommendation(
    raw_response: str,
    finding: Finding,
    repo_evidence: dict[str, Any],
) -> tuple[ModelRecommendation, bool]:
    """Validate a model recommendation against the schema and evidence."""
    rec = ModelRecommendation(raw_response=raw_response)

    # Try to extract JSON from response
    try:
        # Try to find JSON in the response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        rec.validation_result = "INVALID_JSON"
        rec.error = "Could not parse JSON from model response"
        return rec, False

    # Validate required fields
    required = ["recommendation", "reasoning"]
    for field in required:
        if field not in data:
            rec.validation_result = "MISSING_FIELDS"
            rec.error = f"Missing required field: {field}"
            return rec, False

    rec.recommendation = data.get("recommendation", "")
    rec.reasoning = data.get("reasoning", "")
    rec.proposed_changes = data.get("proposed_changes", [])

    # Validate proposed changes reference real files
    known_files = set()
    for ev in finding.evidence:
        known_files.add(ev.file_path)
    for manifest_path in repo_evidence.get("manifests", {}).values():
        known_files.add(manifest_path)

    for change in rec.proposed_changes:
        file_ref = change.get("file", "")
        if file_ref and not any(file_ref in kf or kf.endswith(file_ref) for kf in known_files):
            rec.validation_result = "INVALID_FILE_REFERENCE"
            rec.error = f"Change references unknown file: {file_ref}"
            return rec, False

    rec.validation_result = "VALID"
    return rec, True


def get_recommendation(
    finding: Finding,
    repo_evidence: dict[str, Any],
) -> ModelRecommendation:
    """Attempt to get a real model recommendation."""
    availability = check_model_availability()

    if not availability["runtime_available"]:
        return ModelRecommendation(
            model_name="gemma",
            model_runtime="llama-cpp-python",
            inference_occurred=False,
            validation_result="BLOCKED",
            error=f"Runtime unavailable: {availability['error']}",
        )

    if not availability["model_path"]:
        return ModelRecommendation(
            model_name="gemma",
            model_runtime=availability["runtime_name"],
            inference_occurred=False,
            validation_result="BLOCKED",
            error=f"Model unavailable: {availability['error']}",
        )

    # Attempt real inference
    prompt = build_prompt(finding, repo_evidence)
    try:
        from llama_cpp import Llama
        model = Llama(model_path=availability["model_path"], n_ctx=2048, verbose=False)
        output = model(
            prompt,
            max_tokens=512,
            temperature=0.1,
            stop=["\n\n\n"],
        )
        response_text = output["choices"][0]["text"]
        rec, valid = validate_recommendation(response_text, finding, repo_evidence)
        rec.model_name = availability["model_name"]
        rec.model_runtime = availability["runtime_name"]
        rec.inference_occurred = True
        return rec
    except Exception as e:
        return ModelRecommendation(
            model_name=availability.get("model_name", "gemma"),
            model_runtime=availability["runtime_name"],
            inference_occurred=False,
            validation_result="BLOCKED",
            error=f"Inference failed: {type(e).__name__}: {e}",
        )
