"""Query outputs feed exact keyed citations, with independent step baselines."""

from __future__ import annotations


def validate(case, *, target, limits, feature):
    feature.validate_case(case, limits)
    reads, missing = case.get("reads"), case.get("missing")
    if case.get("workflow") != "search-citation" or case["operation"] != "query":
        raise ValueError("invalid_citation_workflow")
    if not isinstance(reads, list) or not isinstance(missing, dict):
        raise ValueError("independent_expected_required")
    for read in [*reads, missing]:
        feature.validate_case(read, limits)
        if read["operation"] != "read" or read.get("expected_status") != "success":
            raise ValueError("citation_read_required")
    documents = case["expected"]["documents"]
    if not documents or len(reads) != len(documents) or missing["expected"]["documents"]:
        raise ValueError("citation_baseline_mismatch")
    for document, read in zip(documents, reads):
        if document.get(target["key_field"]) != read["expression"]:
            raise ValueError("citation_baseline_mismatch")
    identifiers = [step["case_id"] for step in [case, *reads, missing]]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("duplicate_workflow_case")


async def run(case, *, target, limits, credential, before_call, transport=None, feature=None, observed_out=None):
    if feature is None:
        from tests.live_tests.features import search_read as feature

    validate(case, target=target, limits=limits, feature=feature)
    cases = [case, *case["reads"], case["missing"]]
    steps = [{"case_id": item["case_id"], "outcome": "NOT_RUN", "attempts": 0,
              "evidence_class": "offline"} for item in cases]
    observations = []
    failure = None
    for position, original in enumerate(cases):
        current = dict(original)
        if 0 < position <= len(case["reads"]):
            current["expression"] = observations[0]["documents"][position - 1][target["key_field"]]
        observed = {}
        try:
            result = await feature.run(current, target=target, limits=limits, credential=credential,
                                       before_call=before_call, transport=transport, observed_out=observed)
        except Exception:
            result = {"outcome": "FAIL", "attempts": None, "evidence_class": "unknown",
                      "attempts_unknown_reason": "interrupted_or_unreported", "error_code": "case_failed"}
        steps[position] = {"case_id": current["case_id"], **result}
        observations.append(observed)
        if result["outcome"] not in {"PASS_LIVE", "PASS_OFFLINE"}:
            failure = result.get("error_code", "case_failed")
            break
        if 0 < position <= len(case["reads"]):
            queried = observations[0]["documents"][position - 1]
            documents = observed["documents"]
            fields = [name for name in queried if not name.startswith("@search.")]
            if (len(documents) != 1 or any(name not in documents[0] for name in fields)
                    or feature.digest({name: documents[0][name] for name in fields})
                    != feature.digest({name: queried[name] for name in fields})):
                steps[position].update(outcome="FAIL", error_code="oracle_mismatch")
                failure = "oracle_mismatch"
                break
    if observed_out is not None:
        observed_out["steps"] = observations
    unknown = any(step["attempts"] is None for step in steps)
    live = transport is None and all(step["outcome"] == "PASS_LIVE" for step in steps)
    report = {"outcome": "FAIL" if failure else "PASS_LIVE" if live else "PASS_OFFLINE",
              "attempts": None if unknown else sum(step["attempts"] for step in steps),
              "evidence_class": "unknown" if unknown else "live" if transport is None else "offline",
              "result_status": "failed" if failure else "success", "steps": steps,
              "observed_sha256": feature.digest(observations)}
    if failure:
        report["error_code"] = failure
    if unknown:
        report["attempts_unknown_reason"] = "interrupted_or_unreported"
    return report