"""
content_quality_scorer.py — evaluate extracted content quality.

Scoring dimensions (0.0–1.0 each, weighted sum → 0–100):
  - title_present:        10 pts — has a title
  - body_length:          30 pts — body text byte count (capped at 3000)
  - keyword_coverage:     20 pts — how many search keywords appear in body
  - not_empty:            15 pts — body is not empty/error/captcha
  - not_login_page:       10 pts — doesn't look like a login page
  - not_captcha:          10 pts — doesn't look like a captcha page
  - not_error_page:        5 pts — doesn't look like an error page

Status labels:
  - 高质量  (score >= 70)
  - 可用    (score >= 40)
  - 需复核  (score >= 20)
  - 失败    (score <  20)
"""

import re

# Patterns suggesting this is a login page
LOGIN_PATTERNS = [
    r"登录", r"login", r"sign\s*in", r"signin", r"密码", r"password",
    r"验证码", r"用户名", r"username", r"请登录", r"请先登录",
]

# Patterns suggesting this is a captcha page
CAPTCHA_PATTERNS = [
    r"captcha", r"验证码", r"verify", r"verification", r"滑块",
    r"请完成.*验证", r"安全验证", r"人机验证", r"security check",
    r"are you a robot", r"cf-browser-verify",
]

# Patterns suggesting this is an error page
ERROR_PAGE_PATTERNS = [
    r"404", r"not found", r"找不到", r"不存在", r"已删除",
    r"500", r"server error", r"服务.*错误", r"内部错误",
    r"403", r"forbidden", r"禁止", r"无权", r"access denied",
    r"502", r"bad gateway", r"503", r"unavailable",
    r"connection refused", r"timeout", r"超时",
    r"页面不存在", r"无法访问", r"拒绝连接",
]


def score_quality(article: dict, keywords: list = None) -> dict:
    """
    Score an extracted article's content quality.

    Args:
        article: The ContentRecord dict from article_extractor.
        keywords: Optional list of search keywords for coverage scoring.

    Returns:
        dict:
          - score: 0–100 overall quality score
          - status_label: one of 高质量/可用/需复核/失败
          - dimensions: per-dimension scores
          - flags: list of detected issues (login_page, captcha, error_page, etc.)
          - reasons: human-readable explanation
    """
    keywords = keywords or []
    body = article.get("main_text", "")
    title = article.get("title", "")
    error = article.get("error", "")
    combined = f"{title} {body}".lower()

    dimensions = {}
    flags = []
    reasons = []

    # ── Dimension 1: Title present (10 pts) ──
    if title and len(title.strip()) >= 3:
        dimensions["title_present"] = 10
    else:
        dimensions["title_present"] = 0
        flags.append("missing_title")
        reasons.append("缺少标题")

    # ── Dimension 2: Body length (30 pts) ──
    body_len = len(body)
    if body_len >= 3000:
        dimensions["body_length"] = 30
    elif body_len >= 1000:
        dimensions["body_length"] = 20
    elif body_len >= 200:
        dimensions["body_length"] = 10
    elif body_len >= 50:
        dimensions["body_length"] = 5
    else:
        dimensions["body_length"] = 0
        flags.append("empty_body")
        reasons.append("正文为空或极短")

    # ── Dimension 3: Keyword coverage (20 pts) ──
    if keywords:
        hits = sum(1 for kw in keywords if kw.lower() in combined)
        hit_ratio = hits / len(keywords) if keywords else 0
        dimensions["keyword_coverage"] = min(20, round(hit_ratio * 20))
        if hits == 0:
            flags.append("no_keywords")
            reasons.append("无关键词命中")
    else:
        dimensions["keyword_coverage"] = 0

    # ── Dimension 4: Not empty/error (15 pts) ──
    if body and not error and body_len >= 50:
        dimensions["not_empty"] = 15
    elif body and not error:
        dimensions["not_empty"] = 5
    else:
        dimensions["not_empty"] = 0
        flags.append("empty_or_error")
        reasons.append("正文为空或采集出错")

    # ── Dimension 5: Not login page (10 pts) ──
    is_login = _matches_patterns(combined, LOGIN_PATTERNS)
    if not is_login:
        dimensions["not_login_page"] = 10
    else:
        dimensions["not_login_page"] = 0
        flags.append("login_page")
        reasons.append("疑似登录页面")

    # ── Dimension 6: Not captcha (10 pts) ──
    is_captcha = _matches_patterns(combined, CAPTCHA_PATTERNS)
    if not is_captcha:
        dimensions["not_captcha"] = 10
    else:
        dimensions["not_captcha"] = 0
        flags.append("captcha_page")
        reasons.append("疑似验证码页面")

    # ── Dimension 7: Not error page (5 pts) ──
    is_error = _matches_patterns(combined, ERROR_PAGE_PATTERNS)
    if not is_error:
        dimensions["not_error_page"] = 5
    else:
        dimensions["not_error_page"] = 0
        flags.append("error_page")
        reasons.append("疑似错误页面")

    # ── Compute total ──
    total = sum(dimensions.values())

    # Status label
    if total >= 70:
        status_label = "高质量"
    elif total >= 40:
        status_label = "可用"
    elif total >= 20:
        status_label = "需复核"
    else:
        status_label = "失败"

    return {
        "score": total,
        "status_label": status_label,
        "dimensions": dimensions,
        "flags": flags,
        "reasons": reasons if reasons else ["内容质量良好"],
    }


def _matches_patterns(text: str, patterns: list) -> bool:
    """Check if text matches any of the given patterns."""
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False
