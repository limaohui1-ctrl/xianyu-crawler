"""Tests: runtime data must be gitignored — logs, shadow logs, exports, reports."""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_gitignore():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".gitignore")
    with open(path) as f:
        return f.read()


def test_gitignore_covers_logs():
    gi = _read_gitignore()
    assert "logs/" in gi, "logs/ must be gitignored"


def test_gitignore_covers_shadow_logs():
    gi = _read_gitignore()
    assert "acs_shadow_logs/" in gi, "acs_shadow_logs/ must be gitignored"


def test_gitignore_covers_acs_data():
    gi = _read_gitignore()
    assert "acs_data/" in gi, "acs_data/ must be gitignored"


def test_gitignore_covers_reports():
    gi = _read_gitignore()
    assert "reports/" in gi, "reports/ must be gitignored"


def test_gitignore_covers_env():
    gi = _read_gitignore()
    assert "\n.env\n" in gi or gi.endswith(".env\n"), ".env must be gitignored"


def test_gitignore_no_typo_envreports():
    gi = _read_gitignore()
    assert "envreports" not in gi, ".envreports typo must be fixed"


def test_examples_not_gitignored():
    """Example files should be tracked in git for new users."""
    gi = _read_gitignore()
    lines = [l.strip() for l in gi.split("\n") if l.strip() and not l.startswith("#")]
    for line in lines:
        assert "examples" not in line, f"examples/ should NOT be in .gitignore: '{line}'"
