"""Admin › Coverage: exercise counts per difficulty (pure aggregation, no DB)."""
from app.exercise_service import build_exercise_stats


def test_exercise_stats_list_every_level_and_type():
    stats = build_exercise_stats(
        [(1, "fill_blank", True, 4), (1, "fill_blank", False, 2), (1, "romaji_input", True, 1),
         (3, "multiple_choice", False, 5), (99, "fill_blank", True, 7)],
        ["fill_blank", "multiple_choice", "romaji_input"],
    )
    assert [level.difficulty for level in stats.levels] == list(range(1, 11))
    first, third = stats.levels[0], stats.levels[2]
    assert (first.total, first.human_checked) == (7, 5)
    assert first.by_type == {"fill_blank": 6, "multiple_choice": 0, "romaji_input": 1}
    assert (third.total, third.human_checked) == (5, 0)
    assert stats.levels[1].total == 0
    # Out-of-scale rows are ignored.
    assert (stats.total, stats.human_checked) == (12, 5)
