import discord

from cogs.fastsnakestats import FastSnakeStats
from cogs import stats_charts


def _cog():
    return object.__new__(FastSnakeStats)


def test_improvement_timed_and_high_score():
    cog = _cog()
    old = {"times": {"primary": "PT1M2.500S"}}
    new = {"times": {"primary": "PT1M1S"}}
    assert cog._calculate_improvement(old, new, "a|b|c|d|25 Apples") == 1500
    hs_old = {"times": {"primary_t": 0.120}}
    hs_new = {"times": {"primary_t": 0.125}}
    assert cog._calculate_improvement(hs_old, hs_new, "a|b|c|d|High Score") == 5
    assert cog._calculate_improvement({}, new) is None


def test_format_improvement_units():
    cog = _cog()
    assert cog._format_improvement(5, "High Score") == "+5 apples"
    assert cog._format_improvement(1500) == "1.5s"


def test_embed_builders_are_size_fitted():
    assert hasattr(FastSnakeStats.create_record_embed, "__wrapped__")
    assert hasattr(FastSnakeStats.build_monthly_report_embeds, "__wrapped__")
    embed = _cog().create_help_embed(0)
    assert isinstance(embed, discord.Embed) and len(embed) <= 6000


def test_high_score_progression_chart_renders():
    flips = [{"d": "2024-01-01", "t": "PT0.095S"}, {"d": "2024-06-01", "t": "PT0.120S"}]
    png = stats_charts.progression_chart_png(flips, high_score=True)
    assert png and png.startswith(b"\x89PNG")
