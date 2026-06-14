"""Tests for chart page, chart API, and API key safety."""
import sys, os, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acs.web.app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()

def test_charts_page_ok(client):
    r = client.get("/charts")
    assert r.status_code == 200

def test_charts_page_has_chart_js(client):
    r = client.get("/charts")
    html = r.data.decode("utf-8", errors="replace")
    assert "Chart" in html or "chart" in html or "canvas" in html

def test_charts_page_has_canvas_elements(client):
    r = client.get("/charts")
    html = r.data.decode("utf-8", errors="replace")
    assert "canvas" in html.lower()

def test_chart_api_shadow_trend(client):
    r = client.get("/api/charts/shadow_trend")
    assert r.status_code == 200
    d = r.get_json()
    assert "labels" in d

def test_chart_api_ai_call_trend(client):
    r = client.get("/api/charts/ai_call_trend")
    assert r.status_code == 200

def test_chart_api_parser_distribution(client):
    r = client.get("/api/charts/parser_distribution")
    assert r.status_code == 200

def test_chart_api_review_status(client):
    r = client.get("/api/charts/review_status")
    assert r.status_code == 200

def test_chart_api_structure_trend(client):
    r = client.get("/api/charts/structure_trend")
    assert r.status_code == 200

def test_chart_page_no_api_key(client):
    r = client.get("/charts")
    html = r.data.decode("utf-8", errors="replace")
    assert "sk-" not in html
    assert "Bearer" not in html

def test_chart_api_no_api_key(client):
    for route in ["/api/charts/shadow_trend","/api/charts/ai_call_trend","/api/charts/parser_distribution",
                  "/api/charts/review_status","/api/charts/structure_trend"]:
        r = client.get(route)
        j = json.dumps(r.get_json())
        assert "sk-" not in j
        assert "Bearer" not in j
