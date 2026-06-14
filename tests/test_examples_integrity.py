"""Tests: example files integrity — no real keys, no commercial platforms."""
import sys, os, json, re, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")


def test_examples_dir_exists():
    assert os.path.isdir(EXAMPLES), "examples/ directory must exist"


def test_urls_sample_exists():
    path = os.path.join(EXAMPLES, "urls_sample.txt")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    assert len(lines) >= 5, "should have at least 5 sample URLs"


def test_csv_sample_exists():
    path = os.path.join(EXAMPLES, "search_results_sample.csv")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8-sig") as f:
        content = f.read()
    assert "url" in content.lower()
    assert ",title" in content.lower() or ",name" in content.lower()


def test_json_sample_exists():
    path = os.path.join(EXAMPLES, "search_results_sample.json")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) >= 3
    for item in data:
        assert "url" in item


def test_sitemap_sample_exists():
    path = os.path.join(EXAMPLES, "sitemap_sample.xml")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        xml = f.read()
    assert "<urlset" in xml or "<sitemap" in xml
    assert "<loc>" in xml


def test_rss_sample_exists():
    path = os.path.join(EXAMPLES, "rss_sample.xml")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        xml = f.read()
    assert "<rss" in xml or "<feed" in xml
    assert "<item>" in xml or "<entry>" in xml


def test_no_commercial_platforms_in_examples():
    commercial = ["amazon.com", "walmart.com", "bestbuy.com", "ebay.com",
                  "homedepot.com", "target.com", "goofish.com", "xianyu"]
    for fname in os.listdir(EXAMPLES):
        if fname.endswith(".bat"):
            continue
        path = os.path.join(EXAMPLES, fname)
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read().lower()
        for domain in commercial:
            assert domain not in content, f"{fname} contains commercial platform: {domain}"


def test_no_api_keys_in_examples():
    for fname in os.listdir(EXAMPLES):
        path = os.path.join(EXAMPLES, fname)
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        assert "sk-" not in content, f"{fname} may contain API key"
        assert "Bearer" not in content, f"{fname} may contain auth token"
