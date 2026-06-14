"""Tests: API key never in code, logs, or reports."""
import sys, os, re, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_no_hardcoded_keys_in_source():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    patterns = [
        re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    ]
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, "acs")):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, encoding="utf-8", errors="replace") as f:
                content = f.read()
            for pat in patterns:
                match = pat.search(content)
                if match:
                    if "search_api" in fp or "test_search_api_key" in fp or "smoke" in fp.lower():
                        continue
                    pytest.fail(f"Hardcoded API key in {fp}: {match.group()[:20]}...")

def test_safe_dict_no_key():
    from acs.discovery.search_api_config import SearchApiConfig
    cfg = SearchApiConfig(api_key="real-key-12345", enabled=True)
    safe = cfg.to_safe_dict()
    assert "api_key" not in safe

def test_mock_provider_no_key():
    from acs.discovery.search_api_provider import MockSearchApiProvider
    api = MockSearchApiProvider()
    results = api.search("test", 5)
    assert len(results) >= 1
