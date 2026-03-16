#!/usr/bin/env python3
"""
Diagnose why the Relocation Concierge agent might not be working.
Run from project root: python scripts/diagnose.py
"""
import os
import sys
from pathlib import Path

# Project root = parent of scripts/
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main():
    print("=" * 60)
    print("Relocation Concierge – diagnostic")
    print("=" * 60)

    issues = []
    ok = []

    # 1. .env file
    env_path = ROOT / ".env"
    if not env_path.exists():
        issues.append(".env file is missing. Copy .env.example to .env and fill in values.")
    else:
        ok.append(".env file exists")
        from dotenv import load_dotenv
        load_dotenv(env_path)
        seed = os.getenv("RELOCATION_AGENT_SEED", "").strip()
        api_key = os.getenv("AGENTVERSE_API_KEY", "").strip()
        if not seed:
            issues.append("RELOCATION_AGENT_SEED is empty in .env. Set it to any long secret phrase (you choose it).")
        else:
            ok.append("RELOCATION_AGENT_SEED is set")
        if not api_key:
            issues.append("AGENTVERSE_API_KEY is empty in .env. Get it from agentverse.ai (profile/settings). Without it the agent won't register and will show as unreachable.")
        else:
            ok.append("AGENTVERSE_API_KEY is set")

    # 2. Dependencies
    try:
        from uagents import Agent
        ok.append("uagents imports OK")
    except Exception as e:
        issues.append(f"uagents import failed: {e}. Run: pip install -r requirements.txt")
        print("\n".join(ok))
        print("\nIssues:\n  - " + "\n  - ".join(issues))
        print("\nFix the issues above, then run: python run_agent.py")
        return 1

    # 3. Agent creation (no run)
    try:
        from relocation.concierge import agent
        ok.append("Agent loads OK (address: {}...)".format(agent.address[:20]))
    except Exception as e:
        issues.append("Agent failed to load: {}".format(e))
        print("\n".join(ok))
        print("\nIssues:\n  - " + "\n  - ".join(issues))
        return 1

    # 4. Is agent running right now?
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8001/health", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            ok.append("Agent is RUNNING and reachable at http://127.0.0.1:8001")
    except Exception:
        issues.append("Agent is not running or not reachable. Start it in another terminal: python run_agent.py")

    # Report
    print("\nOK:\n  " + "\n  ".join(ok))
    if issues:
        print("\nIssues (fix these first):\n  - " + "\n  - ".join(issues))
        print("\nThen:")
        print("  1. Ensure .env has RELOCATION_AGENT_SEED and AGENTVERSE_API_KEY")
        print("  2. Run: python run_agent.py")
        print("  3. You should see 'Mailbox access token acquired' (no 'No endpoints provided')")
        print("  4. Keep that terminal open and try ASI:One again")
        return 1
    else:
        print("\nNo obvious issues. If ASI:One still says unreachable:")
        print("  - Keep the terminal where run_agent.py is running open")
        print("  - Wait 30–60 seconds after starting, then try again")
        return 0

if __name__ == "__main__":
    sys.exit(main())
