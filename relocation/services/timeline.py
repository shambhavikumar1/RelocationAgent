"""
Relocation timeline generation.
Produces a phased timeline from decision to move-in.
If target_move_date is set, start_date is computed so that move-in falls on that date.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, date


@dataclass
class TimelinePhase:
    name: str
    start_week: int
    end_week: int
    tasks: list[str]


@dataclass
class TimelineResult:
    phases: list[TimelinePhase]
    total_weeks: int
    summary: str
    start_date: str
    target_move_date: str | None = None


def generate_timeline(
    start_from_weeks_from_now: int = 0,
    include_temp_housing_weeks: int = 4,
    target_move_date: str | None = None,
    **kwargs: object,
) -> TimelineResult:
    """
    Generate a relocation timeline: policy sign-off, moving, travel, temp housing, move-in.
    If target_move_date (YYYY-MM-DD) is given, start_date is set so the timeline ends on that date.
    """
    phases: list[TimelinePhase] = [
        TimelinePhase(
            name="Policy & approval",
            start_week=0,
            end_week=2,
            tasks=[
                "Submit relocation request and documents",
                "Policy validation and manager approval",
                "Budget confirmation and allowance approval",
            ],
        ),
        TimelinePhase(
            name="Moving arrangements",
            start_week=2,
            end_week=5,
            tasks=[
                "Select moving company and get quotes",
                "Schedule packing and pickup",
                "Coordinate with landlord for handover",
            ],
        ),
        TimelinePhase(
            name="Travel & temporary housing",
            start_week=5,
            end_week=5 + include_temp_housing_weeks,
            tasks=[
                "Book travel for employee and family",
                "Check into temporary accommodation",
                "Register address and local admin",
            ],
        ),
        TimelinePhase(
            name="Settling & move-in",
            start_week=5 + include_temp_housing_weeks,
            end_week=5 + include_temp_housing_weeks + 2,
            tasks=[
                "Household goods delivery",
                "Permanent housing move-in",
                "Final settling allowance and closure",
            ],
        ),
    ]
    total_weeks = phases[-1].end_week if phases else 0

    if target_move_date:
        try:
            target = date.fromisoformat(target_move_date)
            start_dt = target - timedelta(weeks=total_weeks)
            start_str = start_dt.strftime("%Y-%m-%d")
            summary = (
                f"Relocation timeline: {total_weeks} weeks. To be moved by {target_move_date}, start by {start_str}. "
                f"Phases: policy & approval → moving → travel & temp housing ({include_temp_housing_weeks} weeks) → settling & move-in."
            )
        except (ValueError, TypeError):
            base = datetime.utcnow() + timedelta(weeks=start_from_weeks_from_now)
            start_str = base.strftime("%Y-%m-%d")
            summary = (
                f"Relocation timeline: {total_weeks} weeks from start ({start_str}). "
                f"Phases: policy & approval → moving → travel & temp housing ({include_temp_housing_weeks} weeks) → settling & move-in."
            )
            target_move_date = None
    else:
        base = datetime.utcnow() + timedelta(weeks=start_from_weeks_from_now)
        start_str = base.strftime("%Y-%m-%d")
        summary = (
            f"Relocation timeline: {total_weeks} weeks from start ({start_str}). "
            f"Phases: policy & approval → moving → travel & temp housing ({include_temp_housing_weeks} weeks) → settling & move-in."
        )

    return TimelineResult(
        phases=phases,
        total_weeks=total_weeks,
        summary=summary,
        start_date=start_str,
        target_move_date=target_move_date,
    )
