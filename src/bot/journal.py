""" Reasoning log with one JSON line per reasoning cycle.
Used to keep track of AI reasoning for LTP hackathon.
"""

import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("bot.journal")

JOURNAL_DIR = "data"
JOURNAL_PATH = os.path.join(JOURNAL_DIR, "decisions.jsonl")

def record(entry: dict) -> None:
    """ Append one cycle record as a single JSON line. """
    try:
        os.makedirs(JOURNAL_DIR, exist_ok=True)
        stamped = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
        with open(JOURNAL_PATH, "a") as f:
            f.write(json.dumps(stamped, default=str) + "\n")
    except Exception:
        log.exception("Failed to write journal entry ; continuing anyway.")
        