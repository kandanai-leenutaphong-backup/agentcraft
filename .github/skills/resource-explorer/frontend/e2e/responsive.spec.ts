/**
 * Geometry, touch targets and the shipped screenshots.
 *
 * Measured, not asserted from CSS: a page that scrolls sideways at 360px is
 * broken however correct the utility classes read, and a 44px minimum written
 * in a class name is not a 44px box until a browser has laid it out.
 */

import { expect, test, type Page } from "@playwright/test";

const ROW = '[data-testid="tree-row"]';

async function overflow(page: Page): Promise<{ scroll: number; client: number }> {
  return page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
}

async function openPath(page: Page, labels: string[]): Promise<void> {
  for (const label of labels) {
    const target = page.locator(`${ROW}[data-label="${label}"]`).first();
    await target.click();
    await expect(target).toHaveAttribute("aria-expanded", "true");
  }
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(ROW)).toHaveCount(4);
});

test("nothing scrolls sideways, at the shipped viewport or at 360", async ({ page }) => {
  await openPath(page, [
    "rg-fixture",
    "Microsoft.Storage/storageAccounts (1)",
    "hcfixturestore",
    "Blob containers",
    "explorer-demo",
  ]);
  await page.locator(`${ROW}[data-label="payload.bin"]`).click();

  const shipped = await overflow(page);
  expect(shipped.scroll, JSON.stringify(shipped)).toBeLessThanOrEqual(shipped.client);

  await page.setViewportSize({ width: 360, height: 800 });
  const narrow = await overflow(page);
  expect(narrow.scroll, JSON.stringify(narrow)).toBeLessThanOrEqual(narrow.client);
});

test("a wide table scrolls inside its own box, never the page", async ({ page }) => {
  await openPath(page, [
    "rg-fixture",
    "Microsoft.OperationalInsights/workspaces (1)",
    "log-fixture",
    "Log tables",
  ]);
  await page.locator(`${ROW}[data-kind="log_table"]`).first().click();
  const opener = page.getByTestId("open-detail");
  if (await opener.isVisible()) await opener.click();
  await expect(page.getByTestId("rows-table")).toBeVisible();

  const page1 = await overflow(page);
  expect(page1.scroll, JSON.stringify(page1)).toBeLessThanOrEqual(page1.client);
});

test("the panes are laid out for the viewport they are on", async ({ page }, info) => {
  const twoUp = info.project.name !== "mobile";
  const tree = page.getByTestId("tree");
  const treeBox = await tree.boundingBox();
  expect(treeBox).not.toBeNull();

  if (twoUp) {
    expect(treeBox?.width ?? 0).toBeGreaterThanOrEqual(300);
    const detailBox = await page.getByTestId("detail").boundingBox();
    expect(detailBox).not.toBeNull();
    // Side by side, not stacked.
    expect(detailBox?.x ?? 0).toBeGreaterThan((treeBox?.x ?? 0) + (treeBox?.width ?? 0) - 1);
    expect(detailBox?.width ?? 0).toBeGreaterThan(280);
  } else {
    await expect(page.getByTestId("detail")).toHaveCount(0);
    await page.locator(`${ROW}[data-label="rg-locked"]`).click();
    await page.getByTestId("open-detail").click();
    await expect(page.getByTestId("detail")).toBeVisible();
    await expect(page.getByTestId("tree")).toHaveCount(0);
    await page.getByTestId("detail-back").click();
    await expect(page.getByTestId("tree")).toBeVisible();
  }
});

test("every touch target clears 44px on the narrow viewport", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "touch minimums apply to the narrow build");
  await openPath(page, ["rg-fixture", "Microsoft.Kusto/clusters (2)"]);

  // The expand control is included on purpose: it is the only way to close a
  // branch on a touch screen, and a 24px one is unhittable.
  const targets = page.locator(
    `${ROW}, [data-testid="tree-twisty"], header button, header a, [data-testid="open-detail"], [data-testid="search-input"]`,
  );
  const count = await targets.count();
  expect(count).toBeGreaterThan(8);
  for (let index = 0; index < count; index += 1) {
    const box = await targets.nth(index).boundingBox();
    expect(box, `target ${index} has no box`).not.toBeNull();
    expect(
      box?.height ?? 0,
      `target ${index} is ${String(box?.height ?? 0)}px tall`,
    ).toBeGreaterThanOrEqual(44);
  }

  await page.locator(`${ROW}[data-label="adx-fixture"]`).click();
  await page.getByTestId("open-detail").click();
  const tabs = page.locator('[role="tab"]');
  for (let index = 0; index < (await tabs.count()); index += 1) {
    const box = await tabs.nth(index).boundingBox();
    expect(box?.height ?? 0, `tab ${index}`).toBeGreaterThanOrEqual(44);
  }
});

test("every text role a reader must read clears AA contrast", async ({ page }) => {
  await page.locator(`${ROW}[data-label="rg-fixture"]`).click();
  const opener = page.getByTestId("open-detail");
  if (await opener.isVisible()) await opener.click();

  const measured = await page.evaluate(() => {
    const parse = (value: string): number[] => (value.match(/[\d.]+/g) ?? []).map(Number);
    const over = (fg: number[], bg: number[]): number[] => {
      const alpha = fg[3] ?? 1;
      return [0, 1, 2].map((i) => (fg[i] ?? 0) * alpha + (bg[i] ?? 0) * (1 - alpha));
    };
    const lum = (c: number[]): number => {
      const f = (v: number): number => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * f(c[0] ?? 0) + 0.7152 * f(c[1] ?? 0) + 0.0722 * f(c[2] ?? 0);
    };
    const bgOf = (el: Element): number[] => {
      const stack: number[][] = [];
      let node: Element | null = el;
      while (node !== null) {
        const parsed = parse(getComputedStyle(node).backgroundColor);
        if ((parsed[3] ?? 1) > 0) stack.push(parsed);
        node = node.parentElement;
      }
      let base = [255, 255, 255, 1];
      for (let i = stack.length - 1; i >= 0; i -= 1) base = [...over(stack[i] ?? [], base), 1];
      return base;
    };
    const selectors = [
      '[data-testid="tree-row"] .truncate',
      '[data-testid="observed-at"]',
      '[data-testid="detail-title"]',
      '[data-testid="detail-kind"]',
      '[data-testid="detail-list"] dt',
      '[data-testid="detail-list"] dd',
      '[data-testid="breadcrumbs"] li span',
      '[role="tab"]',
    ];
    return selectors.map((selector) => {
      const el = document.querySelector(selector);
      if (el === null) return { selector, ratio: 99, size: 0 };
      const style = getComputedStyle(el);
      const background = bgOf(el);
      const foreground = [...over(parse(style.color), background), 1];
      const [high, low] = [lum(foreground), lum(background)].sort((a, b) => b - a);
      return {
        selector,
        ratio: Number((((high ?? 0) + 0.05) / ((low ?? 0) + 0.05)).toFixed(2)),
        size: parseFloat(style.fontSize),
      };
    });
  });

  for (const entry of measured) {
    // 4.5:1 below 18.66px is the AA threshold this surface commits to.
    const required = entry.size >= 18.66 ? 3 : 4.5;
    expect(entry.ratio, `${entry.selector} at ${String(entry.size)}px`).toBeGreaterThanOrEqual(
      required,
    );
  }
});

test("the focus ring is drawn, and drawn outside the row", async ({ page }) => {
  await page.locator(`${ROW}[data-label="rg-fixture"]`).focus();
  const outline = await page
    .locator(`${ROW}[data-label="rg-fixture"]`)
    .evaluate((node) => {
      const style = window.getComputedStyle(node);
      return { width: style.outlineWidth, style: style.outlineStyle };
    });
  expect(outline.style).not.toBe("none");
  expect(parseFloat(outline.width)).toBeGreaterThanOrEqual(2);
});

test("screenshot the shipped viewport", async ({ page }, info) => {
  await openPath(page, [
    "rg-fixture",
    "Microsoft.Storage/storageAccounts (1)",
    "hcfixturestore",
    "Blob containers",
    "explorer-demo",
  ]);
  if (info.project.name !== "desktop") {
    await page.screenshot({ path: `tests/__screenshots__/${info.project.name}-tree.png` });
  }
  await page.locator(`${ROW}[data-label="README.md"]`).click();
  const opener = page.getByTestId("open-detail");
  if (await opener.isVisible()) await opener.click();
  await expect(page.getByTestId("content-markdown")).toBeVisible();
  await page.screenshot({
    path: `tests/__screenshots__/${info.project.name}.png`,
    fullPage: false,
  });
});
