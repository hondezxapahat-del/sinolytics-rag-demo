"""Unit test for agent.py's language-instruction helper (docs/TechSpec_v1.2.md
§4.4) — deliberately does not test run_agent() itself, since that's a live
LLM call and belongs in evaluate.py's answer-quality evaluation instead of a
fast unit suite."""

import agent


def test_language_rule_names_english():
    assert "English" in agent._language_rule("en")


def test_language_rule_names_chinese():
    assert "Chinese" in agent._language_rule("zh")


def test_language_rule_defaults_to_english_for_unknown_code():
    assert "English" in agent._language_rule("fr")


def test_language_rule_carves_out_explicit_user_request_exception():
    # PRD_v1.2.md Requirement 14: mixing languages is only ever acceptable
    # if the user explicitly asks for it in that turn.
    assert "explicitly" in agent._language_rule("en")
