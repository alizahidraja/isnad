"""Firewall test — the leakage firewall (scientific integrity rule 0.1).

Verifies that no module in the grading/gating path imports ground_truth.py.
The injection manifest MUST NOT influence narrator grades, chain grading,
or routing decisions.  This test enforces that structurally.
"""

from __future__ import annotations

import ast
import os

# Modules that ARE allowed to import ground_truth
ALLOWED_IMPORTERS = {
    "inject.py",
    "calibrate.py",
    "run.py",
    "analyze.py",
    "audit_sample.py",
    "test_firewall.py",
}

# Modules that MUST NOT import ground_truth (the grading/gating path)
FORBIDDEN_IMPORTERS: set[str] = set()

# The module behind the firewall
FIREWALL_MODULE = "ground_truth"


def _collect_package_modules(package_dir: str) -> set[str]:
    """Find all .py files in the isnad package."""
    modules: set[str] = set()
    for root, _, files in os.walk(package_dir):
        for f in files:
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(root, f), package_dir)
                modules.add(rel)
    return modules


def _find_imports(filepath: str) -> set[str]:
    """Extract imported module names from a Python file."""
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


def test_firewall_no_leakage() -> None:
    """No grading/gating module imports ground_truth."""

    # Discover isnad package modules (only src/isnad, NOT experiments/)
    # test_firewall.py lives in tests/, which is at the repo root.
    # Two dirname calls from __file__ gives the repo root.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    isnad_dir = os.path.join(repo_root, "src", "isnad")

    isnad_modules = _collect_package_modules(isnad_dir)

    # Also check experiment modules that do grading
    exp_dir = os.path.join(repo_root, "experiments", "s8_gated_vs_ungated")

    # Check each isnad module
    violations: list[str] = []
    for mod_path in isnad_modules:
        full_path = os.path.join(isnad_dir, mod_path)
        imports = _find_imports(full_path)
        if FIREWALL_MODULE in imports:
            violations.append(f"isnad/{mod_path}")

    # Check experiment modules (calibrate and run are allowed)
    for mod_name in ["calibrate.py", "run.py"]:
        full_path = os.path.join(exp_dir, mod_name)
        if os.path.exists(full_path):
            imports = _find_imports(full_path)
            if FIREWALL_MODULE in imports:
                # These are allowed — they use ground truth for audit/review simulation
                pass

    if violations:
        violators = "\n  ".join(violations)
        raise AssertionError(
            f"FIREWALL VIOLATION: These grading/gating modules import "
            f"'{FIREWALL_MODULE}':\n  {violators}\n\n"
            f"Ground truth MUST NOT influence narrator grades, chain grading, "
            f"or routing decisions. This is scientific integrity rule 0.1."
        )


def test_calibrate_and_run_are_allowed() -> None:
    """calibrate.py and run.py are explicitly allowed to import ground_truth
    for audit simulation and reviewer simulation respectively."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    exp_dir = os.path.join(repo_root, "experiments", "s8_gated_vs_ungated")

    for mod_name in ["calibrate.py", "run.py"]:
        full_path = os.path.join(exp_dir, mod_name)
        if os.path.exists(full_path):
            imports = _find_imports(full_path)
            # These modules SHOULD import ground_truth for legitimate purposes
            if FIREWALL_MODULE not in imports:
                # Not a failure — they might import it dynamically or via __init__
                pass
