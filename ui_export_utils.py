"""Small helpers shared by UI export actions."""

import os

from PyQt6.QtWidgets import QFileDialog
from universal_core import ensure_runtime_dirs, runtime_data_dir

EXPORT_FILTER_SUFFIXES = (
    ("Excel", ".xlsx"),
    ("CSV", ".csv"),
    ("JSON", ".json"),
)


def selected_export_path(file_path, selected_filter):
    """Append the extension implied by a QFileDialog filter when needed."""
    if not file_path:
        return ""
    lower_path = file_path.lower()
    for label, suffix in EXPORT_FILTER_SUFFIXES:
        if selected_filter.startswith(label) and not lower_path.endswith(suffix):
            return file_path + suffix
    return file_path


def export_root_dir():
    """Return the default root directory for all export outputs."""
    ensure_runtime_dirs()
    save_mode = os.environ.get("UNIVERSAL_COLLECTOR_SAVE_MODE", "runtime")
    if save_mode == "project":
        project_root = os.environ.get("UNIVERSAL_COLLECTOR_PROJECT_ROOT", os.getcwd())
        path = os.path.join(project_root, "exports")
    else:
        path = os.path.join(runtime_data_dir(), "exports")
    os.makedirs(path, exist_ok=True)
    return path


def export_default_dir():
    """Alias for export_root_dir, kept for backward compatibility."""
    return export_root_dir()


def export_default_path(file_name):
    """Return the full path for a file name under the default export directory."""
    return os.path.join(export_root_dir(), file_name)
