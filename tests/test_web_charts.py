"""Tests for chart data API."""
import sys, os, pytest, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acs.web.app import app

@pytest.fixture(autouse=True)
def app_ctx():
    app.config["TESTING"] = True

def test_shadow_trend_returns_json():
    with app.test_client() as c:
        from acs.web.charts import shadow_trend_data
        with app.app_context():
            r = shadow_trend_data()
            assert isinstance(r.get_json(), dict)

def test_ai_call_trend_returns_json():
    with app.test_client() as c:
        from acs.web.charts import ai_call_trend_data
        with app.app_context():
            r = ai_call_trend_data()
            assert isinstance(r.get_json(), dict)

def test_parser_distribution_returns_json():
    with app.test_client() as c:
        from acs.web.charts import parser_distribution_data
        with app.app_context():
            r = parser_distribution_data()
            assert isinstance(r.get_json(), dict)

def test_review_status_returns_json():
    with app.test_client() as c:
        from acs.web.charts import review_status_data
        with app.app_context():
            r = review_status_data()
            assert isinstance(r.get_json(), dict)

def test_structure_trend_returns_json():
    with app.test_client() as c:
        from acs.web.charts import structure_trend_data
        with app.app_context():
            r = structure_trend_data()
            assert isinstance(r.get_json(), dict)

def test_chart_data_no_api_key():
    with app.test_client() as c:
        from acs.web.charts import shadow_trend_data
        with app.app_context():
            r = shadow_trend_data()
            j = json.dumps(r.get_json())
            assert "sk-" not in j
