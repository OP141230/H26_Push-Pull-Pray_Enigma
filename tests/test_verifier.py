"""Tests for enigma.verifier — Stage E: Command execution and verification."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from enigma.verifier import run_check


class TestRunCheck:
    def test_successful_command(self, tmp_path):
        result = run_check(
            label="echo_test",
            command=[sys.executable, "-c", "print('hello')"],
            cwd=str(tmp_path),
        )
        assert result.status == "PASS"
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_nonzero_exit_code_is_fail(self, tmp_path):
        result = run_check(
            label="fail_test",
            command=[sys.executable, "-c", "import sys; sys.exit(1)"],
            cwd=str(tmp_path),
        )
        assert result.status == "FAIL"
        assert result.exit_code == 1

    def test_missing_executable(self, tmp_path):
        result = run_check(
            label="missing_exe",
            command=["nonexistent_binary_xyz123", "--version"],
            cwd=str(tmp_path),
        )
        assert result.status == "MISSING_EXECUTABLE"
        assert result.exit_code is None

    def test_missing_cwd_returns_error(self, tmp_path):
        result = run_check(
            label="bad_cwd",
            command=[sys.executable, "-c", "pass"],
            cwd=str(tmp_path / "nonexistent"),
        )
        assert result.status == "ERROR"

    def test_timeout_is_captured(self, tmp_path):
        result = run_check(
            label="timeout_test",
            command=[sys.executable, "-c", "import time; time.sleep(10)"],
            cwd=str(tmp_path),
            timeout=1,
        )
        assert result.status == "TIMEOUT"

    def test_output_is_captured(self, tmp_path):
        result = run_check(
            label="output_test",
            command=[sys.executable, "-c", "print('captured output')"],
            cwd=str(tmp_path),
        )
        assert "captured output" in result.stdout

    def test_stderr_captured(self, tmp_path):
        result = run_check(
            label="stderr_test",
            command=[sys.executable, "-c", "import sys; sys.stderr.write('err msg')"],
            cwd=str(tmp_path),
        )
        assert "err msg" in result.stderr

    def test_to_dict_has_required_keys(self, tmp_path):
        result = run_check(
            label="dict_test",
            command=[sys.executable, "-c", "pass"],
            cwd=str(tmp_path),
        )
        d = result.to_dict()
        required = {"label", "command", "cwd", "interpreter", "exit_code",
                    "status", "elapsed_seconds"}
        assert required.issubset(d.keys())

    def test_elapsed_seconds_recorded(self, tmp_path):
        result = run_check(
            label="time_test",
            command=[sys.executable, "-c", "pass"],
            cwd=str(tmp_path),
        )
        assert result.elapsed_seconds is not None
        assert result.elapsed_seconds >= 0

    def test_started_at_recorded(self, tmp_path):
        result = run_check(
            label="time_test2",
            command=[sys.executable, "-c", "pass"],
            cwd=str(tmp_path),
        )
        assert result.started_at is not None
