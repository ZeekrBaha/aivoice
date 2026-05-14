from aivoice.pipeline.cleanup.prompts import BASE_SYSTEM_PROMPT, MODE_OVERLAYS, build_prompt


def test_base_includes_must_and_must_not():
    assert "You MUST:" in BASE_SYSTEM_PROMPT
    assert "You MUST NOT:" in BASE_SYSTEM_PROMPT
    assert "NOT an assistant" in BASE_SYSTEM_PROMPT


def test_modes_present():
    assert set(MODE_OVERLAYS.keys()) == {"raw", "email", "code-comment", "slack"}
    assert MODE_OVERLAYS["raw"] == ""


def test_build_appends_mode():
    p = build_prompt(mode="email")
    assert p.startswith(BASE_SYSTEM_PROMPT)
    assert "email" in p.lower()


def test_build_appends_vocabulary():
    p = build_prompt(mode="raw", vocabulary=["kubectl", "Playwright"])
    assert "VOCABULARY" in p
    assert "- kubectl" in p
    assert "- Playwright" in p


def test_build_no_vocab_section_when_empty():
    p = build_prompt(mode="raw", vocabulary=[])
    assert "VOCABULARY (preserve" not in p
