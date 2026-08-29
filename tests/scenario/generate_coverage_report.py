"""Generate a human-readable report from exact pytest scenario markers."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


SCENARIO = re.compile(r"^#### Scenario: (.+)$", re.MULTILINE)


def marked_scenarios(test_root: Path) -> set[tuple[str, str]]:
    covered: set[tuple[str, str]] = set()
    for path in test_root.rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or len(decorator.args) != 2:
                    continue
                if not isinstance(decorator.func, ast.Attribute) or decorator.func.attr != "scenario":
                    continue
                values = [arg.value for arg in decorator.args if isinstance(arg, ast.Constant)]
                if len(values) == 2 and all(isinstance(value, str) for value in values):
                    covered.add((values[0], values[1]))
    return covered


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-root", type=Path, required=True)
    parser.add_argument("--test-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    expected: set[tuple[str, str]] = set()
    for path in args.spec_root.rglob("spec.md"):
        expected.update((path.parent.name, name) for name in SCENARIO.findall(path.read_text(encoding="utf-8")))
    covered = marked_scenarios(args.test_root)
    rows = []
    for capability, name in sorted(expected):
        rows.append(f"| {capability} | {name} | {'已覆蓋' if (capability, name) in covered else '未覆蓋'} |")
    missing = expected - covered
    report = "\n".join(
        [
            "# Prototype Scenario Coverage",
            "",
            "## 名詞定義",
            "",
            "| 名詞 | 定義 |",
            "|---|---|",
            "| Scenario | OpenSpec 中可驗證的一個系統情境。 |",
            "| 已覆蓋 | 至少有一個 automated test 使用 capability 與 Scenario 完整名稱標記。 |",
            "",
            "## 摘要",
            "",
            f"- Scenarios：{len(expected)}",
            f"- 已覆蓋：{len(expected) - len(missing)}",
            f"- 未覆蓋：{len(missing)}",
            "",
            "## 明細",
            "",
            "| Capability | Scenario | 狀態 |",
            "|---|---|---|",
            *rows,
            "",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

