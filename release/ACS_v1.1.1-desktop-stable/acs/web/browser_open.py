"""Browser opener — cross-platform open file or URL in default browser."""
import os
import subprocess
import sys
import webbrowser


def open_browser(path_or_url: str):
    """Open a local HTML file or URL in the default browser.

    Args:
        path_or_url: Local file path or http(s) URL
    """
    if not path_or_url:
        return

    # If it's already a URL, use webbrowser directly
    if path_or_url.startswith(("http://", "https://")):
        webbrowser.open(path_or_url)
        return

    # Otherwise, resolve absolute path
    abs_path = os.path.abspath(path_or_url)

    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")

    # Use webbrowser for all platforms
    url = "file:///" + abs_path.replace("\\", "/")
    webbrowser.open(url)
