import pytest

from chat.responses import mentions_67, parse_how_many_records_player, wants_fastsnakestats_link


@pytest.mark.parametrize(
    "text",
    [
        "<@896745671234567890> has been doing them occasionally",
        "<#1267000000000000067> check this",
        "<:emote67:123> <a:x:1670>",
        "https://tenor.com/view/67-kid-12345",
        "I got 167 apples",
        "pb is 6.67s",
        "",
    ],
)
def test_67_ignores_ids_urls_and_other_numbers(text):
    assert not mentions_67(text)


@pytest.mark.parametrize("text", ["67", "six seven 67!", "<@123> 67", "it was 67."])
def test_67_detected_when_written(text):
    assert mentions_67(text)


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
