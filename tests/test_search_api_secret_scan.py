"""Static scan: no API keys in codebase outside of env/.env handling."""
import sys, os, re, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_no_sk_key_in_source():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pat = re.compile(r"sk-[a-zA-Z0-9]{16,}")
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, "acs")):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, encoding="utf-8", errors="replace") as f:
                content = f.read()
            match = pat.search(content)
            if match:
                allowed = any(x in fp for x in ("test_", "_config", "secret_guard", "secret_scan", "smoke"))
                if not allowed:
                    pytest.fail(f"API key pattern in {fp}: ...{match.group()[-10:]}")

def test_bing_endpoint_not_hardcoded_with_auth():
    from acs.discovery.search_api_clients import BingSearchClient
    ep = BingSearchClient.ENDPOINT
    assert "api.bing.microsoft.com" in ep
    assert "subscription-key" not in ep.lower()
    assert "apikey" not in ep.lower()
