"""Small cross-platform process helpers used by the update bootstrap."""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from pathlib import Path
from typing import Sequence


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    process_query_limited_information = 0x1000
    still_active = 259
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def wait_for_process_exit(pid: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while process_is_running(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


def terminate_process(pid: int) -> None:
    if not process_is_running(pid):
        return
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, pid)
        if handle:
            try:
                ctypes.windll.kernel32.TerminateProcess(handle, 1)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        return
    os.kill(pid, 15)


def spawn_detached(command: Sequence[str], *, cwd: Path | None = None) -> subprocess.Popen:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    return subprocess.Popen(
        list(command),
        cwd=str(cwd) if cwd else None,
        close_fds=True,
        creationflags=creationflags,
    )
