"""Create or validate a Backend deployment-manifest.json."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from bap_backend.deployment import DeploymentManifest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--output", type=Path)
    result.add_argument("--validate", type=Path)
    result.add_argument("--component", choices=("backend",))
    result.add_argument("--commit-sha")
    result.add_argument("--source-tree-sha")
    result.add_argument("--version")
    result.add_argument("--python-requires", default=">=3.12,<3.13")
    result.add_argument("--entry-point", default="bap_backend.app.main:app")
    result.add_argument("--alembic-revision", default="0001_initial")
    result.add_argument("--file", action="append", default=[])
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.validate:
        DeploymentManifest.model_validate_json(args.validate.read_text(encoding="utf-8"))
        return 0
    required = (args.output, args.component, args.commit_sha, args.source_tree_sha, args.version)
    if any(value is None for value in required):
        raise SystemExit("--output, --component, --commit-sha, --source-tree-sha, and --version are required")
    manifest = DeploymentManifest(
        project="BAP",
        component=args.component,
        commit_sha=args.commit_sha,
        source_tree_sha=args.source_tree_sha,
        version=args.version,
        created_at=datetime.now(UTC),
        python_requires=args.python_requires,
        application_entry_point=args.entry_point,
        alembic_revision=args.alembic_revision,
        files=sorted(set(args.file)),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
