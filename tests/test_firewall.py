"""Firewall test — the leakage firewall (scientific integrity rule 0.1).

The injection manifest MUST NOT influence narrator grades, chain grading, or
routing decisions. Two layers of protection, tested here:

1. **Import edge** — no module in the shipped `isnad` package imports the
   experiment's `ground_truth` module.
2. **Field level** — the experiment's *grading/gating* modules (`calibrate.py`,
   `run.py`) may read only the audit verdict (`corrupted`), never the manifest
   fields (`responsible_narrator`, `fault_type`, `original_text`) that reveal
   *who* injected *what*. Those are reserved for `inject.py` (the writer) and
   metric/reporting code.
"""

from __future__ import annotations

import ast
import os

FIREWALL_MODULE = "ground_truth"

# The manifest fields that would leak injection ground truth into grading.
_MANIFEST_FIELDS = ("responsible_narrator", "fault_type", "original_text")

# Grading/gating modules that may import ground_truth but must read only the
# audit verdict (`corrupted`), not the manifest fields.
_GRADING_MODULES = ["calibrate.py", "run.py"]

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXP_DIR = os.path.join(_REPO_ROOT, "experiments", "s8_gated_vs_ungated")


def _collect_package_modules(package_dir: str) -> set[str]:
    modules: set[str] = set()
    for root, _, files in os.walk(package_dir):
        for f in files:
            if f.endswith(".py"):
                modules.add(os.path.relpath(os.path.join(root, f), package_dir))
    return modules


def _find_imports(filepath: str) -> set[str]:
    imports: set[str] = set()
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read())
    except SyntaxError:
        return imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def test_shipped_package_never_imports_ground_truth() -> None:
    """No module in src/isnad may import the injection manifest."""
    isnad_dir = os.path.join(_REPO_ROOT, "src", "isnad")
    violators = [
        mod
        for mod in _collect_package_modules(isnad_dir)
        if FIREWALL_MODULE in _find_imports(os.path.join(isnad_dir, mod))
    ]
    assert not violators, f"src/isnad modules must never import {FIREWALL_MODULE!r}: {violators}"


def test_grading_modules_read_only_the_audit_verdict() -> None:
    """calibrate.py / run.py may read `corrupted`, but never the manifest fields
    that reveal which narrator injected which fault (that would leak the
    injection ground truth into grading)."""
    violators: list[str] = []
    for mod_name in _GRADING_MODULES:
        full_path = os.path.join(_EXP_DIR, mod_name)
        if not os.path.exists(full_path):
            continue
        with open(full_path) as f:
            source = f.read()
        for field in _MANIFEST_FIELDS:
            if field in source:
                violators.append(f"{mod_name}: {field}")
    assert not violators, (
        "FIREWALL VIOLATION — grading/gating modules must not read manifest "
        f"fields ({', '.join(_MANIFEST_FIELDS)}):\n" + "\n  ".join(violators)
    )
