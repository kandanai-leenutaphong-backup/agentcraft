---
name: situation-detector
description: "Use when configurable query-test rules must run over explicit time windows and produce ordered observations, stable configuration digests, or streamed results. Includes a domain-neutral synchronous/asynchronous battery and refusal tests. Hosts provide queries and processing; this skill executes no configuration-supplied code itself."
---

# Situation Detector

Use installed `situation-detector`; import `situation_detector`.
Read the [canonical skill guide](../../../libraries/situation-detector/docs/skills/situation-detector.md)
for contracts, bounds, failures, lifecycle and offline verification.
The host owns data access, caller authorization and processing. Configuration remains
data; this entry contains no runtime and grants no query or code-execution authority.