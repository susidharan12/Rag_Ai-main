"""Track E - one-command evaluator.

    python eval/run_eval.py

Ingests the Nimbus SDK corpus (corpus/nimbus_sdk/{v2,v3}/*.md + the sports
PDF - the same source set as week5_error_analysis/ingest_corpus.py) into an
isolated index under eval/.eval_index/, so this command is self-contained
and reproducible without depending on, or polluting, the live app's
data/index/. Runs every case in eval_cases.json through the deterministic
extractive-v2 generator (no LLM key required, fully replayable), applies
the 4 deterministic assertions, and writes eval/results.json.
"""

import ast
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

EVAL_INDEX_DIR = os.path.join(HERE, ".eval_index")
os.environ.setdefault("RAG_DATA_DIR", EVAL_INDEX_DIR)

from rag_core.pipeline import ask_sync  # noqa: E402
from rag_core.store import DocStore  # noqa: E402

CASES_PATH = os.path.join(HERE, "eval_cases.json")
RESULTS_PATH = os.path.join(HERE, "results.json")
OPENAPI_PATH = os.path.join(HERE, "openapi_paths.json")

REFUSAL = "i could not find the answer in the provided documents"

# No literal "deprecated" symbol exists in the corpus/nimbus_sdk docs (v2 is
# described as "in maintenance mode", not a deprecated symbol with a named
# migration target) - this map stays empty rather than inventing one, so the
# assertion honestly reports 0 applicable cases.
DEPRECATED_SYMBOLS = {}


def _ensure_index_built():
    store = DocStore()
    store.ensure_loaded()
    if store.stats()["documents"] > 0:
        return store

    import glob
    for path in sorted(glob.glob(os.path.join(REPO_ROOT, "corpus", "nimbus_sdk", "v*", "*.md"))):
        with open(path, "rb") as f:
            store.add_document(path, f.read())
    pdf = os.path.join(REPO_ROOT, "documents", "Complete_Guide_to_Major_World_Sports.pdf")
    if os.path.exists(pdf):
        with open(pdf, "rb") as f:
            store.add_document(pdf, f.read())
    return store


def _code_parses(answer):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", answer,
                         flags=re.IGNORECASE | re.DOTALL)
    if not blocks:
        return None  # not applicable
    return all(_parses(b) for b in blocks)


def _parses(source):
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


def _endpoint_exists(answer):
    mentioned = set(re.findall(r"/(?:v2|v3)/[A-Za-z0-9_/{}-]+", answer))
    if not mentioned:
        return None
    known = set(json.loads(open(OPENAPI_PATH, encoding="utf-8").read())["paths"]) \
        if os.path.exists(OPENAPI_PATH) else set()
    return mentioned <= known


def _version_stated(answer, expected_version):
    if not expected_version:
        return None
    low = answer.lower()
    if expected_version == "v2/v3":
        return "v2" in low and "v3" in low
    return expected_version in low or "maintenance" in low


def _deprecated_migration(answer):
    low = answer.lower()
    hits = [s for s in DEPRECATED_SYMBOLS if s in low]
    if not hits:
        return None
    return all(DEPRECATED_SYMBOLS[s].lower() in low for s in hits)


def deterministic_assertions(case, answer):
    return {
        "code_sample_parses": _code_parses(answer),
        "endpoint_exists": _endpoint_exists(answer),
        "api_version_stated": _version_stated(answer, case.get("expected_version")),
        "deprecated_symbol_migration": _deprecated_migration(answer),
    }


def run_case(case, store):
    payload, _trace = ask_sync(case["question"], generator="extractive",
                                store=store, surface="eval")
    answer = payload["answer"]
    refused = payload["refused"]

    if case["expect"] == "refuse":
        app_pass = refused
    else:
        app_pass = (not refused) and all(
            tok.lower() in answer.lower() for tok in case.get("expected_tokens", []))

    return {
        "id": case["id"],
        "mode": case["mode"],
        "question": case["question"],
        "answer": answer,
        "refused": refused,
        "expect": case["expect"],
        "app_pass": app_pass,
        "assertions": deterministic_assertions(case, answer),
    }


def main():
    cases = json.loads(open(CASES_PATH, encoding="utf-8").read())["cases"]
    store = _ensure_index_built()

    results = [run_case(c, store) for c in cases]

    by_mode = defaultdict(list)
    for r in results:
        by_mode[r["mode"]].append(r)

    total_pass = sum(r["app_pass"] for r in results)

    assertion_names = ("code_sample_parses", "endpoint_exists",
                        "api_version_stated", "deprecated_symbol_migration")
    assertion_summary = {}
    for name in assertion_names:
        vals = [r["assertions"][name] for r in results]
        applicable = [v for v in vals if v is not None]
        assertion_summary[name] = {
            "applicable": len(applicable),
            "passed": sum(1 for v in applicable if v),
            "failed": sum(1 for v in applicable if not v),
            "na": len(vals) - len(applicable),
        }

    out = {
        "cases": len(results),
        "application_pass": total_pass,
        "application_pass_rate": round(total_pass / len(results) * 100, 1),
        "by_mode": {
            mode: {
                "pass": sum(r["app_pass"] for r in rows),
                "total": len(rows),
                "rate": round(sum(r["app_pass"] for r in rows) / len(rows) * 100, 1),
            }
            for mode, rows in sorted(by_mode.items())
        },
        "deterministic_assertions": assertion_summary,
        "judged_criteria": 1,
        "results": results,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print("Track E - one-command eval")
    print(f"cases: {out['cases']} | application pass: {total_pass}/{len(results)} "
          f"= {out['application_pass_rate']}%")
    print()
    print("mode\tpass\ttotal\trate")
    for mode, m in out["by_mode"].items():
        print(f"{mode}\t{m['pass']}\t{m['total']}\t{m['rate']}%")
    print()
    print("deterministic assertions (applicable / passed / failed / n_a)")
    for name, s in assertion_summary.items():
        print(f"{name}\t{s['applicable']}\t{s['passed']}\t{s['failed']}\t{s['na']}")
    print()
    print(f"Wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
