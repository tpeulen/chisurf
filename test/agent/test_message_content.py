"""An assistant message's text has to survive every provider's content shape.

Most providers put the answer in ``content`` as a string. Some send a list of
typed chunks instead — text beside references, images or thinking blocks — and
stringifying that list put a Python repr in front of the user: a real answer
arrived as ``[{'type': 'text', 'text': '...'}, {'type': 'reference', ...}]``.
"""

from __future__ import annotations

from chisurf.core.agent.llm import message_text


def test_a_plain_string_is_unchanged():
    assert message_text("the lifetime is 1.85 ns") == "the lifetime is 1.85 ns"


def test_missing_content_is_empty():
    assert message_text(None) == ""


def test_typed_chunks_are_joined_into_prose():
    """The shape Mistral returns."""
    content = [
        {"type": "text", "text": "The residual anisotropy is 0.045."},
        {"type": "reference", "reference_ids": []},
        {"type": "text", "text": "That gives S2 = 0.35."},
    ]
    assert message_text(content) == ("The residual anisotropy is 0.045.\nThat gives S2 = 0.35.")


def test_a_lone_chunk_is_unwrapped():
    assert message_text({"type": "text", "text": "done"}) == "done"


def test_chunks_without_text_are_dropped_not_rendered():
    """A reference or an image must not leak its repr into the answer."""
    content = [
        {"type": "reference", "reference_ids": [1, 2]},
        {"type": "text", "text": "kappa2 = 0.67"},
    ]
    rendered = message_text(content)

    assert rendered == "kappa2 = 0.67"
    assert "reference_ids" not in rendered
    assert "{" not in rendered


def test_an_empty_list_is_empty_not_brackets():
    assert message_text([]) == ""


# ── malformed tool calls ──────────────────────────────────────────────


def test_a_sentence_is_not_a_tool_name():
    """Providers sometimes put prose where the function name goes.

    Dispatching it wastes a turn on "unknown tool <paragraph>" and loses the
    prose from the answer. A tool name is an identifier by every provider's
    schema, so anything else is the model talking.
    """
    from chisurf.core.agent.llm import is_tool_name

    assert is_tool_name("run_python")
    assert is_tool_name("kappa2_dist.compute")
    assert is_tool_name("fit-decay")

    assert not is_tool_name("To compute a distance I will use the FRET Calculator plugin")
    assert not is_tool_name("")
    assert not is_tool_name("   ")
    assert not is_tool_name("a" * 200)
    assert not is_tool_name("{'code': 'x = 1'}")
