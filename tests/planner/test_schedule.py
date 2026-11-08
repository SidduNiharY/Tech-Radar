from __future__ import annotations

from datetime import date

from techradar.planner.schedule import (
    DailyPlan,
    EnergyLevel,
    StudyBlock,
    StudyGoal,
    generate_daily_plan,
)


def test_energy_level_matching_high_energy():
    goals = [StudyGoal.GATE, StudyGoal.DEV, StudyGoal.SSC]
    plan = generate_daily_plan(
        available_minutes=90,
        current_energy=EnergyLevel.HIGH,
        target_goals=goals,
        plan_date=date(2026, 11, 8),
    )
    assert len(plan.blocks) == 3
    for block in plan.blocks:
        assert block.energy_required == EnergyLevel.HIGH
        assert any(kw in block.title.lower() for kw in ("problem", "drill", "coding"))


def test_energy_level_matching_medium_energy():
    goals = [StudyGoal.BANKING, StudyGoal.ENGLISH]
    plan = generate_daily_plan(
        available_minutes=60,
        current_energy=EnergyLevel.MEDIUM,
        target_goals=goals,
        plan_date=date(2026, 11, 8),
    )
    assert len(plan.blocks) == 2
    for block in plan.blocks:
        assert block.energy_required == EnergyLevel.MEDIUM
        assert any(kw in block.title.lower() for kw in ("reading", "mcq"))


def test_energy_level_matching_low_energy():
    goals = [StudyGoal.GATE, StudyGoal.ENGLISH]
    plan = generate_daily_plan(
        available_minutes=60,
        current_energy=EnergyLevel.LOW,
        target_goals=goals,
        plan_date=date(2026, 11, 8),
    )
    assert len(plan.blocks) == 2
    for block in plan.blocks:
        assert block.energy_required == EnergyLevel.LOW
        assert any(kw in block.title.lower() for kw in ("review", "flashcard", "vocab"))


def test_total_minutes_budget_constraint():
    goals = [StudyGoal.GATE, StudyGoal.DEV]
    for available in [10, 45, 90, 180]:
        plan = generate_daily_plan(
            available_minutes=available,
            current_energy=EnergyLevel.HIGH,
            target_goals=goals,
        )
        assert plan.total_minutes <= available
        assert sum(b.duration_minutes for b in plan.blocks) == plan.total_minutes


def test_zero_and_negative_minutes_budget():
    plan_zero = generate_daily_plan(
        available_minutes=0,
        current_energy=EnergyLevel.MEDIUM,
        target_goals=[StudyGoal.GATE],
    )
    assert plan_zero.total_minutes == 0
    assert plan_zero.blocks == []

    plan_neg = generate_daily_plan(
        available_minutes=-30,
        current_energy=EnergyLevel.LOW,
        target_goals=[StudyGoal.DEV],
    )
    assert plan_neg.total_minutes == 0
    assert plan_neg.blocks == []


def test_empty_goals_list():
    plan = generate_daily_plan(
        available_minutes=120,
        current_energy=EnergyLevel.HIGH,
        target_goals=[],
    )
    assert plan.total_minutes == 0
    assert plan.blocks == []


def test_multi_goal_even_balance():
    # 3 goals with 100 minutes: 34 + 33 + 33 = 100
    goals = [StudyGoal.GATE, StudyGoal.SSC, StudyGoal.BANKING]
    plan = generate_daily_plan(
        available_minutes=100,
        current_energy=EnergyLevel.MEDIUM,
        target_goals=goals,
    )
    assert len(plan.blocks) == 3
    durations = [b.duration_minutes for b in plan.blocks]
    assert sum(durations) == 100
    assert max(durations) - min(durations) <= 1


def test_duplicate_goals_deduplicated():
    goals = [StudyGoal.GATE, StudyGoal.GATE, StudyGoal.DEV]
    plan = generate_daily_plan(
        available_minutes=60,
        current_energy=EnergyLevel.HIGH,
        target_goals=goals,
    )
    # Deduplicates to [GATE, DEV] -> 30 min each
    assert len(plan.blocks) == 2
    assert [b.goal for b in plan.blocks] == [StudyGoal.GATE, StudyGoal.DEV]
    assert all(b.duration_minutes == 30 for b in plan.blocks)


def test_study_block_schema_attributes():
    plan = generate_daily_plan(
        available_minutes=45,
        current_energy=EnergyLevel.HIGH,
        target_goals=[StudyGoal.DEV],
        plan_date=date(2026, 11, 8),
    )
    assert plan.date == date(2026, 11, 8)
    assert isinstance(plan, DailyPlan)
    assert len(plan.blocks) == 1
    block = plan.blocks[0]
    assert isinstance(block, StudyBlock)
    assert isinstance(block.id, str)
    assert block.id.startswith("dev-")
    assert block.goal == StudyGoal.DEV
    assert block.duration_minutes == 45
    assert block.energy_required == EnergyLevel.HIGH
