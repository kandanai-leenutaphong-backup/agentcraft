import { chromium } from 'playwright';
const browser = await chromium.launch();
const ctx = await browser.newContext();
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push('PAGE_ERROR: ' + e.message));
page.on('console', (msg) => {
  if (msg.type() === 'error' || msg.type() === 'warning') {
    errors.push(msg.type().toUpperCase() + ': ' + msg.text());
  }
});
page.on('requestfailed', (req) => errors.push('REQ_FAIL: ' + req.url() + ' — ' + req.failure()?.errorText));
await page.goto('https://gridiq-v1.nicesmoke-72d7e88d.australiaeast.azurecontainerapps.io/', { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(2000);
console.log('--- console errors ---');
errors.forEach(e => console.log(e));
console.log('--- buttons in header ---');
const buttons = await page.locator('header button').allTextContents();
console.log(JSON.stringify(buttons));
console.log('--- click Play demo ---');
const btn = page.locator('button:has-text("Play demo")').first();
const visible = await btn.isVisible().catch(() => false);
console.log('Play demo visible:', visible);
if (visible) {
  await btn.click();
  await page.waitForTimeout(500);
  const items = await page.locator('button:has-text("Placeholder Demo")').allTextContents();
  console.log('Dropdown items:', JSON.stringify(items));
  if (items.length > 0) {
    await page.locator('button:has-text("Placeholder Demo")').first().click();
    await page.waitForTimeout(3000);
    const chatVisible = await page.locator('text=Something strange').first().isVisible().catch(() => false);
    console.log('User msg appeared after 3s:', chatVisible);
    console.log('--- console errors after click ---');
    errors.slice().forEach(e => console.log(e));
  }
}
await browser.close();
