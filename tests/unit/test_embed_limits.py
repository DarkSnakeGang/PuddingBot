import discord

from cogs import embed_limits as el


def test_split_value_respects_limit_and_keeps_lines():
    text = "\n".join(f"line {i:03d} " + "x" * 50 for i in range(60))
    chunks = el.split_value(text)
    assert all(len(chunk) <= el.FIELD_VALUE_MAX for chunk in chunks)
    assert "\n".join(chunks).split("\n") == text.split("\n")


def test_split_value_breaks_single_huge_line():
    chunks = el.split_value("y" * 2500)
    assert [len(c) for c in chunks] == [1024, 1024, 452]


def test_fit_embed_enforces_all_limits():
    embed = discord.Embed(title="t" * 400, description="d" * 5000)
    embed.add_field(name="huge", value="\n".join("z" * 60 for _ in range(100)))
    for i in range(40):
        embed.add_field(name=f"f{i}", value="v")
    el.fit_embed(embed)
    assert len(embed.title) <= el.TITLE_MAX
    assert len(embed.description) <= el.DESCRIPTION_MAX
    assert len(embed.fields) <= el.FIELDS_MAX
    assert all(0 < len(f.value) <= el.FIELD_VALUE_MAX for f in embed.fields)
    assert len(embed) <= el.TOTAL_MAX


def test_fit_embeds_decorator_handles_lists():
    @el.fit_embeds
    def build():
        return [discord.Embed(title="x" * 300), "not an embed"]

    embed, other = build()
    assert len(embed.title) <= el.TITLE_MAX
    assert other == "not an embed"


def test_group_embeds_splits_by_total_size():
    embeds = [discord.Embed(description="a" * 3500) for _ in range(3)]
    assert [len(group) for group in el.group_embeds(embeds)] == [1, 1, 1]
    small = [discord.Embed(description="a") for _ in range(12)]
    assert [len(group) for group in el.group_embeds(small)] == [10, 2]
