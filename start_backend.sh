#!/bin/zsh
cd "$(dirname "$0")/backend"
exec /Users/jaswanthyamana/Desktop/agent/AgentScope/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
