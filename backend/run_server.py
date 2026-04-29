"""Launcher: sets sys.path then starts uvicorn programmatically."""
import sys, os

# Ensure backend/ is on the path, regardless of where this script is invoked from
BACKEND = os.path.dirname(os.path.abspath(__file__))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import uvicorn
uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")
