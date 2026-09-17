"""Plain label in, typeset label out.

The rule these pin: a view spec spells a quantity the way code and translators
want it (``tau_D(0)``, ``Phi_A``, ``kappa^2``) and the screen shows the
typography. Getting that wrong is invisible in a construction test — the label
simply reads ``tau_D(0)`` forever — so the conversion is asserted directly.
"""

import pytest

from chisurf.core.support.labels import to_plain, to_rich


@pytest.mark.parametrize(
    "plain, rich",
    [
        # the subscript convention, on the labels that actually occur
        ("R_DA", "R<sub>DA</sub>"),
        ("I_DD (donor)", "I<sub>DD</sub> (donor)"),
        ("Bg I_DA", "Bg I<sub>DA</sub>"),
        ("x_D,0", "x<sub>D,0</sub>"),
        ("R_{D,A}", "R<sub>D,A</sub>"),
        # a Greek name becomes the letter
        ("gamma", "&gamma;"),
        ("Phi_A", "&Phi;<sub>A</sub>"),
        ("tau_D(0) (ns)", "&tau;<sub>D(0)</sub> (ns)"),
        ("kappa^2", "&kappa;<sup>2</sup>"),
        # ... but only when it is the whole word
        ("alphabet", "alphabet"),
        ("Deltatron", "Deltatron"),
    ],
)
def test_plain_labels_are_typeset(plain, rich):
    """The spellings used across the view specs convert as intended."""
    assert to_rich(plain) == rich


@pytest.mark.parametrize(
    "text",
    [
        "&tau;<sub>0</sub>",  # models spell their labels out in HTML
        "cpm<sub>all</sub>",
        "x<sup>2</sup>",
    ],
)
def test_hand_written_markup_is_left_alone(text):
    """Labels already typeset by hand must survive untouched.

    Hundreds of them exist in the models and view specs; re-escaping one would
    show the user literal angle brackets.
    """
    assert to_rich(text) == text


def test_a_subscript_does_not_eat_the_bracket_that_closes_its_group():
    """``P(R_DA)`` is a probability of a distance, not ``P(R`` subscript ``DA)``.

    Parentheses have to be allowed inside a subscript for ``tau_D(0)``, which is
    exactly what made this fail: the greedy run swallowed the closing bracket of
    the enclosing group.
    """
    assert to_rich("P(R_DA)") == "P(R<sub>DA</sub>)"
    assert to_rich("f(x_i)") == "f(x<sub>i</sub>)"
    assert to_rich("Sum of R_DA, then") == "Sum of R<sub>DA</sub>, then"
    assert to_rich("E_app.") == "E<sub>app</sub>."


def test_a_superscript_glyph_still_counts_as_a_word_boundary():
    """``kappa²`` must give κ².

    Python's ``\\w`` counts ``²`` as a word character, so a neighbour test
    written with ``[^\\W\\d_]`` silently refused to convert this one.
    """
    assert to_rich("kappa²") == "&kappa;²"


def test_markup_characters_in_a_plain_label_are_escaped():
    """A plain label is data, not markup — ``N > 5`` must not become a tag."""
    assert to_rich("N > 5") == "N &gt; 5"
    assert to_rich("beta & gamma") == "&beta; &amp; &gamma;"


@pytest.mark.parametrize(
    "text, plain",
    [
        ("R<sub>DA</sub>", "RDA"),
        ("&kappa;<sup>2</sup>", "κ2"),
        ("tau_D(0)", "tau_D(0)"),  # already plain
        ("", ""),
    ],
)
def test_to_plain_strips_back_to_readable_text(text, plain):
    """Tooltips, documentation cells and logs get text, never markup."""
    assert to_plain(text) == plain


def test_round_trip_keeps_the_reader_oriented():
    """Typesetting then stripping loses the markup, not the meaning."""
    for label in ("R_DA", "Phi_A", "tau_D(0) (ns)", "I_DD (donor)"):
        stripped = to_plain(to_rich(label))
        assert "<" not in stripped and "&" not in stripped
        assert stripped
