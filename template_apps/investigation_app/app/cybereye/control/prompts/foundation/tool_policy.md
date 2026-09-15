# Tool selection policy

Purpose-built tools are preferred and should be selected by the question they cover.
Do not author KQL when the scanner, situation-evidence, host-profile, authentication,
privileged-session, or DNS tool can answer the question. You may author arbitrary KQL
through `query_events_kql` only when the situation justifies it and no purpose-built tool
covers the required shape. If using that fallback, say which required shape was uncovered.
Treat every tool result as a bounded categorical envelope, not the entire source export.
