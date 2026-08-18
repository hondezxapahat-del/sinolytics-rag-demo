"""Unit tests for the pure, dependency-free helper functions in tools.py —
deliberately does not test search_documents/search_web/generate_chart etc.,
since those hit OpenAI/Tavily/Supabase and belong in evaluate.py's answer-
quality evaluation instead of a fast unit suite."""

import tools


def test_strip_years_removes_four_digit_years():
    assert tools._strip_years("latest trend in 2024") == "latest trend in"
    assert tools._strip_years("no year here") == "no year here"
    assert "2026" not in tools._strip_years("as of 2026, the market")


def test_strip_years_ignores_non_year_numbers():
    # Only 1900-2099 should be treated as a year token.
    assert tools._strip_years("top 10 companies") == "top 10 companies"


def test_query_is_too_vague_true_for_bare_timeliness_phrase():
    assert tools._query_is_too_vague("what is the newest trend?") is True
    assert tools._query_is_too_vague("最新趋势是什么") is True


def test_query_is_too_vague_false_when_topic_present():
    assert tools._query_is_too_vague("latest trend in AI pricing in China") is False
    assert tools._query_is_too_vague("电池供应链最新趋势") is False
    assert tools._query_is_too_vague("battery supply chain latest developments") is False


def test_query_is_too_vague_ignores_stray_year_tokens():
    # A guessed year token (the fixed year-fabrication bug) must not count
    # as "content" and mask an otherwise-vague query.
    assert tools._query_is_too_vague("newest trend in China 2024") is True


def test_format_date_parses_rfc_style_date():
    assert tools._format_date("Wed, 22 Apr 2026 15:38:51 GMT") == "2026-04-22"


def test_format_date_returns_none_for_missing_input():
    assert tools._format_date(None) is None
    assert tools._format_date("") is None


def test_format_date_falls_back_to_raw_string_on_unparseable_input():
    assert tools._format_date("not a date") == "not a date"


def test_site_name_strips_www_and_returns_domain():
    assert tools._site_name({"url": "https://www.apnews.com/article/x"}) == "apnews.com"
    assert tools._site_name({"url": "https://china-briefing.com/news"}) == "china-briefing.com"


def test_site_name_falls_back_to_title_or_unknown():
    assert tools._site_name({"title": "Some Report"}) == "Some Report"
    assert tools._site_name({}) == "unknown source"
