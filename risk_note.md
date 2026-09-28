Supply-Chain Risk Note: package-registry MCP Server

1. Author: DevRel team (internal), no third-party audit or SBOM published.
2. Reach: Reads public PyPI metadata (versions, dates, deprecation notices); no network egress beyond registry API; no local filesystem access.
3. Logs: Tool calls (package_name, version) and results emitted to stdout/stderr; no PII, but query patterns reveal internal package interests.
4. Stolen token impact: If server runs with an authenticated PyPI token, thief could publish malicious packages or yank legitimate ones — agent's tool list would then serve poisoned metadata.
5. Verdict: Ship with read-only PyPI access (no publish token), pin server version, and monitor tool-call logs for anomalous package queries.