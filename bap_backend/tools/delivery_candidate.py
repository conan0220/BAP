"""CLI used by GitHub Actions to create, classify, and validate BAP Candidates."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from bap_backend.deployment.scope import classify_paths


def _git(git_path: str, *args: str) -> str:
    return subprocess.check_output([git_path, *args], text=True).strip()


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise argparse.ArgumentTypeError("expected true or false")
    return normalized == "true"


def _reference(path: Path | None) -> ArtifactReference | None:
    from bap_backend.deployment.artifact import sha256_file
    from bap_backend.deployment.manifest import ArtifactReference
    if path is None:
        return None
    if not path.is_file():
        raise ValueError(f"Candidate artifact does not exist: {path}")
    return ArtifactReference(filename=path.name, sha256=sha256_file(path))


def _write_github_output(path: Path | None, values: dict[str, object]) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            stream.write(f"{key}={rendered}\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-path", default="git")
    commands = parser.add_subparsers(dest="command", required=True)

    scope = commands.add_parser("scope")
    scope.add_argument("--base", required=True)
    scope.add_argument("--head", required=True)
    scope.add_argument("--github-output", type=Path)

    tree = commands.add_parser("tree")
    tree.add_argument("--ref", default="HEAD")

    create = commands.add_parser("create")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--pr-number", type=int, required=True)
    create.add_argument("--pr-head-sha", required=True)
    create.add_argument("--pr-base-sha", required=True)
    create.add_argument("--ci-test-commit-sha", required=True)
    create.add_argument("--source-tree-sha", required=True)
    create.add_argument("--ci-run-id", type=int, required=True)
    create.add_argument("--ci-url", required=True)
    create.add_argument("--docs-only", type=_bool, required=True)
    create.add_argument("--backend-changed", type=_bool, required=True)
    create.add_argument("--desktop-changed", type=_bool, required=True)
    create.add_argument("--backend-artifact", type=Path)
    create.add_argument("--desktop-artifact", type=Path)
    create.add_argument("--test", action="append", default=[])

    validate = commands.add_parser("validate")
    validate.add_argument("--candidate-dir", type=Path, required=True)
    validate.add_argument("--expected-tree", required=True)
    validate.add_argument("--github-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "tree":
        print(_git(args.git_path, "rev-parse", f"{args.ref}^{{tree}}").lower())
        return 0

    if args.command == "scope":
        paths = _git(args.git_path, "diff", "--name-only", args.base, args.head).splitlines()
        result = classify_paths(paths).as_dict()
        _write_github_output(args.github_output, result)
        print(json.dumps(result, sort_keys=True))
        return 0

    if args.command == "create":
        from bap_backend.deployment.manifest import DeliveryManifest

        tests: dict[str, str] = {}
        for item in args.test:
            if "=" not in item:
                raise ValueError("--test must use NAME=RESULT")
            name, result = item.split("=", 1)
            if not name or result != "passed":
                raise ValueError("Candidate may contain only named passed tests")
            tests[name] = result
        backend = _reference(args.backend_artifact)
        desktop = _reference(args.desktop_artifact)
        if args.docs_only:
            if args.backend_changed or args.desktop_changed or backend or desktop:
                raise ValueError("docs-only Candidate cannot contain delivery artifacts")
        elif backend is None or desktop is None:
            raise ValueError("a non-docs Candidate must contain Backend and Desktop artifacts")
        manifest = DeliveryManifest(
            project="BAP",
            pr_number=args.pr_number,
            pr_head_sha=args.pr_head_sha,
            pr_base_sha=args.pr_base_sha,
            ci_test_commit_sha=args.ci_test_commit_sha,
            source_tree_sha=args.source_tree_sha,
            ci_workflow_run_id=args.ci_run_id,
            ci_workflow_url=args.ci_url,
            created_at=datetime.now(UTC),
            docs_only=args.docs_only,
            backend_changed=args.backend_changed,
            desktop_changed=args.desktop_changed,
            backend=backend,
            desktop=desktop,
            tests=tests,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        print(args.output)
        return 0

    from bap_backend.deployment.artifact import validate_candidate

    manifest = validate_candidate(args.candidate_dir, expected_source_tree_sha=args.expected_tree)
    values = {
        "docs_only": manifest.docs_only,
        "backend_changed": manifest.backend_changed,
        "desktop_changed": manifest.desktop_changed,
        "pr_number": manifest.pr_number,
        "ci_run_id": manifest.ci_workflow_run_id,
        "source_tree_sha": manifest.source_tree_sha,
        "backend_filename": manifest.backend.filename if manifest.backend else "",
        "desktop_filename": manifest.desktop.filename if manifest.desktop else "",
    }
    _write_github_output(args.github_output, values)
    print(manifest.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
