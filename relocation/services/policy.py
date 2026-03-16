"""
Policy validation for employee relocation.
Validates eligibility and constraints against company relocation policy.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyResult:
    eligible: bool
    summary: str
    constraints: list[str]
    details: dict[str, Any]


# Example policy rules (can be replaced with config/API)
DEFAULT_POLICY = {
    "min_tenure_months": 12,
    "max_distance_km": 500,
    "eligible_roles": ["full_time", "contract_12m_plus"],
    "max_allowance_eur": 15000,
    "requires_approval_above_eur": 5000,
}


def validate_policy(
    tenure_months: int = 12,
    role: str = "full_time",
    distance_km: float = 0,
    requested_allowance_eur: float = 0,
    **kwargs: Any,
) -> PolicyResult:
    """
    Validate employee and relocation request against company policy.
    Returns eligibility, summary, and constraints.
    """
    constraints: list[str] = []
    details: dict[str, Any] = {}

    if tenure_months < DEFAULT_POLICY["min_tenure_months"]:
        constraints.append(
            f"Minimum tenure not met: {tenure_months} months (required: {DEFAULT_POLICY['min_tenure_months']})"
        )
    else:
        details["tenure_ok"] = True

    if role not in DEFAULT_POLICY["eligible_roles"]:
        constraints.append(
            f"Role '{role}' may not be eligible; eligible: {DEFAULT_POLICY['eligible_roles']}"
        )
    else:
        details["role_ok"] = True

    if distance_km > DEFAULT_POLICY["max_distance_km"]:
        constraints.append(
            f"Distance {distance_km} km exceeds max {DEFAULT_POLICY['max_distance_km']} km"
        )
    else:
        details["distance_ok"] = distance_km <= DEFAULT_POLICY["max_distance_km"]

    if requested_allowance_eur > DEFAULT_POLICY["max_allowance_eur"]:
        constraints.append(
            f"Requested allowance €{requested_allowance_eur} exceeds max €{DEFAULT_POLICY['max_allowance_eur']}"
        )
    details["allowance_within_limit"] = requested_allowance_eur <= DEFAULT_POLICY["max_allowance_eur"]
    details["approval_required"] = requested_allowance_eur > DEFAULT_POLICY["requires_approval_above_eur"]

    eligible = len(constraints) == 0
    summary = (
        "Eligible under current relocation policy."
        if eligible
        else "One or more policy constraints apply; review required."
    )

    return PolicyResult(
        eligible=eligible,
        summary=summary,
        constraints=constraints,
        details=details,
    )
