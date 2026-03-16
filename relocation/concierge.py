"""
Multi-Agent Employee Relocation Concierge.
Orchestrates: policy validation, budget estimation, neighborhood shortlisting (API/tool), timeline generation.
When eligible, supports Stripe travel booking via the Agent Payment Protocol.
Chat Protocol compatible for Agentverse and ASI:One discovery.
"""

import asyncio
import os
import re
from datetime import datetime, date
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI
from uagents import Context, Model, Protocol, Agent
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)
from uagents_core.contrib.protocols.payment import (
    CommitPayment,
    CompletePayment,
    Funds,
    RejectPayment,
    RequestPayment,
    payment_protocol_spec,
)

from relocation.services import (
    validate_policy,
    estimate_budget,
    get_country_code,
    shortlist_neighborhoods,
    generate_timeline,
)
from relocation.services.policy import PolicyResult
from relocation.services.budget import BudgetResult
from relocation.services.neighborhood import Neighborhood
from relocation.services.timeline import TimelineResult
from relocation.services.stripe_payments import (
    create_embedded_checkout_session,
    is_stripe_configured,
    verify_checkout_session_paid,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------
RELOCATION_AGENT_SEED = os.getenv("RELOCATION_AGENT_SEED", "employee relocation concierge seed phrase for agent identity")
AGENTVERSE_API_KEY = os.getenv("AGENTVERSE_API_KEY", "")
ASI_ONE_API_KEY = os.getenv("ASI_ONE_API_KEY", "")

# Use testnet to register on Almanac without mainnet funds (avoids "not enough funds" warning)
RELOCATION_NETWORK = os.getenv("RELOCATION_NETWORK", "mainnet")

agent = Agent(
    name="relocation-concierge",
    seed=RELOCATION_AGENT_SEED,
    port=8001,
    network=RELOCATION_NETWORK,
    mailbox=bool(AGENTVERSE_API_KEY),
    publish_agent_details=True,
    enable_agent_inspector=True,
)


class HealthResponse(Model):
    status: str = "ok"
    address: str = ""


@agent.on_rest_get("/health", HealthResponse)
async def _health(_ctx: Context):
    return HealthResponse(status="ok", address=agent.address)


protocol = Protocol(spec=chat_protocol_spec)

# Per-sender state key for last orchestration and pending payment
def _state_key(sender: str) -> str:
    return f"relocation_{sender}"


def _wants_book_travel(text: str) -> bool:
    """True if user message indicates they want to pay for travel booking."""
    t = text.lower().strip()
    return any(
        phrase in t
        for phrase in (
            "book travel",
            "pay for travel",
            "pay for my travel",
            "pay travel",
            "book my travel",
            "i want to pay",
            "pay to book",
        )
    )


def _get_travel_amount_and_currency(data: dict) -> tuple[float, str] | None:
    """From orchestration result, get (travel amount, currency). None if not found."""
    budget = data.get("budget") or {}
    currency = budget.get("currency", "EUR")
    for item in budget.get("breakdown") or []:
        if item.get("category") == "Travel to destination":
            return (float(item.get("amount_eur", 0)), currency)
    return None


# ---------------------------------------------------------------------------
# Orchestration: extract params from user message and run all services
# Words that are never city names
_NOT_CITIES = frozenset({
    "the", "my", "our", "for", "and", "relocate", "relocating", "moving", "move",
    "from", "to", "want", "need", "by", "this", "that", "company", "have", "with",
})

# Month name -> number
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

def _extract_params(text: str) -> dict:
    """Extract origin, destination, family size, tenure, etc. from natural language."""
    text_lower = text.lower()
    params = {
        "destination_city": "",
        "origin_city": "",
        "family_size": 1,
        "tenure_months": 12,
        "role": "full_time",
        "distance_km": 200,
        "requested_allowance_eur": 5000,
        "include_temp_housing_weeks": 4,
        "currency": "EUR",
    }
    # "from X to Y" or "relocate from X to Y" (origin and destination)
    m = re.search(r"(?:relocat(?:e|ing)|move)\s+from\s+([A-Za-z][A-Za-z\s]*?)\s+to\s+([A-Za-z][A-Za-z\s]*?)(?:\s+and|\s+with|\s+i\s+|\s+want|\s+by|\s+\.|,|$)", text, re.IGNORECASE)
    if m:
        orig = m.group(1).strip()
        dest = m.group(2).strip()
        if orig and dest and orig.lower() not in _NOT_CITIES and dest.lower() not in _NOT_CITIES:
            params["origin_city"] = orig.title()
            params["destination_city"] = dest.title()
    # Fallback: "to Atlanta" or "to Berlin"
    if not params["destination_city"]:
        m = re.search(r"\bto\s+([A-Za-z][A-Za-z\s]{1,25}?)(?:\s+and|\s+with|\s+i\s+|\s+want|\s+by|\s+\.|,|$)", text, re.IGNORECASE)
        if m:
            dest = m.group(1).strip()
            if dest.lower() not in _NOT_CITIES:
                params["destination_city"] = dest.title()
    # Single city mentions
    if not params["destination_city"]:
        for city in ("atlanta", "tampa", "berlin", "munich", "münchen", "london", "new york"):
            if city in text_lower:
                params["destination_city"] = city.title() if len(city) > 1 else city
                if city in ("atlanta", "tampa") and not params["origin_city"]:
                    if "tampa" in text_lower and "atlanta" in text_lower:
                        params["origin_city"] = "Tampa"
                        params["destination_city"] = "Atlanta"
                break
    if not params["destination_city"]:
        params["destination_city"] = "Berlin"
    # Currency is set in _run_orchestration via geocode API (USD if US, else EUR)
    # Family
    m = re.search(r"(?:family|with)\s+(\d+)\s*(?:people|members|kids)?", text_lower)
    if m:
        params["family_size"] = max(1, min(10, int(m.group(1))))
    if "spouse" in text_lower or "partner" in text_lower or "children" in text_lower or "kids" in text_lower:
        params["family_size"] = max(params["family_size"], 2)
    # Tenure: "worked for 9 months" or "9 months in this company"
    m = re.search(r"(?:tenure|worked|employed|with)\s+(?:for\s+)?(\d+)\s*(?:months|years?)", text_lower)
    if m:
        val = int(m.group(1))
        params["tenure_months"] = val * 12 if "year" in text_lower[m.start():m.end() + 20] else val
    m = re.search(r"(\d+)\s*months?\s+(?:in\s+this\s+company|tenure|with)", text_lower)
    if m:
        params["tenure_months"] = int(m.group(1))
    # Target move date: "move by 15th April", "by April 15", "by 23rd april"
    params["target_move_date"] = _parse_move_by_date(text_lower)
    return params


# ---------------------------------------------------------------------------
# Payment Protocol (seller): Stripe travel booking when eligible
# ---------------------------------------------------------------------------
payment_protocol = Protocol(spec=payment_protocol_spec, role="seller")


@payment_protocol.on_message(CommitPayment)
async def on_commit_payment(ctx: Context, sender: str, msg: CommitPayment):
    funds = getattr(msg, "funds", None)
    method = getattr(funds, "payment_method", None) if funds else None
    txn_id = getattr(msg, "transaction_id", None)
    if method != "stripe" or not txn_id:
        await ctx.send(sender, RejectPayment(reason="Unsupported payment method (expected stripe)."))
        return
    paid = await asyncio.to_thread(verify_checkout_session_paid, txn_id)
    if not paid:
        await ctx.send(
            sender,
            RejectPayment(reason="Stripe payment not completed yet. Please finish checkout."),
        )
        return
    await ctx.send(sender, CompletePayment(transaction_id=txn_id))
    key = _state_key(sender)
    ctx.storage.set(key, {})  # clear pending state
    await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.utcnow(),
            msg_id=uuid4(),
            content=[
                TextContent(
                    type="text",
                    text=(
                        "Payment successful. Your travel booking payment has been received. "
                    ),
                ),
                EndSessionContent(type="end-session"),
            ],
        ),
    )


@payment_protocol.on_message(RejectPayment)
async def on_reject_payment(ctx: Context, sender: str, msg: RejectPayment):
    key = _state_key(sender)
    ctx.storage.set(key, {})
    reason = getattr(msg, "reason", None) or "Payment was declined."
    await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.utcnow(),
            msg_id=uuid4(),
            content=[
                TextContent(type="text", text=f"Payment cancelled. {reason}"),
                EndSessionContent(type="end-session"),
            ],
        ),
    )


def _parse_move_by_date(text: str) -> str | None:
    """Parse 'move by 15th April' / 'by April 15' etc. Return YYYY-MM-DD or None."""
    today = date.today()
    year = today.year
    # "by 15th april", "by april 15", "move by 15 april"
    m = re.search(r"(?:move\s+)?by\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)", text)
    if m:
        day, month_name = int(m.group(1)), m.group(2).lower()
        month = _MONTHS.get(month_name)
        if month and 1 <= day <= 31:
            try:
                d = date(year, month, day)
                if d < today:
                    d = date(year + 1, month, day)
                return d.strftime("%Y-%m-%d")
            except ValueError:
                pass
    m = re.search(r"(?:move\s+)?by\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?", text)
    if m:
        month_name, day = m.group(1).lower(), int(m.group(2))
        month = _MONTHS.get(month_name)
        if month and 1 <= day <= 31:
            try:
                d = date(year, month, day)
                if d < today:
                    d = date(year + 1, month, day)
                return d.strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None


def _run_orchestration(params: dict) -> dict:
    """Run policy, budget, neighborhood, timeline and return structured result."""
    # Resolve currency from geocode API: USD if origin or destination is in US
    origin = (params.get("origin_city") or "").strip()
    dest = (params.get("destination_city") or "").strip()
    if origin or dest:
        codes = []
        if origin:
            codes.append(get_country_code(origin))
        if dest:
            codes.append(get_country_code(dest))
        if any(c == "us" for c in codes if c):
            params["currency"] = "USD"
        else:
            params["currency"] = "EUR"

    policy_result: PolicyResult = validate_policy(
        tenure_months=params.get("tenure_months", 12),
        role=params.get("role", "full_time"),
        distance_km=params.get("distance_km", 200),
        requested_allowance_eur=params.get("requested_allowance_eur", 5000),
    )
    budget_result: BudgetResult = estimate_budget(
        destination_city=params.get("destination_city", ""),
        origin_city=params.get("origin_city", ""),
        family_size=params.get("family_size", 1),
        include_temp_housing_weeks=params.get("include_temp_housing_weeks", 4),
        currency=params.get("currency", "EUR"),
    )
    neighborhoods: list[Neighborhood] = shortlist_neighborhoods(
        city=params.get("destination_city", "Berlin"),
        max_results=5,
    )
    timeline_result: TimelineResult = generate_timeline(
        start_from_weeks_from_now=0,
        include_temp_housing_weeks=params.get("include_temp_housing_weeks", 4),
        target_move_date=params.get("target_move_date"),
    )

    return {
        "policy": {
            "eligible": policy_result.eligible,
            "summary": policy_result.summary,
            "constraints": policy_result.constraints,
            "details": policy_result.details,
        },
        "budget": {
            "total_eur": budget_result.total_eur,
            "summary": budget_result.summary,
            "currency": getattr(budget_result, "currency", "EUR"),
            "breakdown": [
                {"category": b.category, "amount_eur": b.amount_eur, "notes": b.notes}
                for b in budget_result.breakdown
            ],
        },
        "neighborhoods": [
            {
                "name": n.name,
                "area": n.area,
                "city": n.city,
                "score": n.score,
                "highlights": n.highlights,
                "avg_rent_1bed_eur": n.avg_rent_1bed_eur,
            }
            for n in neighborhoods
        ],
        "timeline": {
            "summary": timeline_result.summary,
            "total_weeks": timeline_result.total_weeks,
            "start_date": timeline_result.start_date,
            "phases": [
                {
                    "name": p.name,
                    "start_week": p.start_week,
                    "end_week": p.end_week,
                    "tasks": p.tasks,
                }
                for p in timeline_result.phases
            ],
        },
        "params_used": params,
    }


def _format_response(data: dict, user_message: str) -> str:
    """Format orchestration result as readable text. Optionally use ASI:One for natural reply."""
    policy = data["policy"]
    budget = data["budget"]
    neighborhoods = data["neighborhoods"]
    timeline = data["timeline"]
    params = data.get("params_used", {})

    city = params.get("destination_city") or "destination"
    currency = budget.get("currency", "EUR")
    sym = "$" if currency == "USD" else "€"
    sections = [
        "## Policy validation",
        policy["summary"],
        *([f"- {c}" for c in policy["constraints"]] if policy["constraints"] else []),
        "",
        "## Budget estimate",
        budget["summary"],
        *[f"- {b['category']}: {sym}{b['amount_eur']:,.2f}" for b in budget["breakdown"]],
        "",
        "## Neighborhood shortlist",
        f"Top areas in {city}:",
        *[
            f"- {n['name']} ({n['area']}): score {n['score']}"
            + (f", highlights: {', '.join(n['highlights'])}" if n.get("highlights") else "")
            + (f", ~{sym}{n['avg_rent_1bed_eur']}/mo 1-bed" if n.get("avg_rent_1bed_eur") else "")
            for n in neighborhoods
        ],
        "",
        "## Relocation timeline",
        timeline["summary"],
        *[f"- {p['name']} (weeks {p['start_week']}-{p['end_week']}): {'; '.join(p['tasks'])}" for p in timeline["phases"]],
    ]
    plain = "\n".join(sections)

    if ASI_ONE_API_KEY:
        try:
            client = OpenAI(
                base_url="https://api.asi1.ai/v1",
                api_key=ASI_ONE_API_KEY,
            )
            r = client.chat.completions.create(
                model="asi1",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the Employee Relocation Concierge. You received a user message and "
                            "have already computed: policy validation, budget estimate, neighborhood shortlist, "
                            "and a relocation timeline. Reply in a friendly, concise way. Include the key numbers "
                            "and next steps. Do not invent data—use only what is in the structured data. "
                            "Keep the reply under 400 words."
                        ),
                    },
                    {"role": "user", "content": f"User asked: {user_message}\n\nStructured data:\n{plain}"},
                ],
                max_tokens=1024,
            )
            return (r.choices[0].message.content or plain).strip()
        except Exception as e:
            if "401" in str(e) or "Unauthorized" in str(e):
                import logging
                logging.getLogger("relocation.concierge").warning(
                    "ASI:One API key invalid or expired (401). Check ASI_ONE_API_KEY in .env. Using plain response."
                )
            return plain
    return plain


# ---------------------------------------------------------------------------
# Chat Protocol handler
# ---------------------------------------------------------------------------
@protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    # Acknowledge receipt
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id),
    )

    text = ""
    for item in msg.content:
        if isinstance(item, TextContent):
            text += item.text

    if not text.strip():
        response_text = (
            "I'm the Employee Relocation Concierge. I can help with policy validation, "
            "budget estimation, neighborhood shortlisting, and a relocation timeline. "
            "Tell me your destination city and any details (e.g. family size, tenure) to get started."
        )
        await ctx.send(
            sender,
            ChatMessage(
                timestamp=datetime.utcnow(),
                msg_id=uuid4(),
                content=[
                    TextContent(type="text", text=response_text),
                    EndSessionContent(type="end-session"),
                ],
            ),
        )
        return

    try:
        text_clean = text.strip()
        # --- Book travel / pay for travel (Stripe) when eligible ---
        if text_clean and _wants_book_travel(text_clean) and is_stripe_configured():
            key = _state_key(sender)
            state = ctx.storage.get(key) or {}
            # Always create a fresh checkout when user says "book travel" so they get a new
            # payment option every time (after reject or timeout we don't re-send the old session).
            if "pending_stripe" in state:
                del state["pending_stripe"]
                ctx.storage.set(key, state)
            last_data = state.get("last_data") if isinstance(state.get("last_data"), dict) else None
            if not last_data:
                params = _extract_params(text_clean)
                data = _run_orchestration(params)
                state["last_data"] = data
                state["last_params"] = params
                ctx.storage.set(key, state)
                last_data = data
            else:
                data = last_data
            eligible = (data.get("policy") or {}).get("eligible", False)
            if not eligible:
                response_text = (
                    "Travel booking payment is only available when you're eligible under the relocation policy. "
                    "Check the policy validation above and meet the requirements first."
                )
                await ctx.send(
                    sender,
                    ChatMessage(
                        timestamp=datetime.utcnow(),
                        msg_id=uuid4(),
                        content=[
                            TextContent(type="text", text=response_text),
                            EndSessionContent(type="end-session"),
                        ],
                    ),
                )
                return
            travel_info = _get_travel_amount_and_currency(last_data)
            if not travel_info:
                response_text = "Could not determine travel amount from your relocation budget. Please ask for a full relocation quote first."
                await ctx.send(
                    sender,
                    ChatMessage(
                        timestamp=datetime.utcnow(),
                        msg_id=uuid4(),
                        content=[
                            TextContent(type="text", text=response_text),
                            EndSessionContent(type="end-session"),
                        ],
                    ),
                )
                return
            amount, currency = travel_info
            amount_cents = int(round(amount * 100))
            currency_lower = currency.lower() if currency else "usd"
            params_used = last_data.get("params_used") or {}
            origin = params_used.get("origin_city") or "origin"
            dest = params_used.get("destination_city") or "destination"
            description = f"Travel booking: {origin} → {dest}"
            checkout = await asyncio.to_thread(
                create_embedded_checkout_session,
                amount_cents=amount_cents,
                currency=currency_lower,
                description=description,
                user_address=sender,
                chat_session_id=str(ctx.session),
            )
            state = ctx.storage.get(key) or {}
            state["pending_stripe"] = checkout
            state["last_data"] = last_data
            ctx.storage.set(key, state)
            sym = "$" if currency == "USD" else "€"
            # Unique reference per payment so the UI shows a new payment card (not the old greyed-out one)
            payment_ref = str(uuid4())
            req = RequestPayment(
                accepted_funds=[
                    Funds(
                        currency=currency,
                        amount=f"{amount:.2f}",
                        payment_method="stripe",
                    )
                ],
                recipient=str(ctx.agent.address),
                deadline_seconds=300,
                reference=payment_ref,
                description=f"Pay {sym}{amount:,.2f} for relocation travel ({origin} → {dest}).",
                metadata={"stripe": checkout, "service": "relocation_travel", "payment_ref": payment_ref},
            )
            await ctx.send(sender, req)
            await ctx.send(
                sender,
                ChatMessage(
                    timestamp=datetime.utcnow(),
                    msg_id=uuid4(),
                    content=[
                        TextContent(
                            type="text",
                            text="Use the **payment form directly above** to complete your travel booking. If you see an older payment card that’s greyed out, scroll to this new one and click Pay / Confirm there.",
                        ),
                        EndSessionContent(type="end-session"),
                    ],
                ),
            )
            return
        # --- Normal relocation flow ---
        params = _extract_params(text)
        data = _run_orchestration(params)
        key = _state_key(sender)
        state = ctx.storage.get(key) or {}
        state["last_data"] = data
        state["last_params"] = params
        ctx.storage.set(key, state)
        response_text = _format_response(data, text)
        if (data.get("policy") or {}).get("eligible", False) and is_stripe_configured():
            response_text += "\n\nIf you'd like to book travel now, say **book travel** or **pay for travel**."
    except Exception as e:
        ctx.logger.exception("Error handling message")
        response_text = (
            "Sorry, something went wrong while processing your request. "
            "Please try again with a short message (e.g. 'Relocation to Berlin, family of 2'). "
            "If it keeps failing, the agent owner can check the server logs for details."
        )

    await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.utcnow(),
            msg_id=uuid4(),
            content=[
                TextContent(type="text", text=response_text),
                EndSessionContent(type="end-session"),
            ],
        ),
    )


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(protocol, publish_manifest=True)
agent.include(payment_protocol, publish_manifest=True)


if __name__ == "__main__":
    agent.run()
