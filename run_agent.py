#!/usr/bin/env python3
"""
Run the Employee Relocation Concierge agent.
From project root: python run_agent.py
"""
import sys
from pathlib import Path

# Ensure project root is on path
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from relocation.concierge import agent

if __name__ == "__main__":
    agent.run()
