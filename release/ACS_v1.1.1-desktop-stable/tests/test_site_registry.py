"""Tests for site registry."""
import sys, os, tempfile, shutil, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.sites.site_config import SiteConfig
from acs.sites.site_registry import SiteRegistry

@pytest.fixture
def reg():
    d = tempfile.mkdtemp()
    r = SiteRegistry(config_path=os.path.join(d, "test_sites.json"))
    yield r
    shutil.rmtree(d, ignore_errors=True)

def test_default_site_exists(reg):
    assert len(reg.list_all()) >= 1

def test_list_enabled_only(reg):
    assert len(reg.list_enabled()) == 0

def test_add_and_get(reg):
    cfg = SiteConfig(site_id="test1", site_name="Test", base_url="https://test.com", allowed_domains=["test.com"])
    assert reg.add(cfg)
    assert reg.get("test1").site_name == "Test"

def test_add_invalid_fails(reg):
    cfg = SiteConfig(site_id="", site_name="").enabled = True
    assert not reg.add(SiteConfig(site_id="", site_name=""))

def test_remove(reg):
    reg.add(SiteConfig(site_id="r1", site_name="R", base_url="https://r.com", allowed_domains=["r.com"]))
    assert reg.remove("r1")
    assert reg.get("r1") is None

def test_set_enabled(reg):
    reg.add(SiteConfig(site_id="e1", site_name="E", base_url="https://e.com", allowed_domains=["e.com"]))
    assert reg.set_enabled("e1", True)
    assert reg.get("e1").enabled

def test_stats(reg):
    reg.add(SiteConfig(site_id="s1", site_name="S", base_url="https://s.com", allowed_domains=["s.com"], enabled=True))
    s = reg.stats()
    assert s["total_sites"] >= 1
    assert s["enabled_sites"] >= 1

def test_validate_errors():
    c = SiteConfig(site_id="")
    assert len(c.validate()) >= 1
    c2 = SiteConfig(site_id="ok", site_name="OK", enabled=True)
    assert len(c2.validate()) >= 1
    c3 = SiteConfig(site_id="ok", site_name="OK", base_url="https://x.com", allowed_domains=["x.com"])
    assert len(c3.validate()) == 0
