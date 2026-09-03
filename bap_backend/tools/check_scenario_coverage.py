"""Check that every Scenario in one active OpenSpec Change is linked to pytest."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


SCENARIO = re.compile(r"^#### Scenario:\s*(.+?)\s*$", re.MULTILINE)


def collect_active_scenarios(root: Path, change: str) -> set[tuple[str, str]]:
    scenarios: set[tuple[str, str]] = set()
    specs = root / "openspec" / "changes" / change / "specs"
    for spec in specs.glob("*/spec.md"):
        capability = spec.parent.name
        for name in SCENARIO.findall(spec.read_text(encoding="utf-8")):
            scenarios.add((capability, name))
    return scenarios


def collect_pytest_markers(root: Path) -> set[tuple[str, str]]:
    markers: set[tuple[str, str]] = set()
    for path in (root / "tests").rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            function = node.func
            if not isinstance(function, ast.Attribute) or function.attr != "scenario":
                continue
            capability, scenario = node.args[:2]
            if isinstance(capability, ast.Constant) and isinstance(capability.value, str) and isinstance(scenario, ast.Constant) and isinstance(scenario.value, str):
                markers.add((capability.value, scenario.value))
    return markers


def missing_scenarios(root: Path, change: str) -> set[tuple[str, str]]:
    return collect_active_scenarios(root, change) - collect_pytest_markers(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--change", required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    missing = sorted(missing_scenarios(root, args.change))
    if missing:
        for capability, scenario in missing:
            print(f"{capability}: {scenario}")
        return 1
    print(f"Every Scenario in {args.change} has a pytest marker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
