"""Readable in dark mode, and a fuller chat (2026-11-01): the welcome page's options, the Log out button, the chart
labels and legends, and the 12 example questions with the note above them.

These check the styles and settings themselves; the screenshots in both themes are in
docs/evidence/week-4/dark-mode-and-examples.md.

Run:
    uv run pytest tests/test_theme.py -v
"""

import re

from creditcoach.app import dashboard, main, theme, welcome


def rule(css: str, selector_part: str) -> str:
    """The declarations of the first rule whose selector contains ``selector_part``."""
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if selector_part in selectors:
            return body
    raise AssertionError(f"no rule for {selector_part!r}")


def test_twelve_different_example_questions():
    assert len(main.EXAMPLES) == 12
    assert len(set(main.EXAMPLES)) == 12
    assert all(q.endswith("?") for q in main.EXAMPLES)


def test_the_guardrail_examples_are_kept():
    assert "Should I take out this payday loan to pay off my credit card?" in main.EXAMPLES
    assert "Can you guarantee my score will hit 720 if I do what you said?" in main.EXAMPLES


def test_a_note_invites_people_to_pick_a_question():
    assert "Pick from one of the queries listed below" in main.PICK_PROMPT
    assert "var(--body-text-color)" in rule(theme.CSS, ".placeholder-content .placeholder p")


def test_welcome_options_have_light_words_in_dark_mode():
    assert "#e2e8f0" in rule(welcome.CSS, ".dark .cc-welcome fieldset label span")
    assert "#ffffff" in rule(welcome.CSS, ".dark .cc-welcome fieldset label.selected span")
    # light mode keeps its dark words
    assert "#0f172a" in rule(welcome.CSS, ".cc-welcome fieldset label span")


def test_log_out_sets_its_own_word_color():
    body = rule(theme.CSS, ".cc-logout")
    assert "background: #ffffff" in body
    assert "color: #0f172a" in body


def test_chart_text_takes_the_page_text_color():
    body = rule(theme.CSS, ".js-plotly-plot .xtick text")
    assert "fill: var(--body-text-color) !important" in body
    for part in (".ytick text", ".g-xtitle text", ".g-ytitle text", ".legendtext", ".textpoint text"):
        assert part in theme.CSS
    assert ".hoverlayer" not in theme.CSS  # hover boxes keep Plotly's own colors


def test_chart_legends_say_they_can_be_clicked():
    import plotly.graph_objects as go

    fig = dashboard._figure(go.Figure())
    assert fig.layout.legend.title.text.startswith("Click to hide or show")
    assert fig.layout.font.size == 13
