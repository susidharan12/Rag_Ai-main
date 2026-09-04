"""Track E docs-answer judge validation.

    python eval/judge.py

Offline and deterministic - no API key, no hosted model - so agreement can
be rerun identically at any time. judge_v1 is a naive baseline (topical
overlap + "looks cited"). It decides a single binary criterion only: does
the answer directly and correctly answer the question? The four
deterministic assertions (code_sample_parses, endpoint_exists,
api_version_stated, deprecated_symbol_migration) are handled exclusively
by eval/run_eval.py and are never re-litigated here.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS_PATH = os.path.join(HERE, "labels_25.json")

REFUSAL = "i could not find the answer in the provided documents"


def load_cases():
    return json.loads(open(LABELS_PATH, encoding="utf-8").read())["labels"]


def judge_v1(case):
    """Naive judge: shares question vocabulary and looks cited => helpful."""
    answer = case["answer"].lower()
    question_terms = set(re.findall(r"[a-z0-9_]+", case["question"].lower()))
    overlap = len(question_terms & set(re.findall(r"[a-z0-9_]+", answer)))
    looks_cited = "[" in answer or REFUSAL in answer
    return int(bool(overlap >= 2 and looks_cited))


# The two real judge_v1 disagreements chosen for the v2 few-shot (see
# eval/prediction.txt, committed before this function existed):
#   eval_019 - false negative: v1 rejected a correct refusal because the
#     refusal sentence shares almost no vocabulary with the question.
#   eval_022 - false positive: v1 accepted an answer that states an
#     unrelated fact instead of the specific thing actually asked about.
JUDGE_V2_FEWSHOT = ("eval_019", "eval_022")


def judge_v2(case):
    """judge_v1 plus two rules learned from JUDGE_V2_FEWSHOT."""
    answer = case["answer"].lower()
    question = case["question"].lower()

    # From eval_019: a correct refusal shouldn't need to share topical
    # vocabulary with the question to be recognized as correct - the exact
    # refusal sentence is itself the signal.
    if REFUSAL in answer:
        return 1

    # From eval_022: a question asking for a specific undocumented
    # limit/size/detail ("maximum ... size/payload") that the answer
    # doesn't actually name (it names an unrelated limit instead) is not a
    # real answer, even though it shares surface vocabulary like "size".
    if re.search(r"\b(maximum|max)\b.*\b(size|payload)\b", question) and \
            "payload" not in answer:
        return 0

    return judge_v1(case)


def write_judge_artifact(version, cases, decisions, extra_header_lines=None):
    path = os.path.join(HERE, f"judge_{version}.txt")
    lines = [
        f"Track E docs-answer binary judge {version}",
        "Single judged criterion: does the answer directly and correctly answer the question?",
        "Deterministic assertions are excluded (handled by eval/run_eval.py): "
        "code_sample_parses, endpoint_exists, api_version_stated, deprecated_symbol_migration.",
    ]
    if extra_header_lines:
        lines += extra_header_lines
    lines.append("")
    lines.append("id\tmode\thuman\tjudge")
    for case, decision in zip(cases, decisions):
        lines.append(f"{case['id']}\t{case['mode']}\t{case['human_label']}\t{decision}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    cases = load_cases()
    v1 = [judge_v1(c) for c in cases]
    write_judge_artifact("v1", cases, v1)

    before = sum(a == c["human_label"] for a, c in zip(v1, cases))
    dis_v1 = [c["id"] for a, c in zip(v1, cases) if a != c["human_label"]]

    v2 = [judge_v2(c) for c in cases]
    write_judge_artifact("v2", cases, v2, extra_header_lines=[
        f"Few-shot disagreement 1 (from v1): {JUDGE_V2_FEWSHOT[0]} was judged "
        f"not-helpful by v1 (false negative), but the human label is 1 - the "
        f"exact refusal sentence shares almost no vocabulary with the question, "
        f"so v1's overlap-based check rejected a correct refusal.",
        f"Few-shot disagreement 2 (from v1): {JUDGE_V2_FEWSHOT[1]} was judged "
        f"helpful by v1 (false positive), but the human label is 0 - the answer "
        f"states an unrelated pagination limit instead of the undocumented "
        f"payload-size detail the question actually asked about.",
        "Iteration rule: trust the exact refusal sentence without requiring "
        "topical overlap, and reject an answer to a 'maximum size/payload' "
        "question that never names the payload.",
    ])
    after = sum(a == c["human_label"] for a, c in zip(v2, cases))
    dis_v2 = [c["id"] for a, c in zip(v2, cases) if a != c["human_label"]]

    print("Track E docs-answer judge validation")
    print(f"cases: {len(cases)} | judged criteria: 1 (binary, no scale)")
    print(f"agreement_before (v1): {before}/{len(cases)} = {before / len(cases) * 100:.1f}%")
    print(f"v1 disagreements ({len(dis_v1)}): {', '.join(dis_v1)}")
    print(f"agreement_after  (v2): {after}/{len(cases)} = {after / len(cases) * 100:.1f}%")
    print(f"v2 disagreements ({len(dis_v2)}): {', '.join(dis_v2)}")
    print(f"\nfew-shot used for v2: {', '.join(JUDGE_V2_FEWSHOT)}")
    print("Artifacts: judge_v1.txt, judge_v2.txt")


if __name__ == "__main__":
    main()
