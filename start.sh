#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Ascentir Outreach OS — start the dashboard
#  Run:  ./start.sh   (from any terminal)
# ─────────────────────────────────────────────────────────────

# Go to project folder no matter where you run this from
cd "$(dirname "$0")"

# Unset any shell-level API key overrides so .env is always the source of truth.
# If ANTHROPIC_API_KEY is exported in ~/.zshrc it will silently override .env — prevent that.
unset ANTHROPIC_API_KEY
unset OPENAI_API_KEY

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║     Ascentir Outreach OS             ║"
echo "  ║     Starting dashboard…              ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  → Open in browser: http://localhost:8000"
echo "  → Press Ctrl+C to stop"
echo ""

python3 -m src.dashboard
