/**
 * Acceptance for the Resource Explorer SPA, driven against the production
 * bundle served by the backend in fixture mode.
 *
 * The fixture estate is chosen so every branch state is reachable without a
 * network: ARM, blobs, Cosmos, Gremlin, Kusto, Search, Log Analytics and a
 * registry all answer; one Cosmos account is forbidden, one storage account is
 * unreachable, one cluster is unconfigured, one Search service is unavailable,
 * one group is empty, one index is truncated at the 500 clamp, and one index is
 * named `assets/v1: beta` — the case a delimiter-joined node id cannot survive.
 */

import { readFileSync } from "node:fs";
import { expect, test, type Locator, type Page } from "@playwright/test";

const ROW = '[data-testid="tree-row"]';

function row(page: Page, label: string): Locator {
  return page.locator(`${ROW}[data-label="${label}"]`).first();
}

/** Clicking a row selects it and opens it; it never closes it by surprise. */
async function open(page: Page, label: string): Promise<void> {
  const target = row(page, label);
  await target.click();
  await expect(target).toHaveAttribute("aria-expanded", "true");
}

async function collapse(page: Page, label: string): Promise<void> {
  await page.locator(`${ROW}[data-label="${label}"] [data-testid="tree-twisty"]`).first().click();
  await expect(row(page, label)).toHaveAttribute("aria-expanded", "false");
}

/** On a narrow viewport the pane is a second screen; on a wide one it is always there. */
async function pane(page: Page): Promise<Locator> {
  const opener = page.getByTestId("open-detail");
  if (await opener.isVisible()) await opener.click();
  const detail = page.getByTestId("detail");
  await expect(detail).toBeVisible();
  return detail;
}

async function backToTree(page: Page): Promise<void> {
  const back = page.getByTestId("detail-back");
  if (await back.isVisible()) await back.click();
  await expect(page.getByTestId("tree")).toBeVisible();
}

/** Walk to the demo blob container, which holds one blob of every typing. */
async function openDemoContainer(page: Page): Promise<void> {
  await open(page, "rg-fixture");
  await open(page, "Microsoft.Storage/storageAccounts (1)");
  await open(page, "hcfixturestore");
  await open(page, "Blob containers");
  await open(page, "explorer-demo");
}

/**
 * Selecting a leaf on a narrow viewport swaps the tree out for the pane, so
 * the property to assert is that the pane shows what was picked — true at
 * every viewport — rather than that the row is still on screen.
 */
async function select(page: Page, label: string): Promise<Locator> {
  await row(page, label).click();
  const detail = await pane(page);
  await expect(detail.getByTestId("detail-title")).toHaveText(label);
  return detail;
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(ROW)).toHaveCount(4);
});

test("the built frontend serves its full font license notice", async ({ request }) => {
  const response = await request.get("/assets/THIRD_PARTY_NOTICES.txt");
  expect(response.ok()).toBe(true);
  expect(await response.text()).toBe(
    readFileSync(new URL("../THIRD_PARTY_NOTICES.txt", import.meta.url), "utf8"),
  );
});

test("the root is the subscription and every resource group under it", async ({ page }) => {
  const labels = await page.locator(ROW).evaluateAll((nodes) =>
    nodes.map((node) => node.getAttribute("data-label")),
  );
  expect(labels).toEqual(["Azure subscription", "rg-empty", "rg-fixture", "rg-locked"]);
  await expect(row(page, "Azure subscription")).toHaveAttribute("data-kind", "root");
  await expect(row(page, "rg-locked")).toHaveAttribute("data-kind", "resource_group");
  // The pane opens on something rather than on an empty panel.
  await expect(page.getByTestId("live-region")).toContainText("3 items");
});

test("fixture data is stated on the surface, not left to be inferred", async ({ page }) => {
  await expect(page.getByTestId("fixture-banner")).toContainText("synthetic estate");
});

test("a branch is read only when it is opened, and kept when it is closed", async ({
  page,
}) => {
  const calls: string[] = [];
  await page.route("**/api/tree**", async (route) => {
    calls.push(route.request().url());
    await route.continue();
  });

  await open(page, "rg-fixture");
  await expect(page.locator(`${ROW}[data-kind="resource_type"]`)).toHaveCount(9);
  // Opening one group does not read the others.
  await expect(row(page, "rg-locked")).toHaveAttribute("aria-expanded", "false");
  const afterFirst = calls.length;

  await collapse(page, "rg-fixture");
  await expect(page.locator(`${ROW}[data-kind="resource_type"]`)).toHaveCount(0);
  await open(page, "rg-fixture");
  await expect(page.locator(`${ROW}[data-kind="resource_type"]`)).toHaveCount(9);
  expect(calls.length, "a re-opened branch is served from cache").toBe(afterFirst);
});

test("a name that breaks a delimiter-joined id still round-trips", async ({ page }) => {
  await open(page, "rg-fixture");
  await open(page, "Microsoft.Search/searchServices (2)");
  await open(page, "srch-fixture");
  await open(page, "Indexes");
  await open(page, "assets/v1: beta");
  await expect(page.locator(`${ROW}[data-kind="search_field"]`).first()).toBeVisible();
});

test.describe("contents", () => {
  test("plain text, JSON and markdown each render as what they are", async ({ page }) => {
    await openDemoContainer(page);

    const text = await select(page, "notes.txt");
    await expect(text.getByTestId("content-facts")).toHaveAttribute(
      "data-content-kind",
      "text",
    );
    await expect(text.getByTestId("content-text")).toContainText("Plain text, no header");
    await backToTree(page);

    const json = await select(page, "config.json");
    await expect(json.getByTestId("content-json")).toContainText('"region"');
    await backToTree(page);

    const markdown = await select(page, "README.md");
    await expect(markdown.getByTestId("content-markdown").locator("h1")).toContainText(
      "Explorer fixture container",
    );
    // The source is one click away, because a renderer can always be wrong.
    await markdown.locator('[data-testid="view-toggle"][data-option="Source"]').click();
    await expect(markdown.getByTestId("content-text")).toContainText("# Explorer fixture");
  });

  test("an image is drawn, at its own size, from the bytes returned", async ({ page }) => {
    await openDemoContainer(page);
    const detail = await select(page, "diagram.png");
    const image = detail.getByTestId("content-image");
    await expect(image).toBeVisible();
    const drawn = await image.evaluate((node) => {
      const img = node as HTMLImageElement;
      return { natural: img.naturalWidth, complete: img.complete, src: img.src.slice(0, 22) };
    });
    expect(drawn.complete).toBe(true);
    expect(drawn.natural).toBeGreaterThan(0);
    expect(drawn.src).toBe("data:image/png;base64,");
  });

  test("delimited text is a real table, and sorts", async ({ page }) => {
    await openDemoContainer(page);
    const detail = await select(page, "metrics.csv");
    const table = detail.getByTestId("rows-table");
    await expect(table).toBeVisible();
    await expect(table.locator("th")).toHaveCount(3);

    const before = await detail.locator('[data-testid="rows-row"] td').first().innerText();
    await detail.locator('[data-testid="rows-sort"][data-column="requests"]').click();
    await expect(
      detail.locator("th", { has: page.locator('[data-column="requests"]') }),
    ).toHaveAttribute("aria-sort", "ascending");
    const after = await detail.locator('[data-testid="rows-row"] td').first().innerText();
    expect(after).not.toBe(before);
  });

  test("bytes that are not text are a hex dump, not mojibake", async ({ page }) => {
    await openDemoContainer(page);
    const detail = await select(page, "payload.bin");
    await expect(detail.getByTestId("content-binary")).toContainText("00000000");
    await expect(detail.getByTestId("content-facts")).toContainText("1.0 KiB");
  });

  test("a blob two folders deep opens, with the whole path shown", async ({ page }) => {
    await openDemoContainer(page);
    await open(page, "nested");
    await open(page, "deep");
    const detail = await select(page, "file.txt");
    await expect(detail.getByTestId("content-text")).toBeVisible();
    const crumbs = await detail
      .getByTestId("breadcrumb-item")
      .evaluateAll((nodes) => nodes.map((node) => node.textContent));
    expect(crumbs).toEqual([
      "Azure subscription",
      "rg-fixture",
      "Microsoft.Storage/storageAccounts (1)",
      "hcfixturestore",
      "Blob containers",
      "explorer-demo",
      "nested",
      "deep",
      "file.txt",
    ]);
  });

  test("a sampled table is a table, and a row opens to its whole document", async ({
    page,
  }) => {
    await open(page, "rg-fixture");
    await open(page, "Microsoft.Kusto/clusters (2)");
    await open(page, "adx-fixture");
    await open(page, "Databases");
    await open(page, "telemetry");
    const detail = await select(page, "Events");
    await expect(detail.getByTestId("content-facts")).toHaveAttribute(
      "data-content-kind",
      "rows",
    );
    await detail.locator('[data-testid="rows-row"]').first().click();
    await expect(detail.getByTestId("rows-row-json")).toContainText("{");
  });

  test("a Cosmos document is rows too, and an empty container says so", async ({ page }) => {
    await open(page, "rg-fixture");
    await open(page, "Microsoft.DocumentDB/databaseAccounts (2)");
    await open(page, "cosmos-fixture");
    await open(page, "SQL databases");
    await open(page, "hcdb");

    const items = await select(page, "items");
    await expect(items.getByTestId("rows-table")).toBeVisible();
    await backToTree(page);

    const empty = await select(page, "empty-container");
    await expect(empty.getByTestId("rows-empty")).toContainText("no rows");
  });

  test("a node with no contents says so instead of showing an empty pane", async ({
    page,
  }) => {
    await open(page, "rg-fixture");
    const detail = await select(page, "Microsoft.KeyVault/vaults (1)");
    await expect(detail.getByTestId("tab-contents")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await expect(detail.getByTestId("tab-details")).toHaveAttribute("aria-selected", "true");
  });
});

test.describe("branches that do not answer", () => {
  test("a forbidden branch names the missing role", async ({ page }) => {
    await open(page, "rg-fixture");
    await open(page, "Microsoft.DocumentDB/databaseAccounts (2)");
    await open(page, "cosmos-forbidden");
    await open(page, "SQL databases");

    const note = page.getByTestId("branch-note").first();
    await expect(note).toHaveAttribute("data-status", "forbidden");
    await expect(note).toContainText("Forbidden");
    await expect(note).toContainText("Cosmos DB Account Reader");
    await expect(note).toContainText("role grant");
    // Never drawn as an empty branch.
    await expect(page.getByTestId("branch-empty")).toHaveCount(0);
  });

  test("an unreachable branch says a role grant will not help", async ({ page }) => {
    await open(page, "rg-locked");
    await open(page, "Microsoft.Storage/storageAccounts (1)");
    await open(page, "stlockedfixture");
    await open(page, "Blob containers");

    const note = page.getByTestId("branch-note").first();
    await expect(note).toHaveAttribute("data-status", "unreachable");
    await expect(note).toContainText("public network access is disabled");
    await expect(note).toContainText("A role grant does nothing here.");
    await expect(page.getByTestId("branch-empty")).toHaveCount(0);
  });

  test("the two diagnoses are told apart by words, not only by colour", async ({ page }) => {
    await open(page, "rg-locked");
    await open(page, "Microsoft.Storage/storageAccounts (1)");
    await open(page, "stlockedfixture");
    await open(page, "Blob containers");
    const unreachable = await page
      .locator('[data-testid="branch-note"][data-status="unreachable"]')
      .first()
      .innerText();

    // Closed, so the storage-account labels below resolve to one row each.
    await collapse(page, "rg-locked");

    await open(page, "rg-fixture");
    await open(page, "Microsoft.DocumentDB/databaseAccounts (2)");
    await open(page, "cosmos-forbidden");
    await open(page, "SQL databases");
    const forbidden = await page
      .locator('[data-testid="branch-note"][data-status="forbidden"]')
      .first()
      .innerText();

    expect(unreachable).toContain("Unreachable");
    expect(forbidden).toContain("Forbidden");
    expect(unreachable).not.toBe(forbidden);
  });

  test("an unconfigured branch names what nobody set", async ({ page }) => {
    await open(page, "rg-fixture");
    await open(page, "Microsoft.Kusto/clusters (2)");
    await open(page, "adx-unconfigured");
    await open(page, "Databases");
    const note = page.getByTestId("branch-note").first();
    await expect(note).toHaveAttribute("data-status", "unconfigured");
    await expect(note).toContainText("query URI");
  });

  test("an unavailable branch reports what the provider said", async ({ page }) => {
    await open(page, "rg-locked");
    await open(page, "Microsoft.Storage/storageAccounts (1)");
    await open(page, "stlockedfixture");
    await open(page, "Tables");
    const note = page.locator('[data-testid="branch-note"][data-status="unavailable"]').first();
    await expect(note).toContainText("provider declares no collection");
  });

  test("an empty group says the call succeeded", async ({ page }) => {
    await open(page, "rg-empty");
    await expect(page.getByTestId("branch-empty")).toContainText("call succeeded");
    await expect(page.getByTestId("branch-note")).toHaveCount(0);
  });

  test("a truncated listing says more exist", async ({ page }) => {
    await open(page, "rg-fixture");
    await open(page, "Microsoft.Search/searchServices (2)");
    await open(page, "srch-fixture");
    await open(page, "Indexes");
    await open(page, "hc-large");

    await expect(page.getByTestId("row-truncated")).toContainText("500 items shown — more exist");
    await expect(page.locator(`${ROW}[data-kind="search_field"]`)).toHaveCount(500);

    const detail = await pane(page);
    await detail.getByTestId("tab-details").click();
    await expect(detail.getByTestId("detail-list")).toContainText("more exist");
  });
});

test.describe("search", () => {
  test("a hit says where it matched and opens in the tree", async ({ page }) => {
    await page.getByTestId("search-input").fill("stlockedfixture");
    await page.getByTestId("search-submit").click();

    const hit = page.locator('[data-testid="search-hit"][data-label="stlockedfixture"]');
    await expect(hit).toBeVisible();
    await expect(hit).toContainText("matched on name");
    await expect(hit).toContainText("Microsoft.Storage/storageAccounts");

    await hit.click();
    // The tree walked down to it: group, then type, then the resource itself.
    await expect(row(page, "stlockedfixture")).toHaveAttribute("aria-selected", "true");
    await expect(row(page, "rg-locked")).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByTestId("search-panel")).toHaveCount(0);
    // The result set is kept, so re-opening it costs no second query.
    await expect(page.getByTestId("search-reopen")).toBeVisible();
  });

  test("a resource group hit opens the group", async ({ page }) => {
    await page.getByTestId("search-input").fill("rg-empty");
    await page.getByTestId("search-submit").click();
    await page.locator('[data-testid="search-hit"][data-kind="resource_group"]').first().click();
    await expect(row(page, "rg-empty")).toHaveAttribute("aria-selected", "true");
  });

  test("a term with no match says so, and says what search covers", async ({ page }) => {
    await page.getByTestId("search-input").fill("zzzznotathing");
    await page.getByTestId("search-submit").click();
    await expect(page.getByTestId("search-empty")).toContainText("property bag");
  });

  test("an empty term is refused here rather than sent", async ({ page }) => {
    let sent = 0;
    await page.route("**/api/search**", async (route) => {
      sent += 1;
      await route.continue();
    });
    await page.getByTestId("search-submit").click();
    await expect(page.getByTestId("search-failure")).toContainText("1 to 200");
    expect(sent).toBe(0);
  });
});

test.describe("keyboard and accessibility", () => {
  test("the whole tree is reachable from the keyboard", async ({ page }) => {
    const active = async (): Promise<string | null> =>
      page.evaluate(() => document.activeElement?.getAttribute("data-label") ?? null);

    await row(page, "Azure subscription").focus();
    expect(await active()).toBe("Azure subscription");

    await page.keyboard.press("ArrowDown");
    expect(await active()).toBe("rg-empty");
    await page.keyboard.press("ArrowDown");
    expect(await active()).toBe("rg-fixture");

    // Right opens, then steps in once the branch has arrived.
    await page.keyboard.press("ArrowRight");
    await expect(row(page, "rg-fixture")).toHaveAttribute("aria-expanded", "true");
    await expect(row(page, "Microsoft.App/containerApps (1)")).toBeVisible();
    await page.keyboard.press("ArrowRight");
    expect(await active()).toBe("Microsoft.App/containerApps (1)");

    // Left steps back out, then closes.
    await page.keyboard.press("ArrowLeft");
    expect(await active()).toBe("rg-fixture");
    await page.keyboard.press("ArrowLeft");
    await expect(row(page, "rg-fixture")).toHaveAttribute("aria-expanded", "false");

    await page.keyboard.press("End");
    expect(await active()).toBe("rg-locked");
    await page.keyboard.press("Home");
    expect(await active()).toBe("Azure subscription");

    // Enter selects and opens.
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await expect(row(page, "rg-fixture")).toHaveAttribute("aria-selected", "true");
  });

  test("slash reaches the search box, and the box is not a trap", async ({ page }) => {
    await row(page, "Azure subscription").focus();
    await page.keyboard.press("/");
    await expect(page.getByTestId("search-input")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("search-input")).not.toBeFocused();
  });

  test("exactly one row is in the tab order at a time", async ({ page }) => {
    await open(page, "rg-fixture");
    const tabbable = await page.locator(`${ROW}[tabindex="0"]`).count();
    expect(tabbable).toBe(1);
  });

  test("the tree carries its own position information", async ({ page }) => {
    await open(page, "rg-fixture");
    const group = row(page, "rg-fixture");
    await expect(group).toHaveAttribute("aria-level", "2");
    await expect(group).toHaveAttribute("aria-posinset", "2");
    await expect(group).toHaveAttribute("aria-setsize", "3");
    const child = row(page, "Microsoft.App/containerApps (1)");
    await expect(child).toHaveAttribute("aria-level", "3");
  });

  test("help explains the surface without documentation, and closes on Escape", async ({
    page,
  }) => {
    await page.getByTestId("help-open").click();
    const dialog = page.getByTestId("help-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId("kind-legend").locator("li")).toHaveCount(21);
    await expect(dialog).toContainText("only reads");
    await expect(dialog).toContainText("A role grant does nothing here.");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });
});
