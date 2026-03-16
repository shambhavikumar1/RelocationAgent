"""
Budget estimation for employee relocation.
Produces cost breakdown and total estimate in EUR or USD based on origin/destination.
"""

from dataclasses import dataclass


@dataclass
class BudgetItem:
    category: str
    amount_eur: float
    notes: str


@dataclass
class BudgetResult:
    total_eur: float
    breakdown: list[BudgetItem]
    summary: str
    currency: str = "EUR"


def estimate_budget(
    destination_city: str = "",
    origin_city: str = "",
    family_size: int = 1,
    include_temp_housing_weeks: int = 4,
    currency: str = "EUR",
    **kwargs: object,
) -> BudgetResult:
    """
    Estimate relocation budget: moving, travel, temp housing, settling allowance.
    When currency is USD, amounts are in USD (US-typical rates); otherwise EUR.
    """
    use_usd = currency == "USD"
    if use_usd:
        moving_base, moving_per_person = 2200.0, 550.0
        travel_per_person = 450.0
        weekly_rent = 500.0
        settling_base, settling_per_person = 1600.0, 350.0
        sym = "$"
    else:
        moving_base, moving_per_person = 2000.0, 500.0
        travel_per_person = 400.0
        weekly_rent = 450.0
        settling_base, settling_per_person = 1500.0, 300.0
        sym = "€"

    breakdown: list[BudgetItem] = []

    moving = moving_base + family_size * moving_per_person
    breakdown.append(
        BudgetItem(
            category="Moving / household goods",
            amount_eur=round(moving, 2),
            notes="Based on family size and typical volume",
        )
    )

    travel = (1 + max(0, family_size - 1) * 0.5) * travel_per_person
    breakdown.append(
        BudgetItem(
            category="Travel to destination",
            amount_eur=round(travel, 2),
            notes="Flights/transport for employee and dependents",
        )
    )

    temp_housing = weekly_rent * include_temp_housing_weeks
    breakdown.append(
        BudgetItem(
            category="Temporary housing",
            amount_eur=round(temp_housing, 2),
            notes=f"{include_temp_housing_weeks} weeks at ~{sym}{weekly_rent:.0f}/week",
        )
    )

    settling = settling_base + family_size * settling_per_person
    breakdown.append(
        BudgetItem(
            category="Settling allowance",
            amount_eur=round(settling, 2),
            notes="One-time settling-in allowance",
        )
    )

    total = sum(item.amount_eur for item in breakdown)
    summary = (
        f"Estimated total: {sym}{total:,.2f} for relocation to {destination_city or 'destination'}"
        f" (origin: {origin_city or 'N/A'}). Breakdown: moving, travel, temp housing, settling."
    )

    return BudgetResult(
        total_eur=round(total, 2),
        breakdown=breakdown,
        summary=summary,
        currency=currency,
    )
