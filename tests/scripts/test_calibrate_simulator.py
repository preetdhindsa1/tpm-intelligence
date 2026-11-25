"""scripts/calibrate_simulator.py works for any project, and never borrows another
project's validation (ADR-0012, ADR-0018)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "calibrate_simulator", ROOT / "scripts" / "calibrate_simulator.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check(name: str, passed: bool) -> dict[str, object]:
    return {"name": name, "real": 1.0, "simulated": 1.1, "error": 0.1, "passed": passed}


def test_release_key_defaults_to_kubernetes_and_keeps_project_keys() -> None:
    s = _script()
    assert s.release_key("v1.38") == "kubernetes:v1.38"
    assert s.release_key("KAFKA:4.5.0") == "KAFKA:4.5.0"


def test_validation_is_per_project(tmp_path: Path) -> None:
    s = _script()
    run = {
        "passed": False,
        "measured_at": "2026-11-22T15:04:30+00:00",
        "tolerance": 0.2,
        "releases": [
            {"release": "kubernetes:v1.37", "passed": False, "checks": [_check("wait", False)]},
            {"release": "kubernetes:v1.38", "passed": False, "checks": [_check("wait", False)]},
        ],
    }
    (tmp_path / "sim-validation-20261122T150430Z.json").write_text(json.dumps(run))
    kube = s.validation_summary("kubernetes", tmp_path)
    assert kube["passed"] is False
    assert [r["release"] for r in kube["releases"]] == ["kubernetes:v1.37", "kubernetes:v1.38"]
    kafka = s.validation_summary("KAFKA", tmp_path)
    assert kafka == {
        "passed": False,
        "reason": "no replay validation has been run for KAFKA yet",
        "releases": [],
    }
