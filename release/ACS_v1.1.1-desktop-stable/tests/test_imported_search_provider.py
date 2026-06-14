"""Tests for imported_search_provider — CSV/JSON/TXT/MD parsing."""
import sys, os, tempfile, shutil, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.discovery.imported_search_provider import ImportedSearchProvider


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def make_file(d, name, content):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def test_parse_txt(tmp_dir):
    p = make_file(tmp_dir, "urls.txt", "https://x.com/1\nhttps://x.com/2\n")
    imp = ImportedSearchProvider()
    c = imp.load(p)
    assert len(c) == 2
    assert c[0].url == "https://x.com/1"
    assert c[0].discovery_method == "import-file"


def test_parse_csv(tmp_dir):
    p = make_file(tmp_dir, "data.csv", "url,title,description\nhttps://x.com/1,T1,D1\nhttps://x.com/2,T2,D2\n")
    imp = ImportedSearchProvider()
    c = imp.load(p)
    assert len(c) == 2
    assert c[0].title == "T1"
    assert c[0].snippet == "D1"


def test_parse_csv_alternate_columns(tmp_dir):
    p = make_file(tmp_dir, "data.csv", "URL,name,summary\nhttps://x.com/1,T1,S1\n")
    imp = ImportedSearchProvider()
    c = imp.load(p)
    assert len(c) == 1
    assert c[0].title == "T1"


def test_parse_json(tmp_dir):
    p = make_file(tmp_dir, "data.json", '[{"url":"https://x.com/1","title":"T1"},{"url":"https://x.com/2","title":"T2"}]')
    imp = ImportedSearchProvider()
    c = imp.load(p)
    assert len(c) == 2


def test_parse_markdown(tmp_dir):
    md = "[Google](https://www.google.com)\nhttps://www.example.com/page\n"
    p = make_file(tmp_dir, "doc.md", md)
    imp = ImportedSearchProvider()
    c = imp.load(p)
    assert len(c) >= 1


def test_parse_txt_skip_comments(tmp_dir):
    p = make_file(tmp_dir, "urls.txt", "# comment\nhttps://x.com/1\n\n# another\nhttps://x.com/2\n")
    imp = ImportedSearchProvider()
    c = imp.load(p)
    assert len(c) == 2


def test_parse_invalid_skips(tmp_dir):
    p = make_file(tmp_dir, "invalid.csv", "name,age\nJohn,30\n")
    imp = ImportedSearchProvider()
    c = imp.load(p)
    assert len(c) == 0
