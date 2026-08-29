# BAP Agent Guide

This file is part of the repository's agent harness. It helps agents locate relevant context and does not define BAP product requirements.

## Before Starting

- Read `openspec/goals/system.md` to understand the non-normative system vision.
- Check `openspec/` for current requirements and planned changes.
- Run `git status` before editing and preserve existing user changes.

## Harness Information Architecture and Authority

The repository harness separates Agent instructions, descriptive context, normative requirements, and proposed changes. Keep those responsibilities distinct.

| Location | Responsibility | Boundary |
|---|---|---|
| `AGENTS.md` | Repository-level Agent entry point, navigation map, and information-boundary rules | Must not contain product requirements, detailed domain knowledge, or implementation plans |
| `.codex/skills/` | Reusable Agent workflows and task-specific operating instructions | Must not become a source of BAP requirements or repository-specific domain facts |
| `docs/knowledge/` | Stable domain facts, concepts, formats, constraints, and explanations | Must not define BAP requirements, planned features, or implementation tasks |
| `docs/guides/` | Procedures that can be followed now, including setup, operation, verification, and troubleshooting | Must not describe future features, desired system behavior, or development plans |
| `docs/references/` | Original external source material such as vendor datasheets and manuals | Treat as evidence, not as BAP requirements; do not rewrite vendor material as project policy |
| `openspec/config.yaml` | OpenSpec bootstrap context that directs Agents to the repository harness | Keep it minimal; do not duplicate navigation, domain knowledge, or requirements from other sources |
| `openspec/goals/` | Non-normative system vision, purpose, intended users, and long-term direction | May reference `docs/`; must not contain formal requirements, scenarios, technical designs, or implementation tasks |
| `openspec/specs/` | Authoritative, normative requirements for system behavior | Describe observable behavior and avoid implementation task lists |
| `openspec/changes/` | Proposed requirement deltas, design decisions, and implementation tasks | Do not treat proposed behavior as current system behavior until the change is completed and archived |

When harness information conflicts, identify the conflict explicitly. Do not copy future plans into `docs/`, and do not infer normative system requirements solely from guides or references.

## Where to Look

| Problem or task | Location |
|---|---|
| System-independent domain knowledge and procedures | `docs/` |
| Non-normative system vision and goals | `openspec/goals/` |
| IMU domain knowledge and vendor references | `docs/knowledge/imu/` and `docs/references/imu/` |
| IMU setup and troubleshooting procedures | `docs/guides/imu/` |
| IMU communication and data collection | `anrot_imu_driver/` |
| Command-line operations | `anrot_imu_driver/commands/` |
| Sensor data parsing | `anrot_imu_driver/parsers/` |
| Requirements, designs, and implementation plans | `openspec/` |
| Automated verification | `tests/` |

## Repository Rules

- Treat `ANROT-IMU-v1.3.6-windows-x64/` as vendor material unless explicitly asked to modify it.
- Do not assume documentation and implementation agree; verify behavior in code and tests.
