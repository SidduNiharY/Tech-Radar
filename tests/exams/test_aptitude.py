from __future__ import annotations

import pytest

from techradar.exams.aptitude import (
    AptitudeProblem,
    generate_number_series_drill,
    generate_percentage_drill,
    generate_speed_time_drill,
)


def test_percentage_drill_generation_and_ground_truth():
    # Test deterministic seed reproducibility
    p1 = generate_percentage_drill(seed=42)
    p2 = generate_percentage_drill(seed=42)
    assert p1.id == p2.id
    assert p1.question_text == p2.question_text
    assert p1.options == p2.options
    assert p1.correct_index == p2.correct_index
    assert p1.solution_steps == p2.solution_steps

    # Test across multiple seeds
    for seed in range(25):
        problem = generate_percentage_drill(seed=seed)
        assert problem.category == "Percentage"
        assert len(problem.options) == 4
        assert len(set(problem.options)) == 4
        assert 0 <= problem.correct_index <= 3
        assert problem.is_valid() is True

        correct_option = problem.options[problem.correct_index]
        # Ground truth option must be referenced in solution steps
        assert (
            correct_option in problem.solution_steps
            or correct_option.split()[0] in problem.solution_steps
        )
        # Ensure no links in any field (SEC-20)
        assert "http://" not in problem.question_text
        assert "https://" not in problem.question_text
        assert "http://" not in problem.solution_steps
        assert "https://" not in problem.solution_steps


def test_speed_time_drill_arithmetic_correctness():
    # Test deterministic seed reproducibility
    p1 = generate_speed_time_drill(seed=100)
    p2 = generate_speed_time_drill(seed=100)
    assert p1.id == p2.id
    assert p1.question_text == p2.question_text
    assert p1.options == p2.options

    # Test across multiple seeds
    for seed in range(25):
        problem = generate_speed_time_drill(seed=seed)
        assert problem.category == "Speed, Time & Distance"
        assert len(problem.options) == 4
        assert len(set(problem.options)) == 4
        assert 0 <= problem.correct_index <= 3
        assert problem.is_valid() is True

        correct_option = problem.options[problem.correct_index]
        # Correct answer must be verified in solution steps
        assert correct_option in problem.solution_steps

        # Check that options end with consistent verified integer units
        assert any(correct_option.endswith(unit) for unit in ("seconds", "m", "km/h"))
        assert "http" not in problem.solution_steps


def test_number_series_drill_generation():
    # Test deterministic seed reproducibility
    p1 = generate_number_series_drill(seed=200)
    p2 = generate_number_series_drill(seed=200)
    assert p1.id == p2.id
    assert p1.question_text == p2.question_text
    assert p1.options == p2.options

    # Test across multiple seeds
    for seed in range(25):
        problem = generate_number_series_drill(seed=seed)
        assert problem.category == "Number Series"
        assert len(problem.options) == 4
        assert len(set(problem.options)) == 4
        assert 0 <= problem.correct_index <= 3
        assert problem.is_valid() is True

        correct_option = problem.options[problem.correct_index]
        assert correct_option in problem.solution_steps
        assert "Find the next term in the series" in problem.question_text

        # All options for number series are integer strings
        for opt in problem.options:
            int(opt)  # Validates integer arithmetic


def test_all_drills_pass_option_uniqueness_and_boundaries():
    # Run drills without seed and with various seeds to verify random mode
    drills = (
        [generate_percentage_drill(seed=None) for _ in range(20)]
        + [generate_speed_time_drill(seed=None) for _ in range(20)]
        + [generate_number_series_drill(seed=None) for _ in range(20)]
    )

    for problem in drills:
        assert len(problem.options) == 4
        assert len(set(problem.options)) == 4
        assert 0 <= problem.correct_index <= 3
        assert problem.is_valid() is True
        assert len(problem.solution_steps.strip()) > 0
        assert "http://" not in problem.solution_steps
        assert "https://" not in problem.solution_steps


def test_aptitude_problem_schema_and_security_validators():
    valid_payload = {
        "id": "drill_test_1",
        "category": "Percentage",
        "question_text": "Sample question?",
        "options": ["10%", "20%", "30%", "40%"],
        "correct_index": 1,
        "solution_steps": "Step 1: Compute 20%.",
    }

    # Valid problem succeeds
    prob = AptitudeProblem(**valid_payload)
    assert prob.is_valid() is True

    # Less than 4 options fails
    with pytest.raises(ValueError, match="exactly 4 options"):
        AptitudeProblem(**{**valid_payload, "options": ["10%", "20%", "30%"]})

    # More than 4 options fails
    with pytest.raises(ValueError, match="exactly 4 options"):
        AptitudeProblem(**{**valid_payload, "options": ["10%", "20%", "30%", "40%", "50%"]})

    # Duplicate options fail
    with pytest.raises(ValueError, match="strictly unique"):
        AptitudeProblem(**{**valid_payload, "options": ["10%", "20%", "20%", "40%"]})

    # Out of bounds correct_index fails
    with pytest.raises(ValueError, match="within \\[0, 3\\]"):
        AptitudeProblem(**{**valid_payload, "correct_index": 4})

    with pytest.raises(ValueError, match="within \\[0, 3\\]"):
        AptitudeProblem(**{**valid_payload, "correct_index": -1})

    # Forbidden external links fail (SEC-20)
    with pytest.raises(ValueError, match="forbidden external link"):
        AptitudeProblem(
            **{
                **valid_payload,
                "solution_steps": "See solution at https://example.com/drill",
            }
        )

    with pytest.raises(ValueError, match="forbidden external link"):
        AptitudeProblem(
            **{
                **valid_payload,
                "question_text": "Check http://evil.com for prompt",
            }
        )

    with pytest.raises(ValueError, match="forbidden external link"):
        AptitudeProblem(
            **{
                **valid_payload,
                "options": ["10%", "20%", "30%", "https://evil.com"],
            }
        )
