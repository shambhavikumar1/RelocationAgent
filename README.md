# Multi-Agent Employee Relocation Concierge

An **Employee Relocation Concierge** that orchestrates **policy validation**, **budget estimation**, **neighborhood shortlisting** (via API/tool), and **relocation timeline generation**. Built with the [uAgents](https://uagents.fetch.ai/) framework, **Chat Protocol** compatible for [Agentverse](https://agentverse.ai/) and discoverable via [ASI:One](https://asi1.ai/).

## Capabilities

| Component | Description |
|-----------|-------------|
| **Policy validation** | Validates eligibility and constraints (tenure, role, distance, allowance limits). |
| **Budget estimation** | Estimates moving, travel, temporary housing, and settling allowance (EUR). |
| **Neighborhood shortlisting** | Shortlists neighborhoods by city using **OpenStreetMap** (Nominatim geocode + Overpass API) for real suburb/neighbourhood data; optional custom API via `NEIGHBORHOOD_API_URL`, then Teleport or mock fallback. |
| **Timeline generation** | Produces a phased relocation timeline from approval to move-in. |

The concierge runs these four steps in sequence for each user request and returns a single, consolidated response.

## Quick start

### 1. Install dependencies

```bash
cd /path/to/Relocation
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env: set RELOCATION_AGENT_SEED (required), optionally AGENTVERSE_API_KEY and ASI_ONE_API_KEY
```

**Not working?** Run the diagnostic: `python scripts/diagnose.py` — it checks .env, keys, and whether the agent is running, and suggests what to fix.

- **RELOCATION_AGENT_SEED**: Any stable string (e.g. 12+ words). Defines the agent’s identity.
- **AGENTVERSE_API_KEY**: From [Agentverse](https://agentverse.ai/) — when set, the agent starts with mailbox enabled; you then complete the connection by opening the Inspector URL (printed in the terminal) and clicking **Connect → Mailbox** in the browser. If you see “Something went wrong while proving mailbox connection”, see [Troubleshooting](#troubleshooting-something-went-wrong-while-proving-mailbox-connection) below.
- **ASI_ONE_API_KEY**: From [ASI:One](https://asi1.ai/dashboard/api-keys) — optional; used to format replies with the ASI:One model.
- **NEIGHBORHOOD_API_URL**: Optional. If set, neighborhood shortlisting uses this API instead of the default (OpenStreetMap geolocation). Expected: `GET {url}/neighborhoods?city=...&limit=...`.

### 3. Run the agent

From the project directory, run:

```bash
python run_agent.py
```

(You must use `python run_agent.py` — not just `run_agent.py` — so the script is executed by Python.)

The agent listens on `http://0.0.0.0:8001`. With `AGENTVERSE_API_KEY` set, it will use the Agentverse mailbox and register on the Almanac.

---

## Register on Agentverse and be discoverable via ASI:One

To have your Concierge **registered on Agentverse** and **discoverable via ASI:One**:

1. **Sign up** at [Agentverse](https://agentverse.ai/) and get an **API key** (e.g. from your profile/settings).
2. **Run the agent** with a **reachable endpoint** (see below).
3. In Agentverse: **Launch Agents → Launch an Agent**.
4. Enter:
   - **Agent name**: e.g. `Employee Relocation Concierge`
   - **Agent endpoint**: the URL where the agent is reachable (e.g. `http://your-host:8001` or your tunnel URL).
5. Select **Chat Protocol**.
6. If you are **not** using the uAgents framework’s built-in registration, Agentverse will give you a **registration script**; add your **Agentverse API key** and **seed phrase** (same as `RELOCATION_AGENT_SEED`), then run it.
7. Click **Evaluate Registration** in Agentverse to verify the agent is reachable.
8. Add **keywords** for discovery, e.g. `relocation`, `employee relocation`, `HR`, `policy`, `budget`, `moving`.

Your agent will then appear in Agentverse and can be discovered and used via **ASI:One** (e.g. [ASI:One Chat](https://asi1.ai/chat)).

### Making the agent reachable

- **Local development**: Use a tunnel (e.g. [ngrok](https://ngrok.com/) or similar) so Agentverse can reach your machine, and use that URL as the agent endpoint.
- **Production**: Deploy the agent on a server with a public URL and use that as the endpoint.

### "Agent is currently unreachable" on Agentverse / ASI:One

When Agentverse or ASI:One shows **"An internal error occurred"** or **"relocation-concierge is currently unreachable"**, it means requests cannot reach your agent. Check the following:

| Cause | What to do |
|-------|------------|
| **Agent not running** | Start the agent and keep it running: `python run_agent.py`. Leave the terminal open. Agentverse/ASI:One can only deliver messages when the agent process is up. |
| **Using Mailbox** | With mailbox, your agent *polls* Agentverse for new messages. If the agent stops or loses connection, it stops polling and Agentverse marks it unreachable. Restart the agent and wait until you see e.g. "Mailbox access token acquired" (and, if applicable, "Successfully registered as mailbox agent"). |
| **Using a public URL (e.g. ngrok)** | If you registered an endpoint like `https://xxxx.ngrok.io`, the tunnel must be running on your machine whenever you want the agent to be reachable. Restart ngrok and, if the URL changed, update the agent endpoint in Agentverse. |
| **Firewall / network** | If the agent runs on a server, ensure port 8001 (or your chosen port) is open and reachable from the internet. |

**Quick check:** In the terminal where you ran `python run_agent.py`, you should see the server and (if mailbox is on) mailbox logs. If that terminal is closed or the process exited, the agent is down and will show as unreachable until you start it again.

### References

- [Launch ASI:One compatible uAgent (Agentverse)](https://docs.agentverse.ai/documentation/launch-agents/launch-asi-one-compatible-u-agent)
- [Agent setup & discovery (Agentverse)](https://docs.agentverse.ai/documentation/agent-discovery/agent-setup-guide)
- [Create an ASI:One compatible Agent (uAgents)](https://uagents.fetch.ai/docs/examples/asi-1)

---

## Troubleshooting: “Something went wrong while proving mailbox connection”

This message usually appears in the **Agentverse Inspector** (in your browser) when you click **Connect → Mailbox**. The “prove” step is when Agentverse checks that it can reach your local agent. Try the following:

1. **Agent must be running**  
   Start the agent with `python run_agent.py` and leave it running. You should see `Starting server on http://0.0.0.0:8001` in the terminal.

2. **Use the Inspector URL from the terminal**  
   After the agent starts, the terminal prints a line like:  
   `Agent inspector available at https://agentverse.ai/inspect/?uri=...&address=...`  
   Open **that exact URL** in your browser (do not change the `uri` or `address`).

3. **Allow Local Network Access (Chrome/Brave)**  
   Newer Chrome and Brave versions can block the Inspector from reaching your machine. When you open the Inspector, if you see a prompt like **“Allow this site to access devices on your local network”**, click **Allow**.  
   If you dismissed it: **Chrome → Settings → Privacy and security → Site settings → Additional permissions → Local network access** and allow **agentverse.ai**.

4. **Log in to Agentverse**  
   Use the same browser where you opened the Inspector, and make sure you are **signed in** at [agentverse.ai](https://agentverse.ai/). On the free tier, logging in at least once every 30 days keeps your mailbox active.

5. **No custom endpoint when using Inspector**  
   For a **local** mailbox connection, the Inspector expects the agent at `http://127.0.0.1:8001`. Do not set an `endpoint` in code for this flow; the terminal URL already points to 127.0.0.1.

6. **Run without mailbox first**  
   To confirm the agent works, you can run **without** `AGENTVERSE_API_KEY` in `.env`. The agent will start and serve on port 8001; you just won’t get mailbox registration. Then add the key back and try the Inspector again.

**Find the real error:**  
- **Browser:** F12 → Network tab; click Connect → Mailbox and see if the request to `127.0.0.1:8001` fails (blocked, CORS, or Local Network Access).  
- **Agent terminal:** Look for `Failed to prove authorization: ...` or a stack trace; that often shows the Agentverse response (e.g. invalid token, subscription expired).

**Verify the agent is reachable:** run `python scripts/check_agent_reachable.py` in a second terminal while the agent is running. If that fails, the browser cannot reach your agent.

If it still fails, see [docs/MAILBOX_TROUBLESHOOTING.md](docs/MAILBOX_TROUBLESHOOTING.md) and [Agentverse agent logs & errors](https://docs.agentverse.ai/documentation/advanced-usages/agent-logs-errors).

### "Can not decode content-encoding: br" or "process() takes exactly 1 argument (2 given)"

Agentverse may send Brotli-compressed responses; the HTTP client (aiohttp) needs a compatible Brotli decoder. Install it with:

```bash
pip install "brotlicffi>=1.2.0"
```

(Quotes prevent zsh from misparsing `>=`.) Then restart the agent. If you use `requirements.txt`, run `pip install -r requirements.txt` (it includes `brotlicffi`).

---

## Project layout

```
Relocation/
├── README.md
├── requirements.txt
├── .env.example
├── run_agent.py              # Entrypoint: python run_agent.py
└── relocation/
    ├── __init__.py
    ├── concierge.py          # Main agent (Chat Protocol + orchestration)
    └── services/
        ├── __init__.py
        ├── policy.py         # Policy validation
        ├── budget.py         # Budget estimation
        ├── neighborhood.py   # Neighborhood shortlisting (API or mock)
        └── timeline.py       # Timeline generation
```

## Neighborhood data: OpenStreetMap (geolocation API)

By default, neighborhood shortlisting uses the **Teleport API** ([api.teleport.org](https://api.teleport.org/)) — free, no API key. It provides:

- **City-level scores** (Housing, Cost of Living, Safety, Healthcare, etc.) for 200+ urban areas.
- **Quality-of-life categories** shown as neighborhood “highlights”.
- Optional cost/salary details when available.

City names are matched to Teleport urban area slugs (e.g. Berlin, London, Munich, Paris, Amsterdam, Vienna, Dublin, and many more); unknown cities are resolved via Teleport’s search API. Well-known district names (e.g. Mitte, Kreuzberg for Berlin) are added from a small built-in list so results include both real API data and area names. If Teleport is unavailable or the city isn’t found, the service falls back to built-in mock data.

## Example interaction

User (e.g. via ASI:One Chat or a client):

> I’m relocating to Berlin with my family of 3. Can you give me a budget and neighborhood shortlist?

The concierge will:

1. **Validate policy** (tenure, role, distance, allowance).
2. **Estimate budget** (moving, travel, temp housing, settling) for Berlin and family size 3.
3. **Shortlist neighborhoods** for Berlin (OpenStreetMap geolocation for real suburb/neighbourhood names, or your custom API if set).
4. **Generate a timeline** (phases from approval to move-in).

The reply will combine policy outcome, budget breakdown, top neighborhoods, and timeline in one response (optionally formatted by ASI:One if `ASI_ONE_API_KEY` is set).

## License

Apache-2.0.
