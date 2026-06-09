"""Small helpers shared by UI export actions."""

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
