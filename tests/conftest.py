"""Pytest configuration for deterministic Tk cleanup and Windows Tcl init resilience."""

import gc
import sys
import time
import tkinter as tk

import pytest


def _is_transient_windows_tcl_init_error(exc: BaseException) -> bool:
    """Return True when Windows Tcl raises the transient init.tcl 'No error' race."""
    if sys.platform != "win32" or not isinstance(exc, tk.TclError):
        return False
    msg = str(exc).lower()
    return "init.tcl" in msg and "no error" in msg


@pytest.fixture(autouse=True)
def _collect_tk_garbage_after_test():
    """Flush Tk Variable/Font/PhotoImage finalizers right after each test."""
    yield
    gc.collect()


@pytest.fixture(autouse=True, scope="session")
def _guard_windows_tcl_init():
    """Retry tk.Tcl() on the transient Windows Python 3.11 init.tcl handle race."""
    if sys.platform != "win32":
        yield
        return

    original_tcl = tk.Tcl

    def _safe_tcl(*args, **kwargs):
        for attempt in range(5):
            try:
                return original_tcl(*args, **kwargs)
            except tk.TclError as exc:
                if attempt == 4 or not _is_transient_windows_tcl_init_error(exc):
                    raise
                gc.collect()
                time.sleep(0.05 * (attempt + 1))

    tk.Tcl = _safe_tcl
    try:
        yield
    finally:
        tk.Tcl = original_tcl
