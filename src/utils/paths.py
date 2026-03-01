"""
Path resolution helper for frozen (PyInstaller) and source execution.

When running from source:
    app root = project directory (parent of src/)

When running as a PyInstaller --onedir exe:
    app root = the folder containing the exe (parent of _internal/)

Usage:
    from src.utils.paths import get_app_root
    runs_dir = os.path.join(get_app_root(), "runs")
"""

import os
import sys


def get_app_root() -> str:
    """
    Return the application root directory.

    Works identically whether running from source or from a
    PyInstaller-frozen executable.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller --onedir: sys.executable is  dist/ALU Timer/ALU Timer.exe
        # We want the folder containing the exe.
        return os.path.dirname(sys.executable)
    else:
        # Running from source: this file is  src/utils/paths.py
        # App root is two levels up.
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
