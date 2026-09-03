"""One change-scope policy shared by PR CI and CD."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath


_DOC_ROOTS = {"docs", "openspec"}
_DOC_FILES = {"README.md", "AGENTS.md"}
_BACKEND_ROOTS = {"bap_backend", "migrations"}
_DESKTOP_ROOTS = {"bap_desktop", "packaging"}
_SHARED_ROOTS = {"bap_common", "anrot_imu_driver"}
_SHARED_FILES = {"pyproject.toml", "uv.lock", ".python-version"}


@dataclass(frozen=True)
class ChangeScope:
    docs_only: bool
    backend_changed: bool
    desktop_changed: bool

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


def classify_paths(paths: list[str]) -> ChangeScope:
    normalized = [PurePosixPath(path.replace("\\", "/")) for path in paths if path.strip()]
    if not normalized:
        return ChangeScope(docs_only=True, backend_changed=False, desktop_changed=False)
    backend = desktop = False
    only_docs = True
    for path in normalized:
        root = path.parts[0]
        text = path.as_posix()
        is_doc = root in _DOC_ROOTS or text in _DOC_FILES
        only_docs = only_docs and is_doc
        if is_doc:
            continue
        if (
            root in _BACKEND_ROOTS
            or text.startswith("deployment/windows/backend/")
            or text.startswith("tests/backend/")
        ):
            backend = True
        elif root in _DESKTOP_ROOTS or text.startswith("tests/desktop/"):
            desktop = True
        elif root in _SHARED_ROOTS or text in _SHARED_FILES:
            backend = desktop = True
        elif root == ".github":
            backend = desktop = True
        else:
            backend = desktop = True
    return ChangeScope(docs_only=only_docs, backend_changed=backend, desktop_changed=desktop)
