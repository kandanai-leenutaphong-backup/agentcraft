import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { once } from "node:events";
import test from "node:test";

const entry = new URL("./verify-current-catalogue.mjs", import.meta.url);
const source = readFileSync(entry, "utf8");
assert.match(source, /export (?:async )?function createReadGuard/, "actual dispatched verifier is not yet import-safe or guarded");
const { createReadGuard, loadAcceptance } = await import(entry.href);

const emptyMetrics = () => ({ known_attempts: 0, unknown_attempt_operations: 0 });
const identity = () => ({ distribution: "azdata", version: "fixture", source_sha256: "a".repeat(64),
  editable: false, wheel_install: true, transport: "native", read_surfaces: {
    knowledge: { metrics: emptyMetrics() },
    catalogue: { adx: { metrics: emptyMetrics() }, search: { metrics: emptyMetrics() } },
  } });

function baseline() {
  return { schema_version: 1, candidate_sha256: "b".repeat(64),
    binding: { plan_sha256: "c".repeat(64), candidate_sha256: "b".repeat(64), target_sha256: "d".repeat(64) },
    identity: { distribution: "azdata", version: "fixture", source_sha256: "a".repeat(64), editable: false, wheel_install: true, transport: "native" },
    sources: { "perth.adx.events_unified": { node: "perth-node" }, "cyberkb.search.mitre_attack": { node: "search-node" } },
    expires_at: new Date(Date.now() + 60_000).toISOString(), principal_id: "local:workstation" };
}

function ledger(maximum = 73) {
  const reservations = [];
  return { reservations, remaining: maximum,
    snapshot() { return { remaining_slots: this.remaining, reserved_call_slots: 100 - this.remaining }; },
    reserve(owner, maximum, binding) {
      assert.equal(binding.candidate_sha256, "b".repeat(64));
      if (maximum > this.remaining) throw new Error("budget_exhausted");
      this.remaining -= maximum;
      const entry = { owner, maximum, attempts: undefined };
      reservations.push(entry);
      return String(reservations.length - 1);
    },
    settle(identifier, attempts) {
      const entry = reservations[Number(identifier)];
      entry.attempts = attempts;
      if (attempts !== null) this.remaining += entry.maximum - attempts;
    },
  };
}

async function host() {
  const delivered = [], current = identity();
  const server = createServer((request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    delivered.push(url.pathname);
    response.setHeader("content-type", "application/json");
    if (url.pathname === "/api/cyber/library-identity") return response.end(JSON.stringify(current));
    if (request.headers["x-inventory-selection"] === "none") {
      response.statusCode = 409;
      return response.end(JSON.stringify({ error: "source_disabled" }));
    }
    current.read_surfaces.catalogue.adx.metrics.known_attempts += url.pathname.endsWith("content") ? 3 : 2;
    response.end(JSON.stringify({ status: "ok" }));
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return { base: `http://127.0.0.1:${server.address().port}`, delivered, server,
    async close() { server.closeAllConnections(); server.close(); await once(server, "close"); } };
}

test("launcher dispatches the guarded current catalogue entry", () => {
  const launcher = readFileSync(new URL("../../../../../deploy/deploy.sh", import.meta.url), "utf8");
  assert.match(launcher, /inventory\) SCRIPT=verify-current-catalogue\.mjs/);
  assert.match(source, /import\.meta\.url/);
});

test("missing read-only mode, baseline, ledger or private output refuses before browser", () => {
  for (const env of [{}, { CYBEREYE_READ_ONLY_ACCEPTANCE: "1" },
    { CYBEREYE_READ_ONLY_ACCEPTANCE: "1", CYBEREYE_READ_BASELINE: "/missing", CYBEREYE_READ_LEDGER: "/missing", ARTIFACT_DIR: "/tmp/missing-output" }]) {
    assert.throws(() => loadAcceptance(env));
  }
});

test("all prohibited Node requests are refused before server delivery", async () => {
  const local = await host();
  try {
    const guard = createReadGuard({ base: local.base, baseline: baseline(), ledger: ledger() });
    for (const path of ["/api/health", "/api/cyber/graph/entities", "/api/cyber/situations/summary/stream",
      "/api/cyber/situations/diagnose", "/api/cyber/classification", "/api/chat", "/api/models", "/api/embeddings",
      "/api/cyber/inventory/content?node=graph-node"]) {
      await assert.rejects(guard.fetch(path), /read_guard/);
    }
    await assert.rejects(guard.fetch("/api/sessions", { method: "POST" }), /read_guard/);
    assert.deepEqual(local.delivered, []);
  } finally { await local.close(); }
});

test("admitted Node reads reserve worst case and reconcile all canonical counters", async () => {
  const local = await host();
  const budget = ledger();
  try {
    const guard = createReadGuard({ base: local.base, baseline: baseline(), ledger: budget });
    const response = await guard.fetch("/api/cyber/inventory/content?node=perth-node&limit=1");
    assert.equal(response.status, 200);
    assert.equal(budget.reservations[0].maximum, 3);
    assert.equal(budget.reservations[0].attempts, 3);
    assert.equal(budget.remaining, 70);
    const refused = await guard.fetch("/api/cyber/inventory/content?node=perth-node&limit=1", { headers: { "X-Inventory-Selection": "none" } });
    assert.equal(refused.status, 409);
    assert.equal(budget.reservations.length, 1);
  } finally { await local.close(); }
});

test("exhaustion and stale baselines refuse before read delivery", async () => {
  const local = await host();
  try {
    assert.throws(() => createReadGuard({ base: local.base, baseline: { ...baseline(), expires_at: "2000-01-01T00:00:00Z" }, ledger: ledger() }));
    const guard = createReadGuard({ base: local.base, baseline: baseline(), ledger: ledger(1) });
    await assert.rejects(guard.fetch("/api/cyber/inventory/resource?node=perth-node"), /budget_exhausted/);
    assert(!local.delivered.includes("/api/cyber/inventory/resource"));
  } finally { await local.close(); }
});

test("every browser context receives a pre-navigation request guard", async () => {
  const guard = createReadGuard({ base: "http://127.0.0.1:9999", baseline: baseline(), ledger: ledger() });
  for (let position = 0; position < 2; position += 1) {
    let handler, aborted = 0, delivered = 0;
    const context = { async route(pattern, callback) { assert.equal(pattern, "**/*"); handler = callback; },
      on() {}, async routeWebSocket() {} };
    await guard.install(context);
    const request = { url: () => "http://127.0.0.1:9999/api/health", method: () => "GET", headers: () => ({}) };
    await handler({ request: () => request, abort: async () => { aborted += 1; }, continue: async () => { delivered += 1; } });
    assert.equal(aborted, 1);
    assert.equal(delivered, 0);
  }
});