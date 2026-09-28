"""Week 8 - Agent Failure Modes & Trajectory Evals.

Builds a trajectory-level evaluation on top of the Week 7 ReAct agent
(rag_core.agent.run_agent) to answer a question outcome scoring alone
can't: did the agent get the right answer for the right reason (by
actually executing the tools the question requires), or did it get lucky?

See REPORT.md for the write-up (gap number, false-positive trace, the one
mitigation applied, and the before/after regression matrix) and
trajectory_eval.py to reproduce it.
"""
