"""Tests for content_quality_scorer — evaluate extracted content quality."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acs.content.content_quality_scorer import score_quality


# ── Test data ──

FULL_ARTICLE = {
    "title": "2025年环保政策深度解读与未来趋势分析",
    "main_text": (
        "近日，国务院发布了最新环保政策文件。该文件涵盖了多个重要领域，"
        "包括碳减排、清洁能源推广、生态保护补偿机制等。"
        "专家表示，这些政策将对未来五年的绿色发展产生深远影响。"
        "各地方政府积极响应，陆续出台了配套实施细则。"
        "在能源转型方面，非化石能源消费比重将持续提高。"
        "预计到2030年，清洁能源占比将达到25%以上。"
        "碳交易市场也将进一步扩大覆盖范围，钢铁、水泥等高排放行业将被纳入。"
        "此外，绿色金融体系建设也将加速推进，为环保产业提供更多资金支持。"
        "总体来看，这是一套系统性的政策组合拳，标志着我国环保工作进入新阶段。"
    ) * 8,  # Make it long enough for high body_length score (approx 3200 chars)
    "error": "",
}

EMPTY_ARTICLE = {
    "title": "",
    "main_text": "",
    "error": "No content",
}

LOGIN_PAGE = {
    "title": "用户登录",
    "main_text": "请输入用户名和密码进行登录。用户名：密码：验证码：请登录",
    "error": "",
}

CAPTCHA_PAGE = {
    "title": "安全验证",
    "main_text": "请完成安全验证以继续访问。人机验证 captcha verification 滑块验证",
    "error": "",
}

ERROR_PAGE = {
    "title": "404 Not Found",
    "main_text": "404 页面不存在 无法访问 找不到",
    "error": "HTTP 404",
}


# ── Tests ──

def test_score_quality_full_article():
    """Full article with title, body, keywords should score high."""
    result = score_quality(FULL_ARTICLE, keywords=["环保", "政策", "碳排放"])

    assert result["score"] >= 60
    assert result["status_label"] in ("高质量", "可用")
    assert "title_present" in result["dimensions"]
    assert result["dimensions"]["title_present"] == 10
    assert result["dimensions"]["body_length"] >= 20
    assert result["dimensions"]["not_empty"] == 15
    assert result["dimensions"]["not_login_page"] == 10
    assert result["dimensions"]["not_captcha"] == 10
    assert result["dimensions"]["not_error_page"] == 5
    assert "login_page" not in result["flags"]
    assert "captcha_page" not in result["flags"]
    assert "error_page" not in result["flags"]


def test_score_quality_empty_article():
    """Empty article should score low."""
    result = score_quality(EMPTY_ARTICLE)

    # With empty body but no login/captcha/error marks, base score =
    # not_login_page=10 + not_captcha=10 + not_error_page=5 = 25
    assert result["score"] <= 30
    assert result["status_label"] in ("需复核", "失败")
    assert "missing_title" in result["flags"]
    assert "empty_body" in result["flags"]


def test_score_quality_login_page_detection():
    """Login page patterns should be flagged."""
    result = score_quality(LOGIN_PAGE)

    assert "login_page" in result["flags"]
    assert result["dimensions"]["not_login_page"] == 0
    assert "疑似登录页面" in result["reasons"]


def test_score_quality_captcha_page_detection():
    """Captcha page patterns should be flagged."""
    result = score_quality(CAPTCHA_PAGE)

    assert "captcha_page" in result["flags"]
    assert result["dimensions"]["not_captcha"] == 0
    assert any("验证码" in r for r in result["reasons"])


def test_score_quality_error_page_detection():
    """Error page patterns should be flagged."""
    result = score_quality(ERROR_PAGE)

    assert "error_page" in result["flags"]
    assert result["dimensions"]["not_error_page"] == 0
    assert any("错误" in r for r in result["reasons"])


def test_score_quality_status_label_high():
    """Status label should be '高质量' for score >= 70."""
    # Create an article that scores very high
    high_article = {
        "title": "A Very High Quality Article About Important Topics",
        "main_text": "x " * 3000,  # Very long body, 6000 chars
        "error": "",
    }
    result = score_quality(high_article)
    assert result["status_label"] == "高质量"


def test_score_quality_status_label_usable():
    """Status label should be '可用' for score 40-69."""
    medium_article = {
        "title": "A Decent Article",
        "main_text": "x " * 300,  # About 600 chars
        "error": "",
    }
    result = score_quality(medium_article)
    assert result["status_label"] == "可用"


def test_score_quality_status_label_review():
    """Status label should be '需复核' for score 20-39."""
    low_article = {
        "title": "",
        "main_text": "x " * 20,  # Very short body, no title
        "error": "",
    }
    result = score_quality(low_article)
    # missing_title → 0, body_length → 0, not_empty → 5,
    # not_login_page → 10, not_captcha → 10, not_error_page → 5 = 30
    assert result["status_label"] == "需复核"


def test_score_quality_status_label_fail():
    """Status label should be '失败' for score < 20."""
    # Article with error, error_page flag, login flag, and missing title/body → very low score
    fail_article = {
        "title": "",
        "main_text": "请登录 404 页面不存在 captcha verification 验证码",
        "error": "HTTP 404",
    }
    result = score_quality(fail_article)
    assert result["status_label"] == "失败"


def test_score_quality_keyword_coverage():
    """Keyword coverage should be scored correctly."""
    article = {
        "title": "环保政策解读",
        "main_text": "关于碳排放和新能源的政策分析",
        "error": "",
    }
    result = score_quality(article, keywords=["环保", "政策", "碳排放", "新能源", "不存在的词"])

    # 4 of 5 keywords hit
    assert result["dimensions"]["keyword_coverage"] > 0
    # Should be about 16 (4/5 * 20)
    assert result["dimensions"]["keyword_coverage"] == 16


def test_score_quality_no_keywords():
    """No keywords should result in zero keyword_coverage."""
    result = score_quality(FULL_ARTICLE)

    assert result["dimensions"]["keyword_coverage"] == 0


def test_score_quality_flags_list():
    """Result should always include flags list."""
    result = score_quality(FULL_ARTICLE)
    assert isinstance(result["flags"], list)


def test_score_quality_reasons_list():
    """Result should always include reasons list."""
    result = score_quality(FULL_ARTICLE)
    assert isinstance(result["reasons"], list)
    assert len(result["reasons"]) > 0
