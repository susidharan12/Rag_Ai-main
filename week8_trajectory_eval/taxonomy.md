# Failure Taxonomy — Week 8 Trajectory Evals

Classifier: `taxonomy.classify()`. Applied to the real ReAct agent
(`rag_core.agent.run_agent`) running over the same 10 real migration/
comparison scenarios `week7_agent/race.py` already outcome-scores
(`corpus/dev_docs` — GitHub REST API + Swagger Codegen v2/v3 reference
PDFs). A run can carry more than one tag. See `REPORT.md` for the actual
before/after counts from a real run.

| Mode | Trajectory FAIL? | What it catches | Evidence source |
|---|:---:|---|---|
| `no_tool_before_finish` | ✅ | Agent answered with **zero** tool calls — reciting a plausible answer instead of executing the spec-lookup tool, the exact failure this assignment names. | `tools_used` empty |
| `missing_required_tool` | ✅ | A query-mandatory follow-up tool (`check_deprecation` on the 4 "step 3 depends on step 2" questions — H01/H04/H06/H08) never ran. | required-tool set vs. actual tools |
| `wrong_tool_choice` | ✅ | An error-code / parameter-default lookup tool was called on a version-migration question — the agent misread the question's category. | `queries.DISALLOWED_TOOLS` |
| `invalid_argument` | ✅ | A tool argument that a Pydantic schema can't catch (free-form `version`/`query` strings) was semantically wrong — a version not named in the question, or a blank query. | `taxonomy._is_valid_arg_step` |
| `redundant_repeat` | — | The exact same `(tool, args)` pair called more than once — wasted step budget, no new evidence. | duplicate `(tool, args)` keys |
| `premature_stop_parse_error` | — | Run ended with `stopped_by == "parse_error"` — the LLM's step output failed to parse as JSON and (pre-mitigation) the loop aborted right there, however few tools had run. | `metrics.stopped_by` |

`✅` = disqualifying (fails the trajectory, independent of outcome score).
`—` = tracked for the regression matrix / step-efficiency numbers, but
doesn't by itself fail an otherwise-clean run (a run can repeat a call or
hit a parse error yet still finish having gathered everything the
question required).

## Why `missing_required_tool` is the one targeted by the mitigation

`week7_agent/race.py`'s own historical race already recorded, before
Week 8 existed, that the agent called `check_deprecation` on **0 of the 4**
dependency questions (`race_results.json["summary"]["dependency_questions"]`).
Re-running those same 4 questions here confirms the mechanism: the loop's
*second* LLM call frequently returns text that doesn't parse as the
required `{"thought","tool","args"}` JSON, and — pre-mitigation — a parse
failure aborts the loop immediately (`stopped_by="parse_error"`), often
after only 1 (sometimes 0) tool calls, well before `check_deprecation` (or
sometimes any tool at all) has run. `premature_stop_parse_error` is the
single most common tag across all 10 questions in the "before" run (see
`REPORT.md`), which is why it's the mitigation target, not a hand-picked
one.
