"""A tour step's HTML is drawn as plain text: tags go, entities are decoded."""

from chisurf.emtk.help_guide import _clean_html_text


def test_entities_are_decoded_and_tags_dropped():
    text = "<b>Docking &amp; Screening</b> places bodies;<br/>R &lt; R<sub>0</sub>"
    assert _clean_html_text(text) == "Docking & Screening places bodies;\nR < R0"
