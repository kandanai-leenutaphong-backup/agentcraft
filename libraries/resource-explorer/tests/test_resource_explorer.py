"""The data-inventory component: allowlist, node codec, selection, service.

Every rejection row in the contract is tested here, without a server and
without a network. The recurring assertion is not that a bad request answers
400 — it is that the probe was never called: the allowlist has to refuse
before anything reaches an SDK, not after.
"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from resource_explorer.content import (
    ContentPayload,
    ContentResult,
    collected_now,
    content_failure,
)
from resource_explorer import (
    DEFAULT_PROVENANCE,
    MAX_PREVIEW_ROWS,
    ROOT_ID,
    InvalidNode,
    InvalidSelection,
    InventoryDefinitionError,
    InventoryRegistry,
    InventoryService,
    InventorySource,
    ProbeReport,
    SourceBinding,
    SourceDisabled,
    UseCase,
    build_inventory_router,
    decode_node,
    encode_node,
    is_root,
    parse_selection,
    source_node,
    token_digest,
    use_case_node,
)
from resource_explorer.backend.nodes import NodeRef


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def source(
    source_id: str,
    use_case_id: str,
    *,
    connector: str = "fake",
    coordinates: dict[str, str] | None = None,
    required: tuple[str, ...] = ("endpoint",),
) -> InventorySource:
    return InventorySource(
        source_id=source_id,
        use_case_id=use_case_id,
        name=f"Source {source_id}",
        source_type="adx_table",
        holds="rows",
        capabilities=("metadata", "preview"),
        binding=SourceBinding(
            connector=connector,
            coordinates=coordinates if coordinates is not None else {"endpoint": "https://c"},
            required=required,
            settings=("SOME_KEY",),
            reached_by="tests",
            connector_name="Fake",
        ),
        provenance="A replay.",
    )


def registry() -> InventoryRegistry:
    return InventoryRegistry(
        [
            UseCase(
                use_case_id="alpha",
                name="Alpha",
                summary="First",
                sources=(source("alpha.one", "alpha"), source("alpha.two", "alpha")),
            ),
            UseCase(
                use_case_id="beta",
                name="Beta",
                summary="Second",
                sources=(
                    source("beta.one", "beta"),
                    source(
                        "beta.blank",
                        "beta",
                        coordinates={"endpoint": ""},
                    ),
                ),
            ),
        ]
    )


class RecordingProbe:
    """A probe that says when it was called. Silence is the assertion."""

    def __init__(self) -> None:
        self.metadata_calls: list[str] = []
        self.preview_calls: list[tuple[str, int]] = []

    async def metadata(self, src: InventorySource) -> ProbeReport:
        self.metadata_calls.append(src.source_id)
        return ProbeReport(
            status="ok",
            metrics={"row_count": 42},
            schema_fields=({"name": "a", "type": "string"},),
            total_rows=42,
            collected_at=collected_now(),
        )

    async def preview(self, src: InventorySource, *, limit: int) -> ContentResult:
        self.preview_calls.append((src.source_id, limit))
        return ContentResult(
            service="fake",
            kind="rows",
            status="ok",
            payload=ContentPayload(
                form="rows",
                media_type="application/json",
                rows=tuple({"a": i} for i in range(min(limit, 3))),
                columns=("a",),
                size_bytes=3,
            ),
            truncated=False,
            collected_at=collected_now(),
        )


def service(probe: RecordingProbe | None = None) -> tuple[InventoryService, RecordingProbe]:
    recorder = probe or RecordingProbe()
    return InventoryService(registry(), {"fake": recorder}), recorder


def everything() -> Any:
    return parse_selection(None, allowed=registry().source_ids())


class NeutralDefaultsTests(unittest.TestCase):
    def test_unspecified_provenance_is_unknown_and_explicit_claims_are_preserved(self) -> None:
        for provenance in ("", "Host-declared historical fixture."):
            declared = replace(source("sample", "catalogue"), provenance=provenance)
            declared_registry = InventoryRegistry([UseCase("catalogue", "Catalogue", "", (declared,))])
            svc = InventoryService(declared_registry, {"fake": RecordingProbe()})
            selection = parse_selection(None, allowed=declared_registry.source_ids())

            async def read():
                token = source_node("catalogue", "sample")
                return await svc.resource(token, selection), await svc.content(token, selection)

            for response in run(read()):
                self.assertEqual(response.provenance, provenance or DEFAULT_PROVENANCE)
                if not provenance:
                    self.assertIn("unknown", response.provenance)
                    self.assertNotIn("replay", response.provenance.lower())

    def test_router_defaults_are_neutral_and_hosts_can_choose_a_prefix(self) -> None:
        for prefix in (None, "/host/catalogue"):
            svc, probe = service()
            app = FastAPI()
            options = {} if prefix is None else {"prefix": prefix}
            app.include_router(build_inventory_router(lambda request: svc, **options))
            with TestClient(app) as client:
                base = prefix or "/api/inventory"
                response = client.get(f"{base}/tree")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-store, private")
                self.assertEqual(client.get("/api/cyber/inventory/tree").status_code, 404)
                refused = client.get(f"{base}/tree", headers={"X-Inventory-Selection": "unknown"})
                self.assertEqual(refused.status_code, 400)
            self.assertEqual(probe.metadata_calls, [])
            self.assertEqual(probe.preview_calls, [])


class RegistryTests(unittest.TestCase):
    def test_a_source_filed_under_the_wrong_use_case_is_refused_at_build(self) -> None:
        with self.assertRaises(InventoryDefinitionError):
            InventoryRegistry(
                [UseCase("alpha", "Alpha", "", (source("x", "beta"),))]
            )

    def test_duplicate_source_ids_are_refused_at_build(self) -> None:
        with self.assertRaises(InventoryDefinitionError):
            InventoryRegistry(
                [
                    UseCase("alpha", "Alpha", "", (source("dup", "alpha"),)),
                    UseCase("beta", "Beta", "", (source("dup", "beta"),)),
                ]
            )

    def test_duplicate_use_case_ids_are_refused_at_build(self) -> None:
        with self.assertRaises(InventoryDefinitionError):
            InventoryRegistry(
                [
                    UseCase("alpha", "Alpha", "", (source("a", "alpha"),)),
                    UseCase("alpha", "Alpha again", "", (source("b", "alpha"),)),
                ]
            )

    def test_an_unknown_capability_is_refused_at_build(self) -> None:
        bad = InventorySource(
            source_id="x",
            use_case_id="alpha",
            name="X",
            source_type="adx_table",
            holds="",
            capabilities=("teleport",),
            binding=SourceBinding(connector="fake"),
        )
        with self.assertRaises(InventoryDefinitionError):
            InventoryRegistry([UseCase("alpha", "Alpha", "", (bad,))])

    def test_lookup_refuses_a_cross_use_case_pairing(self) -> None:
        """A real source with the wrong parent is not a source at all."""
        reg = registry()
        self.assertIsNotNone(reg.source("alpha", "alpha.one"))
        self.assertIsNone(reg.source("beta", "alpha.one"))

    def test_a_missing_coordinate_is_unconfigured_and_names_the_key(self) -> None:
        reg = registry()
        blank = reg.source("beta", "beta.blank")
        assert blank is not None
        self.assertFalse(blank.is_configured)
        self.assertIn("endpoint", blank.unconfigured_detail)
        self.assertIn("SOME_KEY", blank.unconfigured_detail)

    def test_a_credential_named_coordinate_is_refused_at_build(self) -> None:
        """Coordinates reach the browser. A name that invites a secret is refused."""
        for name in (
            "account_key",
            "sas",
            "sasToken",
            "api-key",
            "password",
            "connection_string",
            "authorization",
        ):
            with self.subTest(name):
                with self.assertRaises(InventoryDefinitionError) as caught:
                    InventoryRegistry(
                        [
                            UseCase(
                                "alpha",
                                "Alpha",
                                "",
                                (
                                    source(
                                        "alpha.one",
                                        "alpha",
                                        coordinates={
                                            "endpoint": "https://c",
                                            name: "s3cr3t-value",
                                        },
                                    ),
                                ),
                            )
                        ]
                    )
                self.assertIn(name, str(caught.exception))
                self.assertNotIn("s3cr3t-value", str(caught.exception))

    def test_an_ordinary_coordinate_name_is_not_mistaken_for_one(self) -> None:
        """The guard is on the name, not on a scan of the value."""
        reg = InventoryRegistry(
            [
                UseCase(
                    "alpha",
                    "Alpha",
                    "",
                    (
                        source(
                            "alpha.one",
                            "alpha",
                            coordinates={
                                "endpoint": "https://c",
                                "database": "d",
                                "table": "Keystrokes",
                                "index": "monkey-corpus",
                            },
                        ),
                    ),
                )
            ]
        )
        found = reg.source("alpha", "alpha.one")
        assert found is not None
        self.assertEqual(found.binding.coordinates["table"], "Keystrokes")


class NodeCodecTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        token = source_node("alpha", "alpha.one")
        ref = decode_node(token)
        self.assertEqual((ref.use_case_id, ref.source_id, ref.kind), ("alpha", "alpha.one", "source"))
        self.assertEqual(encode_node(ref), token)

    def test_root_is_the_only_literal_id(self) -> None:
        self.assertTrue(is_root(None))
        self.assertTrue(is_root(""))
        self.assertTrue(is_root(ROOT_ID))
        self.assertFalse(is_root(use_case_node("alpha")))

    def test_every_rejection_row(self) -> None:
        cases = {
            "over length": "a" * 5000,
            "alphabet": "not a token!",
            "encoding": "@@@@",
            "not json": encode_junk(b"not json"),
            "not an object": encode_junk(b"[1,2]"),
            "bad version": encode_payload({"v": 2, "s": "inventory", "l": "source", "p": ["a", "b"], "k": "source"}),
            "unknown service": encode_payload({"v": 1, "s": "estate", "l": "source", "p": ["a", "b"], "k": "source"}),
            "unknown level": encode_payload({"v": 1, "s": "inventory", "l": "cluster", "p": ["a"], "k": "use_case"}),
            "unknown kind": encode_payload({"v": 1, "s": "inventory", "l": "source", "p": ["a", "b"], "k": "blob"}),
            "kind mismatch": encode_payload({"v": 1, "s": "inventory", "l": "source", "p": ["a", "b"], "k": "use_case"}),
            "path too deep": encode_payload({"v": 1, "s": "inventory", "l": "source", "p": ["a", "b", "c"], "k": "source"}),
            "path arity": encode_payload({"v": 1, "s": "inventory", "l": "source", "p": ["a"], "k": "source"}),
            "empty segment": encode_payload({"v": 1, "s": "inventory", "l": "source", "p": ["a", ""], "k": "source"}),
            "segment too long": encode_payload({"v": 1, "s": "inventory", "l": "source", "p": ["a", "b" * 500], "k": "source"}),
            "path not a list": encode_payload({"v": 1, "s": "inventory", "l": "source", "p": "ab", "k": "source"}),
        }
        for name, token in cases.items():
            with self.subTest(name):
                with self.assertRaises(InvalidNode):
                    decode_node(token)

    def test_a_token_cannot_carry_an_endpoint(self) -> None:
        """The whole point of the coordinate design: there is nowhere to put one.

        A forged token may name a source that does not exist, and that is
        rejected. It cannot name a cluster, a database or a table, because the
        payload has only two identifier slots and both are looked up.
        """
        forged = encode_payload(
            {
                "v": 1,
                "s": "inventory",
                "l": "source",
                "p": ["alpha", "https://attacker.example.net"],
                "k": "source",
            }
        )
        ref = decode_node(forged)
        self.assertEqual(ref.source_id, "https://attacker.example.net")
        self.assertIsNone(registry().source(ref.use_case_id, ref.source_id))

    def test_digest_is_loggable_and_the_token_is_not_recoverable(self) -> None:
        digest = token_digest(source_node("alpha", "alpha.one"))
        self.assertEqual(len(digest), 12)
        self.assertNotIn("alpha", digest)


def encode_payload(payload: dict[str, Any]) -> str:
    import base64
    import json

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def encode_junk(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.allowed = registry().source_ids()

    def test_absent_header_is_all(self) -> None:
        chosen = parse_selection(None, allowed=self.allowed)
        self.assertEqual(chosen.mode, "all")
        self.assertEqual(len(chosen.ids), len(self.allowed))

    def test_empty_value_is_none_not_all(self) -> None:
        """The distinction the header exists to preserve."""
        for value in ("", "  ", "none", "NONE"):
            with self.subTest(value):
                chosen = parse_selection(value, allowed=self.allowed)
                self.assertEqual(chosen.mode, "none")
                self.assertEqual(chosen.ids, frozenset())

    def test_an_explicit_list_covering_everything_collapses_to_all(self) -> None:
        chosen = parse_selection(",".join(self.allowed), allowed=self.allowed)
        self.assertEqual(chosen.mode, "all")

    def test_an_unknown_id_is_refused_not_ignored(self) -> None:
        with self.assertRaises(InvalidSelection):
            parse_selection("alpha.one,does.not.exist", allowed=self.allowed)

    def test_a_forged_id_shaped_like_a_coordinate_is_refused(self) -> None:
        with self.assertRaises(InvalidSelection):
            parse_selection(
                "https://attacker.example.net/index", allowed=self.allowed
            )

    def test_too_many_ids_and_an_oversized_header_are_refused(self) -> None:
        with self.assertRaises(InvalidSelection):
            parse_selection(",".join(["alpha.one"] * 200), allowed=self.allowed)
        with self.assertRaises(InvalidSelection):
            parse_selection("a" * 5000, allowed=self.allowed)

    def test_an_empty_id_in_a_list_is_refused(self) -> None:
        with self.assertRaises(InvalidSelection):
            parse_selection("alpha.one,,beta.one", allowed=self.allowed)

    def test_a_repeated_id_is_refused_not_deduplicated(self) -> None:
        """A client repeating an id has lost track of its own selection.

        Silently collapsing it means the next bug of that shape is invisible,
        and the count the reader is shown stops matching what was sent.
        """
        for value in ("alpha.one,alpha.one", "alpha.one,beta.one,alpha.one"):
            with self.subTest(value):
                with self.assertRaises(InvalidSelection):
                    parse_selection(value, allowed=self.allowed)

    def test_two_requests_are_independent(self) -> None:
        """No shared store: one request's selection cannot reach another's."""
        first = parse_selection("alpha.one", allowed=self.allowed)
        second = parse_selection(None, allowed=self.allowed)
        self.assertTrue(first.enabled("alpha.one"))
        self.assertFalse(first.enabled("beta.one"))
        self.assertTrue(second.enabled("beta.one"))


class TreeTests(unittest.TestCase):
    def test_the_root_lists_use_cases_and_probes_nothing(self) -> None:
        svc, probe = service()
        response = run(svc.tree(None, everything()))
        self.assertEqual([child.label for child in response.children], ["Alpha", "Beta"])
        self.assertEqual([child.kind for child in response.children], ["use_case"] * 2)
        self.assertEqual(probe.metadata_calls, [])

    def test_a_use_case_lists_its_own_sources_only(self) -> None:
        svc, _ = service()
        response = run(svc.tree(use_case_node("beta"), everything()))
        self.assertEqual(
            [child.source_id for child in response.children], ["beta.one", "beta.blank"]
        )
        for child in response.children:
            self.assertEqual(child.use_case_id, "beta")

    def test_an_unconfigured_source_still_lists_and_says_why(self) -> None:
        """One dark source must not take its siblings' listing with it."""
        svc, _ = service()
        response = run(svc.tree(use_case_node("beta"), everything()))
        blank = response.children[1]
        self.assertEqual(blank.status, "unconfigured")
        self.assertFalse(blank.has_content)
        self.assertIn("endpoint", blank.error or "")
        self.assertEqual(response.children[0].status, "ok")

    def test_a_disabled_source_lists_but_is_not_readable(self) -> None:
        svc, _ = service()
        chosen = parse_selection("beta.one", allowed=registry().source_ids())
        response = run(svc.tree(use_case_node("alpha"), chosen))
        for child in response.children:
            self.assertFalse(child.enabled)
            self.assertFalse(child.has_content)

    def test_an_unknown_use_case_is_rejected(self) -> None:
        svc, probe = service()
        with self.assertRaises(InvalidNode):
            run(svc.tree(use_case_node("nope"), everything()))
        self.assertEqual(probe.metadata_calls, [])

    def test_the_selection_scope_is_stated_by_the_server(self) -> None:
        svc, _ = service()
        response = run(svc.tree(None, everything()))
        self.assertIn("Data sources", response.selection_scope)
        self.assertIn("does not change", response.selection_scope.lower())


class ResourceTests(unittest.TestCase):
    def test_metadata_is_read_and_timestamped(self) -> None:
        svc, probe = service()
        response = run(svc.resource(source_node("alpha", "alpha.one"), everything()))
        self.assertEqual(response.status, "ok")
        self.assertEqual(response.metrics["row_count"], 42)
        self.assertEqual(probe.metadata_calls, ["alpha.one"])
        self.assertTrue(response.observed_at.endswith("Z"))
        self.assertEqual(response.connector.id, "fake")
        self.assertEqual(response.coordinates["endpoint"], "https://c")

    def test_the_endpoint_survives_to_the_client(self) -> None:
        """A declared coordinate is not free text and is not URL-stripped."""
        svc, _ = service()
        response = run(svc.resource(source_node("alpha", "alpha.one"), everything()))
        self.assertNotIn("redacted", str(response.coordinates))

    def test_a_disabled_source_is_refused_before_the_probe(self) -> None:
        svc, probe = service()
        chosen = parse_selection("beta.one", allowed=registry().source_ids())
        with self.assertRaises(SourceDisabled):
            run(svc.resource(source_node("alpha", "alpha.one"), chosen))
        self.assertEqual(probe.metadata_calls, [])

    def test_a_cross_use_case_token_is_refused_before_the_probe(self) -> None:
        svc, probe = service()
        with self.assertRaises(InvalidNode):
            run(svc.resource(source_node("beta", "alpha.one"), everything()))
        self.assertEqual(probe.metadata_calls, [])

    def test_a_use_case_token_is_not_a_resource(self) -> None:
        svc, _ = service()
        with self.assertRaises(InvalidNode):
            run(svc.resource(use_case_node("alpha"), everything()))

    def test_a_connector_with_no_probe_is_unavailable_and_names_it(self) -> None:
        reg = InventoryRegistry(
            [UseCase("alpha", "Alpha", "", (source("alpha.one", "alpha", connector="ghost"),))]
        )
        svc = InventoryService(reg, {})
        chosen = parse_selection(None, allowed=reg.source_ids())
        response = run(svc.resource(source_node("alpha", "alpha.one"), chosen))
        self.assertEqual(response.status, "unavailable")
        self.assertIn("ghost", response.error or "")


class ContentTests(unittest.TestCase):
    def test_a_preview_is_bounded_and_clamped(self) -> None:
        svc, probe = service()
        run(svc.content(source_node("alpha", "alpha.one"), everything(), limit=10_000))
        self.assertEqual(probe.preview_calls[0][1], MAX_PREVIEW_ROWS)

    def test_truncation_is_derived_from_the_population_when_known(self) -> None:
        """`take n` cannot self-report; the count the probe read decides."""
        svc, _ = service()
        response = run(svc.content(source_node("alpha", "alpha.one"), everything(), limit=5))
        self.assertEqual(response.size_bytes, 3)
        self.assertEqual(response.sample_of, 42)
        self.assertTrue(response.truncated)

    def test_an_unconfigured_source_is_reported_without_a_probe(self) -> None:
        svc, probe = service()
        response = run(svc.content(source_node("beta", "beta.blank"), everything()))
        self.assertEqual(response.status, "unconfigured")
        self.assertEqual(response.content_kind, "none")
        self.assertEqual(probe.preview_calls, [])
        self.assertIn("endpoint", response.error or "")

    def test_a_disabled_source_is_refused_before_the_probe(self) -> None:
        svc, probe = service()
        chosen = parse_selection("none", allowed=registry().source_ids())
        with self.assertRaises(SourceDisabled):
            run(svc.content(source_node("alpha", "alpha.one"), chosen))
        self.assertEqual(probe.preview_calls, [])

    def test_a_reader_failure_is_a_status_not_an_exception(self) -> None:
        class Failing(RecordingProbe):
            async def preview(self, src: InventorySource, *, limit: int) -> ContentResult:
                self.preview_calls.append((src.source_id, limit))
                return content_failure(
                    service="fake", kind="rows", status="forbidden", detail="no role"
                )

        svc, _ = service(Failing())
        response = run(svc.content(source_node("alpha", "alpha.one"), everything()))
        self.assertEqual(response.status, "forbidden")
        self.assertIsNone(response.rows)
        self.assertIn("no role", response.error or "")

    def test_a_readers_sample_notes_reach_the_wire_verbatim(self) -> None:
        """A lossy sample says what it lost, in the words the reader is shown."""

        class Noting(RecordingProbe):
            async def preview(self, src: InventorySource, *, limit: int) -> ContentResult:
                self.preview_calls.append((src.source_id, limit))
                return ContentResult(
                    service="fake",
                    kind="rows",
                    status="ok",
                    payload=ContentPayload(
                        form="rows",
                        media_type="application/json",
                        rows=({"a": 1},),
                        columns=("a",),
                        size_bytes=8,
                        notes=("4 cell(s) were shortened",),
                    ),
                    truncated=True,
                    collected_at=collected_now(),
                )

        svc, _ = service(Noting())
        response = run(svc.content(source_node("alpha", "alpha.one"), everything()))
        self.assertEqual(response.sample_notes, ["4 cell(s) were shortened"])
        self.assertTrue(response.truncated)

    def test_a_sample_short_of_the_population_says_so_without_a_reader_note(self) -> None:
        svc, _ = service()
        response = run(svc.content(source_node("alpha", "alpha.one"), everything(), limit=5))
        self.assertTrue(response.truncated)
        self.assertEqual(len(response.sample_notes), 1)
        self.assertIn("42", response.sample_notes[0])


class SelectionReportTests(unittest.TestCase):
    def test_the_report_lists_every_source_with_its_state(self) -> None:
        svc, _ = service()
        chosen = parse_selection("alpha.one", allowed=registry().source_ids())
        report = svc.selection_report(chosen)
        self.assertEqual(report.mode, "explicit")
        self.assertEqual(report.enabled, ["alpha.one"])
        self.assertEqual(len(report.sources), 4)
        by_id = {item.source_id: item for item in report.sources}
        self.assertTrue(by_id["alpha.one"].enabled)
        self.assertFalse(by_id["beta.one"].enabled)
        self.assertFalse(by_id["beta.blank"].configured)


class NodeRefTests(unittest.TestCase):
    def test_leaf_and_content_flags(self) -> None:
        leaf = NodeRef(service="inventory", level="source", path=("a", "b"), kind="source")
        branch = NodeRef(service="inventory", level="use_case", path=("a",), kind="use_case")
        self.assertTrue(leaf.is_leaf)
        self.assertTrue(leaf.has_content)
        self.assertFalse(branch.is_leaf)
        self.assertFalse(branch.has_content)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
