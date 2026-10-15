"""Tests for enigma.model_adapter — Stage C: Model recommendation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from enigma.model_adapter import (
    ModelResult,
    _validate_response,
    get_recommendation,
)

VALID_FINDING = {
    "finding_id": "FND-ABCD1234",
    "title": "Pydantic v1/v2 conflict",
    "description": "pydantic>=2 declared but pydantic==1.10.13 pinned",
}

VALID_MODEL_RESPONSE = {
    "rationale": "The project declares pydantic>=2 but pins v1 in requirements. config.py uses removed v1 API.",
    "proposed_change": "Update requirements.txt to pydantic>=2,<3 and migrate config.py to field_validator.",
    "confidence": 0.92,
    "warnings": ["Ensure all tests pass after migration"],
}


class TestValidateResponse:
    def test_valid_response_passes(self):
        errors = _validate_response(VALID_MODEL_RESPONSE, "some evidence")
        assert errors == []

    def test_missing_key_fails(self):
        bad = dict(VALID_MODEL_RESPONSE)
        del bad["rationale"]
        errors = _validate_response(bad, "evidence")
        assert any("rationale" in e for e in errors)

    def test_confidence_out_of_range_fails(self):
        bad = dict(VALID_MODEL_RESPONSE)
        bad["confidence"] = 1.5
        errors = _validate_response(bad, "evidence")
        assert any("confidence" in e for e in errors)

    def test_non_numeric_confidence_fails(self):
        bad = dict(VALID_MODEL_RESPONSE)
        bad["confidence"] = "high"
        errors = _validate_response(bad, "evidence")
        assert any("confidence" in e for e in errors)

    def test_short_proposed_change_fails(self):
        bad = dict(VALID_MODEL_RESPONSE)
        bad["proposed_change"] = "fix it"
        errors = _validate_response(bad, "evidence")
        assert any("short" in e.lower() or "proposed" in e.lower() for e in errors)

    def test_unsafe_path_in_proposed_change_fails(self):
        bad = dict(VALID_MODEL_RESPONSE)
        bad["proposed_change"] = "../etc/passwd — replace pydantic"
        errors = _validate_response(bad, "evidence")
        assert any("unsafe" in e.lower() or "path" in e.lower() for e in errors)


class TestGetRecommendation:
    def test_returns_blocked_when_ollama_unavailable(self):
        with patch("enigma.model_adapter._ollama_available", return_value=False):
            result = get_recommendation(VALID_FINDING, "evidence text")
        assert result.status == "BLOCKED"
        assert result.inference_performed is False
        assert result.blocker_reason is not None

    def test_returns_blocked_when_no_gemma_model(self):
        with patch("enigma.model_adapter._ollama_available", return_value=True), \
             patch("enigma.model_adapter._find_gemma_model", return_value=None):
            result = get_recommendation(VALID_FINDING, "evidence text")
        assert result.status == "BLOCKED"
        assert "gemma" in result.blocker_reason.lower()

    def test_returns_invalid_when_response_not_json(self):
        with patch("enigma.model_adapter._ollama_available", return_value=True), \
             patch("enigma.model_adapter._find_gemma_model", return_value="gemma:2b"), \
             patch("enigma.model_adapter._call_ollama", return_value="not json at all"):
            result = get_recommendation(VALID_FINDING, "evidence text")
        assert result.status == "INVALID_RESPONSE"
        assert result.inference_performed is True

    def test_returns_success_with_valid_response(self):
        raw = json.dumps(VALID_MODEL_RESPONSE)
        with patch("enigma.model_adapter._ollama_available", return_value=True), \
             patch("enigma.model_adapter._find_gemma_model", return_value="gemma:2b"), \
             patch("enigma.model_adapter._call_ollama", return_value=raw):
            result = get_recommendation(VALID_FINDING, "evidence text")
        assert result.status == "SUCCESS"
        assert result.inference_performed is True
        assert result.validated_recommendation is not None

    def test_returns_failed_on_inference_exception(self):
        with patch("enigma.model_adapter._ollama_available", return_value=True), \
             patch("enigma.model_adapter._find_gemma_model", return_value="gemma:2b"), \
             patch("enigma.model_adapter._call_ollama", side_effect=ConnectionError("refused")):
            result = get_recommendation(VALID_FINDING, "evidence text")
        assert result.status == "FAILED"
        assert result.inference_performed is False

    def test_model_result_to_dict(self):
        result = ModelResult(status="BLOCKED", blocker_reason="no ollama")
        d = result.to_dict()
        assert d["status"] == "BLOCKED"
        assert d["inference_performed"] is False
        assert d["label"] == "NOT_VERIFIED"

    def test_successful_model_result_label(self):
        result = ModelResult(
            status="SUCCESS",
            model_id="gemma:2b",
            inference_performed=True,
            validated_recommendation=VALID_MODEL_RESPONSE,
        )
        d = result.to_dict()
        assert d["label"] == "AI_RECOMMENDATION"
