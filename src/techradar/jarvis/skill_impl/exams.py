from __future__ import annotations


def speak_exam_status(days_left: int | None, covered_pct: float) -> str:
    """Produce spoken text for exam timeline and syllabus coverage."""
    pct_str = f"{covered_pct:.1f}%" if covered_pct % 1 != 0 else f"{int(covered_pct)}%"

    if days_left is None:
        return f"No upcoming exam date is currently scheduled. Syllabus coverage is at {pct_str}."

    if days_left == 0:
        return f"Your exam is today! Syllabus coverage is at {pct_str}."
    elif days_left == 1:
        return f"There is 1 day left until your exam. Syllabus coverage is at {pct_str}."
    elif days_left > 1:
        return (
            f"There are {days_left} days left until your exam. Syllabus coverage is at {pct_str}."
        )
    else:  # days_left < 0
        days_ago = abs(days_left)
        unit = "day" if days_ago == 1 else "days"
        return f"The exam date passed {days_ago} {unit} ago. Syllabus coverage is at {pct_str}."
