"""Validate a deployment ZIP before a PowerShell script extracts it."""

from __future__ import annotations

import argparse

from bap_backend.deployment.artifact import validate_zip


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--component", required=True, choices=("backend", "deployment-scripts"))
    parser.add_argument("--expected-sha")
    args = parser.parse_args(argv)
    validate_zip(args.path, component=args.component, expected_sha=args.expected_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

