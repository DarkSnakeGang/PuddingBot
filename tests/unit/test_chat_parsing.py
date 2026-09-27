import pytest

from chat.responses import parse_how_many_records_player, wants_fastsnakestats_link


@pytest.mark.parametrize(
    "text, expected",
    [
        ("how many records does Yarmiplay have?", "Yarmiplay"),
        ("<@1210325027023753307> how many wrs does moterstorm have", "moterstorm"),
        ("how many wrs does he have", None),
        ("how many records do you have", None),
        ("", None),
    ],
)
def test_how_many_records_parser(text, expected):
    assert parse_how_many_records_player(text) == expected


def test_website_question_detected():
    assert wants_fastsnakestats_link("what's the website to see how many records I have?")


@pytest.mark.parametrize("text", ["nice weather today", "I like curls", ""])
def test_website_question_not_triggered_by_unrelated_text(text):
    assert not wants_fastsnakestats_link(text)
