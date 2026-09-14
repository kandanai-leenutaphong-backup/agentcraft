"""Offline compatibility experiment; SdkRbacProbe is not a production provider."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit

from azure.core.credentials import AccessToken
from azure.core.exceptions import (
    HttpResponseError,
    ResourceExistsError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.core.pipeline.policies import SansIOHTTPPolicy
from azure.core.pipeline.transport import HttpRequest, HttpResponse, HttpTransport
from azure.mgmt.authorization import AuthorizationManagementClient

from azaccess import (
    AccessDeclaration,
    AccessManager,
    ArmRbacProvider,
    AssignmentState,
    AuthorityPolicy,
    AuthorizationRefused,
    OperationPending,
    OwnershipRecord,
    ProviderConflict,
    Response,
    Scope,
    TransportError,
    user_assigned_identity,
)


TENANT = "11111111-1111-1111-1111-111111111111"
SUBSCRIPTION = "22222222-2222-2222-2222-222222222222"
PRINCIPAL = "33333333-3333-3333-3333-333333333333"
NAME = "44444444-4444-4444-4444-444444444444"
FOREIGN_NAME = "55555555-5555-5555-5555-555555555555"
GROUP = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/comparison"
SCOPE = f"{GROUP}/providers/Microsoft.Storage/storageAccounts/fixture"
COLLECTION = f"{SCOPE}/providers/Microsoft.Authorization/roleAssignments"
ASSIGNMENT = f"{COLLECTION}/{NAME}"
FOREIGN_ASSIGNMENT = f"{COLLECTION}/{FOREIGN_NAME}"
ROLE = "Storage Blob Data Contributor"


class SyntheticCredential:
    def __init__(self) -> None:
        self.calls = 0

    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        if scopes != ("https://management.azure.com/.default",):
            raise AssertionError("Unexpected credential audience")
        self.calls += 1
        return AccessToken("offline-fixture-not-a-credential", 4_000_000_000)


class FixtureResponse(HttpResponse):
    def __init__(self, request: HttpRequest, status: int, payload: dict) -> None:
        super().__init__(request, None)
        self.status_code = status
        self.headers = {"content-type": "application/json"}
        self.reason = "offline fixture"
        self.payload = payload

    def body(self) -> bytes:
        return json.dumps(self.payload).encode()


class ArmFixture(HttpTransport):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.records: dict[str, dict] = {}
        self.create_status = 201
        self.delete_status = 204
        self.empty_create = False
        self.timeout_create = False
        self.fail_reads = False
        self.next_link = ""

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self) -> ArmFixture:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def send(self, request: HttpRequest, **kwargs: Any) -> FixtureResponse:
        body = json.loads(request.body) if request.body else None
        self.calls.append((request.method, request.url, body))
        path = urlsplit(request.url).path
        if request.method == "GET":
            if self.fail_reads:
                return FixtureResponse(request, 503, {"error": {"code": "Unavailable"}})
            payload: dict = {"value": list(self.records.values())}
            if self.next_link:
                payload["nextLink"] = self.next_link
            return FixtureResponse(request, 200, payload)
        if request.method == "PUT":
            properties = dict(body["properties"])
            properties["scope"] = SCOPE
            record = {"id": path, "name": NAME, "properties": properties}
            if self.create_status == 409:
                record.update(id=FOREIGN_ASSIGNMENT, name=FOREIGN_NAME)
                self.records[FOREIGN_ASSIGNMENT] = record
                return FixtureResponse(request, 409, {"error": {"code": "RoleAssignmentExists"}})
            if self.create_status in (200, 201, 202):
                self.records[path] = record
            if self.timeout_create:
                raise ServiceRequestError("Synthetic lost response")
            payload = {} if self.empty_create or self.create_status == 202 else record
            return FixtureResponse(request, self.create_status, payload)
        if request.method == "DELETE":
            if self.delete_status == 204:
                self.records.pop(path, None)
            return FixtureResponse(request, self.delete_status, {})
        raise AssertionError(f"Unexpected fixture method {request.method}")


class FixtureLegacyTransport:
    def __init__(self, fixture: ArmFixture) -> None:
        self.fixture = fixture

    def request(self, method: str, url: str, json_body: dict | None = None) -> Response:
        request = HttpRequest(method, url, data=json.dumps(json_body) if json_body else None)
        response = self.fixture.send(request)
        return Response(status=response.status_code, body=response.payload)


class FixedTargetGuard(SansIOHTTPPolicy):
    def on_request(self, request: Any) -> None:
        target = urlsplit(request.http_request.url)
        if (
            target.scheme != "https"
            or target.netloc != "management.azure.com"
            or target.fragment
            or not (target.path == COLLECTION or target.path.startswith(COLLECTION + "/"))
        ):
            raise TransportError("SDK request escaped the fixture's configured target")
        Scope.parse(target.path)


class SdkRbacProbe:
    plane = "azure-rbac"
    operations = {"comparison-only": "implemented"}

    def __init__(self, client: AuthorizationManagementClient) -> None:
        self.client = client

    def list_at_scope(self, scope: str) -> tuple[AssignmentState, ...]:
        parsed = Scope.parse(scope)
        states: list[AssignmentState] = []
        pages = self.client.role_assignments.list_for_scope(parsed.value, filter="atScope()").by_page()
        for _page_index in range(2):
            try:
                page = next(pages)
                for assignment in page:
                    states.append(AssignmentState(
                        assignment_id=assignment.id or "",
                        plane=self.plane,
                        principal_id=assignment.principal_id or "",
                        role_definition_id=assignment.role_definition_id or "",
                        scope=assignment.scope or "",
                        condition=assignment.condition or "",
                        condition_version=assignment.condition_version or "",
                        principal_type=assignment.principal_type or "",
                        raw_name=assignment.name or "",
                    ))
            except StopIteration:
                return tuple(states)
            except HttpResponseError as error:
                raise TransportError(f"SDK read failed with HTTP {error.status_code}") from None
            if not pages.continuation_token:
                return tuple(states)
        raise TransportError("SDK comparison page budget exhausted")

    def list_for(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        return tuple(state for state in self.list_at_scope(declaration.scope)
                     if Scope.parse(state.scope).is_exact(declaration.scope))

    def list_inherited(self, scope: str) -> tuple[AssignmentState, ...]:
        return tuple(state for state in self.list_at_scope(scope)
                     if not Scope.parse(state.scope).is_exact(scope))

    def matches(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        return tuple(state for state in self.list_for(declaration) if state.matches(declaration))

    def _record(self, declaration: AccessDeclaration, plan_id: str,
                assignment_id: str, source: str) -> OwnershipRecord:
        return OwnershipRecord(
            assignment_id=assignment_id, plane=self.plane, plan_id=plan_id,
            fingerprint=declaration.fingerprint(), principal_id=declaration.principal.object_id,
            scope=declaration.scope, role=declaration.role, source=source,
        )

    def create(self, declaration: AccessDeclaration, *, plan_id: str) -> OwnershipRecord:
        scope = Scope.parse(declaration.scope).value
        target_id = f"{scope}/providers/Microsoft.Authorization/roleAssignments/{NAME}"
        parameters = self.client.models("2022-04-01").RoleAssignmentCreateParameters(
            role_definition_id=declaration.role_definition.arm_definition_id(SUBSCRIPTION),
            principal_id=declaration.principal.object_id,
            principal_type=declaration.principal.principal_type,
            condition=declaration.condition or None,
            condition_version=declaration.condition_version or None,
        )
        try:
            status, assignment = self.client.role_assignments.create(
                scope, NAME, parameters,
                cls=lambda response, result, headers: (response.http_response.status_code, result),
            )
        except ResourceExistsError:
            matches = self.matches(declaration)
            if not matches:
                raise ProviderConflict("Conflict without a readable exact match") from None
            return self._record(declaration, plan_id, matches[0].assignment_id, "adopted")
        except (ServiceRequestError, ServiceResponseError):
            raise OperationPending("SDK write response unresolved", target_id=target_id) from None
        except HttpResponseError as error:
            if error.status_code == 202:
                raise OperationPending("SDK create accepted but unresolved", target_id=target_id,
                                       status=202) from None
            raise TransportError(f"SDK create failed with HTTP {error.status_code}") from None
        if status not in (200, 201) or assignment is None or assignment.id != target_id:
            raise OperationPending("SDK create lacks exact target evidence", target_id=target_id)
        return self._record(declaration, plan_id, assignment.id, "created")

    def delete(self, assignment_id: str) -> None:
        try:
            status = self.client.role_assignments.delete_by_id(
                assignment_id,
                cls=lambda response, result, headers: response.http_response.status_code,
            )
        except HttpResponseError as error:
            status = error.status_code
        if status == 202:
            raise OperationPending("SDK delete accepted but unresolved", target_id=assignment_id)
        if status not in (204, 404):
            raise TransportError(f"SDK delete failed with HTTP {status}")


class RbacSdkComparison(unittest.TestCase):
    def setUp(self) -> None:
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)
        self.fixture = ArmFixture()
        self.credential = SyntheticCredential()
        self.client = AuthorizationManagementClient(
            self.credential, SUBSCRIPTION, api_version="2022-04-01",
            transport=self.fixture, retry_total=0, redirect_max=0,
            per_call_policies=[FixedTargetGuard()],
            connection_timeout=1, read_timeout=1,
        )
        self.addCleanup(self.client.close)
        self.provider = SdkRbacProbe(self.client)
        self.policy = AuthorityPolicy(
            allowed_tenants=frozenset({TENANT}), allowed_scopes=(SCOPE,),
            allowed_planes=frozenset({"azure-rbac"}), max_tier="write", read_only=False,
        )
        self.manager = AccessManager({"azure-rbac": self.provider}, policy=self.policy)
        self.declaration = AccessDeclaration(
            principal=user_assigned_identity(principal_id=PRINCIPAL, tenant_id=TENANT),
            role=ROLE, scope=SCOPE,
        )

    def apply(self):
        plan = self.manager.plan([self.declaration])
        return self.manager.apply(plan, confirmations=self.manager.confirm(plan), verify_budget_secs=0)

    def test_lifecycle_matches_existing_provider(self) -> None:
        results = []
        legacy_fixture = ArmFixture()
        legacy_provider = ArmRbacProvider(FixtureLegacyTransport(legacy_fixture),
                                          subscription_id=SUBSCRIPTION, name_factory=lambda: NAME)
        for provider, fixture in ((self.provider, self.fixture), (legacy_provider, legacy_fixture)):
            manager = AccessManager({"azure-rbac": provider}, policy=self.policy)
            plan = manager.plan([self.declaration])
            report = manager.apply(plan, confirmations=manager.confirm(plan), verify_budget_secs=0)
            self.assertTrue(report.ok, report.to_dict())
            self.assertEqual(report.ownership[0].assignment_id, ASSIGNMENT)
            revoked = manager.revoke([self.declaration], budget_secs=0)
            self.assertTrue(revoked.ok, revoked.to_dict())
            self.assertFalse(fixture.records)
            results.append((report.ownership[0].source, report.verifications[0].status,
                            tuple(revoked.deleted), revoked.verifications[0].status))
        self.assertEqual(results[0], results[1])
        properties = next(body["properties"] for method, _url, body in self.fixture.calls if method == "PUT")
        self.assertEqual(properties["principalType"], "ServicePrincipal")
        self.assertEqual(properties["principalId"], PRINCIPAL)

    def test_disallowed_scope_stops_before_sdk_and_credential(self) -> None:
        with self.assertRaises(AuthorizationRefused):
            self.manager.inspect(PRINCIPAL, GROUP)
        self.assertEqual(self.credential.calls, 0)
        self.assertEqual(self.fixture.calls, [])

    def test_read_only_plan_cannot_mutate(self) -> None:
        manager = AccessManager({"azure-rbac": self.provider},
                                policy=self.policy.with_authorized(read_only=True))
        plan = manager.plan([self.declaration])
        report = manager.apply(plan, verify_budget_secs=0)
        self.assertFalse(report.ok)
        self.assertTrue(report.refusals)
        self.assertFalse(any(method == "PUT" for method, _url, _body in self.fixture.calls))

    def test_wrong_plan_and_reused_confirmation_stop_before_sdk(self) -> None:
        first = self.manager.plan([self.declaration])
        second = self.manager.plan([self.declaration])
        tokens = self.manager.confirm(first)
        before = len(self.fixture.calls)
        self.assertFalse(self.manager.apply(second, confirmations=tokens).ok)
        self.assertEqual(len(self.fixture.calls), before)
        self.assertTrue(self.manager.apply(first, confirmations=tokens, verify_budget_secs=0).ok)
        before = len(self.fixture.calls)
        self.assertFalse(self.manager.apply(first, confirmations=tokens).ok)
        self.assertEqual(len(self.fixture.calls), before)

    def test_inherited_grant_does_not_satisfy_exact_scope(self) -> None:
        self.assertTrue(self.apply().ok)
        inherited = deepcopy(self.fixture.records[ASSIGNMENT])
        inherited["id"] = f"{GROUP}/providers/Microsoft.Authorization/roleAssignments/{FOREIGN_NAME}"
        inherited["properties"]["scope"] = GROUP
        self.fixture.records = {inherited["id"]: inherited}
        self.assertEqual(self.provider.matches(self.declaration), ())
        inspected = self.manager.inspect(PRINCIPAL, SCOPE)
        self.assertEqual(len(inspected.inherited), 1)
        self.assertEqual(len(inspected.exact), 0)

    def test_conflict_is_adoption_not_cleanup_authority(self) -> None:
        self.fixture.create_status = 409
        report = self.apply()
        self.assertTrue(report.ok, report.to_dict())
        self.assertEqual(report.ownership[0].source, "adopted")
        revoked = self.manager.revoke([self.declaration], budget_secs=0)
        self.assertFalse(revoked.ok)
        self.assertIn(FOREIGN_ASSIGNMENT, self.fixture.records)
        self.assertFalse(any(method == "DELETE" for method, _url, _body in self.fixture.calls))

    def test_uncertain_create_retains_target_without_retry(self) -> None:
        for mode in ("accepted", "missing-body", "lost-response"):
            with self.subTest(mode=mode):
                self.fixture.calls.clear()
                self.fixture.records.clear()
                self.fixture.create_status = 202 if mode == "accepted" else 201
                self.fixture.empty_create = mode == "missing-body"
                self.fixture.timeout_create = mode == "lost-response"
                report = self.apply()
                self.assertFalse(report.ok)
                self.assertEqual(report.pending[0].assignment_id, ASSIGNMENT)
                self.assertEqual(report.ownership, ())
                self.assertEqual(sum(method == "PUT" for method, _url, _body in self.fixture.calls), 1)

    def test_pending_delete_retains_ownership(self) -> None:
        self.assertTrue(self.apply().ok)
        self.fixture.delete_status = 202
        revoked = self.manager.revoke([self.declaration], budget_secs=0)
        self.assertFalse(revoked.ok)
        self.assertEqual(revoked.retained[0]["reason"], "delete-pending")
        self.assertEqual(self.manager.ownership[0].assignment_id, ASSIGNMENT)

    def test_failed_read_is_unknown_not_absent(self) -> None:
        self.fixture.fail_reads = True
        result = self.manager.verify([self.declaration], budget_secs=0)[0]
        self.assertEqual(result.status, "unknown")
        self.assertEqual(len(self.fixture.calls), 1)

    def test_cross_origin_continuation_refuses_before_second_send(self) -> None:
        self.fixture.next_link = "https://example.invalid/steal"
        with self.assertRaises(TransportError):
            self.provider.list_at_scope(SCOPE)
        self.assertEqual(len(self.fixture.calls), 1)
        self.assertEqual(self.credential.calls, 1)

    def test_repeated_page_is_bounded(self) -> None:
        self.fixture.next_link = f"https://management.azure.com{COLLECTION}?page=again"
        with self.assertRaisesRegex(TransportError, "page budget"):
            self.provider.list_at_scope(SCOPE)
        self.assertEqual(len(self.fixture.calls), 2)


if __name__ == "__main__":
    unittest.main()
