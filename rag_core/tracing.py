"""Structured JSONL trace logging.

Every question that flows through the pipeline appends one trace object to
traces.jsonl. The schema carries every field the Week 5 replay contract
needs: trace_id, prompt_version, retrieved chunk_ids + scores, model +
params and the raw output.

Objects are pretty-printed (one key per line) so a human can grep the file,
and parsed back with json.JSONDecoder.raw_decode.
"""

import datetime
import json
import os
import uuid

from rag_core import settings

_DECODER = json.JSONDecoder()


def new_trace_id():
    now = datetime.datetime.utcnow()
    return f"tr_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def write_trace(trace, path=None):
    path = path or settings.TRACES_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(trace, indent=2, ensure_ascii=False))
        f.write("\n")
    return trace


def read_traces(path=None):
    """Parse the pretty-printed multi-object JSONL file."""

    path = path or settings.TRACES_PATH
    traces = []
    if not os.path.exists(path):
        return traces
    text = open(path, encoding="utf-8").read().strip()
    idx = 0
    while idx < len(text):
        obj, next_idx = _DECODER.raw_decode(text, idx)
        traces.append(obj)
        idx = _skip_ws(text, next_idx)
    return traces


def _skip_ws(text, idx):
    while idx < len(text) and text[idx] in " \t\r\n":
        idx += 1
    return idx
