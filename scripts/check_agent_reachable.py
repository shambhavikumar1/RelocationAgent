#!/usr/bin/env python3
"""
Check if the Relocation Concierge agent is reachable (server running and responding).
Run this while the agent is running in another terminal.
Usage: python scripts/check_agent_reachable.py
"""
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8001"


def main():
    for path in ("/health", "/agent_info"):
        url = BASE + path
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode()
                print(f"OK {path} -> {resp.status} ({len(body)} bytes)")
        except urllib.error.URLError as e:
            print(f"FAIL {path} -> {e}")
            if "Connection refused" in str(e) or "nodename" in str(e):
                print("  -> Is the agent running? Start it with: python run_agent.py")
            sys.exit(1)
        except Exception as e:
            print(f"FAIL {path} -> {e}")
            sys.exit(1)
    print("\nAgent is reachable. You can open the Inspector URL from the agent terminal.")
    print("If mailbox connection still fails, allow Local Network Access for agentverse.ai in your browser.")


if __name__ == "__main__":
    main()
