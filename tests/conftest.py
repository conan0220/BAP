from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from helpers import (
    build_gateway_frame,
    build_hi81_frame,
    build_hi91_frame,
    build_hi92_frame,
    build_nmea_sentence,
)


SCENARIO_PATTERN = re.compile(r"^#### Scenario: (.+)$", re.MULTILINE)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--scenario-spec-root",
        action="store",
        default=None,
        help="Audit collected scenario markers against OpenSpec files below this path.",
    )


def pytest_collection_finish(session: pytest.Session) -> None:
    spec_root_option = session.config.getoption("--scenario-spec-root")
    if not spec_root_option:
        return

    spec_root = Path(spec_root_option)
    expected: set[tuple[str, str]] = set()
    for spec_path in spec_root.rglob("spec.md"):
        capability = spec_path.parent.name
        text = spec_path.read_text(encoding="utf-8")
        expected.update((capability, name) for name in SCENARIO_PATTERN.findall(text))

    covered: set[tuple[str, str]] = set()
    for item in session.items:
        for marker in item.iter_markers("scenario"):
            if len(marker.args) != 2 or not all(isinstance(value, str) for value in marker.args):
                raise pytest.UsageError(
                    f"Invalid scenario marker on {item.nodeid}; expected capability and Scenario name."
                )
            covered.add((marker.args[0], marker.args[1]))

    missing = sorted(expected - covered)
    unknown = sorted(covered - expected)
    errors = []
    if missing:
        errors.append("Uncovered Scenarios:\n" + "\n".join(f"  {capability} :: {name}" for capability, name in missing))
    if unknown:
        errors.append("Unknown Scenario markers:\n" + "\n".join(f"  {capability} :: {name}" for capability, name in unknown))
    if errors:
        raise pytest.UsageError("\n".join(errors))


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def hi91_frame() -> bytes:
    return build_hi91_frame()


@pytest.fixture
def hi92_frame() -> bytes:
    return build_hi92_frame()


@pytest.fixture
def hi81_frame() -> bytes:
    return build_hi81_frame()


@pytest.fixture
def gateway_frame() -> bytes:
    return build_gateway_frame()


@pytest.fixture
def nmea_sentence_factory():
    return build_nmea_sentence
