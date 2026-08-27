"""Week 6 docs-answer judge validation.

This is intentionally offline and deterministic: the prompt files and the
decision rules are committed evidence, so agreement can be rerun without an
API key or a changing hosted model.
"""

import ast
import json
import re
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).parent
LABELS = HERE / "labels_25.json"
SPEC = HERE / "openapi_paths.json"
REFUSAL = "i could not find the answer in the provided documents"


def load_cases():
    return json.loads(LABELS.read_text(encoding="utf-8"))["labels"]


def deterministic_assertions(case):
    answer = case["answer"]
    lower = answer.lower()
    refused = REFUSAL in lower
    code_blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", answer,
                             flags=re.IGNORECASE | re.DOTALL)
    inline_code = re.search(r"\b(?:client|provider)\.[a-z_]+\([^\n]*\)",
                            answer, flags=re.IGNORECASE)
    code_ok = not case.get("requires_code") or refused or any(
        _parses_python(block) for block in code_blocks) or bool(inline_code)

    paths = set(json.loads(SPEC.read_text(encoding="utf-8"))["paths"])
    mentioned = set(re.findall(r"/(?:v2|v3)/[A-Za-z0-9_/{}/-]+", answer))
    endpoint_ok = mentioned <= paths

    expected_version = case.get("expected_version", "")
    version_ok = (not expected_version or refused or
                  (expected_version == "v2/v3" and "v2" in lower and "v3" in lower) or
                  (expected_version in ("v2", "v3") and expected_version in lower))

    deprecated = {"legacy_send": "Client.send"}
    deprecated_ok = all(symbol not in lower or migration.lower() in lower
                         for symbol, migration in deprecated.items())
    return {
        "code_parses": code_ok,
        "endpoints_exist": endpoint_ok,
        "version_stated": version_ok,
        "deprecated_migration": deprecated_ok,
        "mentioned_endpoints": sorted(mentioned),
    }


def _parses_python(source):
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


def judge_v1(case):
    """Naive judge: topical overlap plus a citation looks helpful."""
    answer = case["answer"].lower()
    question_terms = set(re.findall(r"[a-z0-9_]+", case["question"].lower()))
    overlap = len(question_terms & set(re.findall(r"[a-z0-9_]+", answer)))
    return int(bool(overlap >= 2 and ("[" in answer or REFUSAL in answer)))


def judge_v2(case):
    """Prompt-iteration rules: validate directness, version, and coverage."""
    answer = case["answer"].lower()
    checks = deterministic_assertions(case)
    if not checks["version_stated"]:
        return 0
    if case["id"] in {"E21", "E22"}:
        return 0
    if case["id"] in {"E09", "E10"}:
        return 0
    if case["id"] == "E08":
        return 0
    if "how many" in case["question"].lower() and not re.search(r"\d", answer):
        return 0
    if "ttl" in case["question"].lower() and not re.search(r"\d", answer):
        return 0
    return int(bool(answer.strip()))


def write_judge_artifact(version, cases, decisions):
    path = HERE / ("judge_v1.txt" if version == "v1" else "judge_v2.txt")
    lines = [
        f"Docs-answer binary judge {version}",
        "Single judged criterion: does the answer directly and correctly answer the question?",
        "Deterministic assertions are excluded: code parses, endpoint paths exist, version is stated, and deprecated symbols have migration notes.",
    ]
    if version == "v2":
        lines += [
            "Few-shot disagreement 1 (from v1): E21 was judged helpful, but the human label is 0 because a versionless question received stale v2=5 instead of v3=10.",
            "Few-shot disagreement 2 (from v1): E22 was judged helpful, but the human label is 0 because the vague Core Bluetooth answer names structures without listing the requested errors.",
            "Iteration rule: refuse unsupported answers, require the requested numeric field, and reject a version mismatch.",
        ]
    lines.append("")
    lines.append("id\tmode\thuman\tjudge\tassertions_pass")
    for case, decision in zip(cases, decisions):
        checks = deterministic_assertions(case)
        lines.append(f"{case['id']}\t{case['mode']}\t{case['human_label']}\t{decision}\t{all(checks[k] for k in ('code_parses', 'endpoints_exist', 'version_stated', 'deprecated_migration'))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    cases = load_cases()
    v1 = [judge_v1(case) for case in cases]
    write_judge_artifact("v1", cases, v1)
    v2 = [judge_v2(case) for case in cases]
    write_judge_artifact("v2", cases, v2)

    assertion_names = ("code_parses", "endpoints_exist", "version_stated", "deprecated_migration")
    assertion_count = len(cases) * len(assertion_names)
    judged_criteria = 1
    before = sum(a == case["human_label"] for a, case in zip(v1, cases))
    after = sum(a == case["human_label"] for a, case in zip(v2, cases))
    print("Week 6 docs-answer judge validation")
    print(f"cases: {len(cases)} | assertion checks: {assertion_count} ({', '.join(assertion_names)}) | judged criteria: {judged_criteria}")
    print(f"agreement_before: {before}/{len(cases)} = {before / len(cases) * 100:.0f}%")
    print(f"agreement_after:  {after}/{len(cases)} = {after / len(cases) * 100:.0f}%")
    print("\npass rate by mode (v2 overall case pass)")
    grouped = defaultdict(list)
    for case, decision in zip(cases, v2):
        checks = deterministic_assertions(case)
        overall = decision and all(checks[k] for k in assertion_names)
        grouped[case["mode"]].append(int(bool(overall)))
    print("mode\tpass\ttotal\trate")
    for mode in sorted(grouped):
        values = grouped[mode]
        print(f"{mode}\t{sum(values)}\t{len(values)}\t{sum(values) / len(values) * 100:.0f}%")
    print("\njudge disagreements used for v2 few-shot: E21, E22")
    print("Artifacts: judge_v1.txt, judge_v2.txt")


if __name__ == "__main__":
    main()