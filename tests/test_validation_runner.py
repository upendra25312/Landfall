"""The validation runner must retain failures, timeouts, and skipped-test evidence."""
import importlib.util
from pathlib import Path
import subprocess
import sys

from conftest import ROOT

spec = importlib.util.spec_from_file_location("system_validation", Path(ROOT) / "scripts/validate_system.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_failed_gate_retains_exit_status_and_log(tmp_path):
    result = runner.run_gate("failure", [sys.executable, "-c", "print('regression'); raise SystemExit(7)"], tmp_path)
    assert result["status"] == "FAIL" and result["exit_code"] == 7
    assert "regression" in (tmp_path / "failure.log").read_text()


def test_timeout_is_not_pass_and_stale_xml_is_not_reused(tmp_path, monkeypatch):
    (tmp_path / "timeout.xml").write_text('<testsuites><testcase name="old"/></testsuites>')
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("test", 1)
    monkeypatch.setattr(runner.subprocess, "run", timeout)
    result = runner.run_gate("timeout", ["test"], tmp_path)
    assert result["status"] == "TIMEOUT" and "tests" not in result


def test_missing_executable_is_blocked(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("missing tool")
    monkeypatch.setattr(runner.subprocess, "run", missing)
    result = runner.run_gate("missing", ["test"], tmp_path)
    assert result["status"] == "BLOCKED"
