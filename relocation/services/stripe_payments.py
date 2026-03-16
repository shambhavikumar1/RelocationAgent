"""
Stripe embedded Checkout for relocation travel booking.
Creates sessions with dynamic amount (travel portion from budget) and verifies payment.
Used with the Agent Payment Protocol (payment_method="stripe").
"""

import os
import time
from typing import Any


def _env(key: str, default: str = "") -> str:
    """Read env at runtime so load_dotenv() has already run (concierge loads .env after imports)."""
    return os.getenv(key, default).strip()


def is_stripe_configured() -> bool:
    """Return True if Stripe keys are set (payment can be offered)."""
    return bool(_env("STRIPE_PUBLISHABLE_KEY") and _env("STRIPE_SECRET_KEY"))


def _get_stripe():  # type: ignore[no-any-unimported]
    import stripe
    stripe.api_key = _env("STRIPE_SECRET_KEY")
    return stripe


def _expires_at() -> int:
    # Session validity: Stripe allows 24h max; we use 30 mins default
    expires = int(_env("STRIPE_CHECKOUT_EXPIRES_SECONDS") or "1800")
    expires = max(1800, min(24 * 60 * 60, expires))
    return int(time.time()) + expires


def create_embedded_checkout_session(
    *,
    amount_cents: int,
    currency: str,
    description: str,
    user_address: str,
    chat_session_id: str,
) -> dict[str, Any]:
    """
    Create a Stripe Checkout Session for one-time payment (travel booking).
    amount_cents: e.g. 40000 for 400.00 USD/EUR
    currency: "usd" or "eur" (Stripe lowercase).
    Returns dict with client_secret, checkout_session_id, publishable_key, etc. for RequestPayment.metadata["stripe"].
    """
    stripe_sdk = _get_stripe()
    success_url = _env("STRIPE_SUCCESS_URL") or "https://agentverse.ai"
    return_url = (
        f"{success_url}"
        f"?session_id={{CHECKOUT_SESSION_ID}}"
        f"&chat_session_id={chat_session_id}"
        f"&user={user_address}"
    )
    session = stripe_sdk.checkout.Session.create(
        ui_mode="embedded",
        redirect_on_completion="if_required",
        payment_method_types=["card"],
        mode="payment",
        return_url=return_url,
        expires_at=_expires_at(),
        line_items=[
            {
                "price_data": {
                    "currency": currency.lower(),
                    "product_data": {
                        "name": "Relocation travel booking",
                        "description": description,
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }
        ],
        metadata={
            "user_address": user_address,
            "session_id": chat_session_id,
            "service": "relocation_travel",
        },
    )
    return {
        "client_secret": session.client_secret,
        "id": session.id,
        "checkout_session_id": session.id,
        "publishable_key": _env("STRIPE_PUBLISHABLE_KEY"),
        "currency": currency.lower(),
        "amount_cents": amount_cents,
        "ui_mode": "embedded",
    }


def verify_checkout_session_paid(checkout_session_id: str) -> bool:
    """Verify that the Stripe Checkout Session has been paid. Used after CommitPayment."""
    stripe_sdk = _get_stripe()
    session = stripe_sdk.checkout.Session.retrieve(checkout_session_id)
    return getattr(session, "payment_status", None) == "paid"
