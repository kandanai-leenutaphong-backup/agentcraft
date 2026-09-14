#!/usr/bin/env python3
"""Capture a page as an image, with provenance.

Text tells you what a page says; a screenshot tells you what it looks like — layout, density,
hierarchy, where a first-time reader's eye lands. `webscrape.py` covers the first, this the
second, recording the same provenance: material acquired without it is an orphan the next reader
cannot verify.

Usage:
    python3 .github/tools/webshot.py https://example.com --out shots/
    python3 .github/tools/webshot.py <url> --viewport 1440x900 --viewport 390x844 --full-page
    python3 .github/tools/webshot.py <url> --out shots/ --catalogue shots/manifest.json
    python3 .github/tools/webshot.py --targets collections/x/targets.json --out shots/

Needs Playwright, in either form. Python is preferred:

    pip install playwright && python3 -m playwright install chromium

Node also works where a `playwright` package is installed:

    export PLAYWRIGHT_NODE_PATH=/path/to/node_modules/playwright

Safety is shared with webscrape.py: non-HTTP schemes and private addresses are refused, robots.txt
respected unless deliberately overridden.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_VIEWPORT = "1440x900"
DEFAULT_TIMEOUT = 30.0


class ShotError(Exception):
    pass


def _scraper() -> Any:
    """Reuse the scraper's URL guard, robots check and catalogue, rather than a second copy."""
    module_path = HERE / "webscrape.py"
    if not module_path.is_file():
        raise ShotError("webscrape.py must sit beside this tool; it owns the guards and catalogue")
    spec = importlib.util.spec_from_file_location("_harness_webscrape", module_path)
    if spec is None or spec.loader is None:
        raise ShotError("webscrape.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_viewport(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except ValueError:
        raise ShotError(f"viewport must look like 1440x900, got {value!r}") from None


def _capture_python(jobs: list[dict[str, Any]], timeout: float, full_page: bool) -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415 — optional dependency

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for job in jobs:
                context = browser.new_context(viewport={"width": job["width"], "height": job["height"]})
                page = context.new_page()
                page.goto(job["url"], wait_until="networkidle", timeout=timeout * 1000)
                if job.get("wait_for"):
                    page.wait_for_selector(job["wait_for"], timeout=timeout * 1000)
                page.screenshot(path=job["path"], full_page=full_page)
                job["title"] = page.title()
                context.close()
        finally:
            browser.close()


NODE_DRIVER = """
const path = process.argv[2];
const { chromium } = require(process.env.PLAYWRIGHT_NODE_PATH || 'playwright');
const spec = JSON.parse(require('fs').readFileSync(path, 'utf8'));
(async () => {
  const browser = await chromium.launch();
  try {
    for (const job of spec.jobs) {
      const context = await browser.newContext({
        viewport: { width: job.width, height: job.height },
      });
      const page = await context.newPage();
      await page.goto(job.url, { waitUntil: 'networkidle', timeout: spec.timeout });
      if (job.wait_for) await page.waitForSelector(job.wait_for, { timeout: spec.timeout });
      await page.screenshot({ path: job.path, fullPage: spec.full_page });
      job.title = await page.title();
      await context.close();
    }
  } finally {
    await browser.close();
  }
  require('fs').writeFileSync(path, JSON.stringify(spec));
})().catch((error) => { console.error(error.message); process.exit(1); });
"""


def _capture_node(jobs: list[dict[str, Any]], timeout: float, full_page: bool) -> None:
    if not shutil.which("node"):
        raise ShotError("neither the Python nor the Node Playwright driver is available")
    with tempfile.TemporaryDirectory() as tmp:
        spec_path = Path(tmp) / "spec.json"
        driver_path = Path(tmp) / "driver.js"
        spec_path.write_text(json.dumps({"jobs": jobs, "timeout": timeout * 1000,
                                         "full_page": full_page}), encoding="utf-8")
        driver_path.write_text(NODE_DRIVER, encoding="utf-8")
        result = subprocess.run(["node", str(driver_path), str(spec_path)],
                                capture_output=True, text=True, timeout=timeout * len(jobs) + 60)
        if result.returncode != 0:
            raise ShotError(f"Playwright (node) failed: {(result.stderr or result.stdout).strip()[:300]}")
        for job, done in zip(jobs, json.loads(spec_path.read_text(encoding="utf-8"))["jobs"]):
            job["title"] = done.get("title", "")


def capture(jobs: list[dict[str, Any]], timeout: float, full_page: bool) -> str:
    if importlib.util.find_spec("playwright") is not None:
        _capture_python(jobs, timeout, full_page)
        return "playwright-python"
    if os.environ.get("PLAYWRIGHT_NODE_PATH") or shutil.which("node"):
        _capture_node(jobs, timeout, full_page)
        return "playwright-node"
    raise ShotError(
        "Playwright is not available. Install it with:\n"
        "  pip install playwright && python3 -m playwright install chromium\n"
        "or point PLAYWRIGHT_NODE_PATH at an existing node playwright package"
    )


def run(args: argparse.Namespace) -> int:
    scraper = _scraper()
    targets: list[dict[str, Any]]
    if args.targets:
        targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))
    else:
        targets = [{"url": args.url, "name": None}]

    out_dir = Path(args.out or ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    viewports = [parse_viewport(v) for v in (args.viewport or [DEFAULT_VIEWPORT])]

    jobs: list[dict[str, Any]] = []
    for target in targets:
        url = target.get("url")
        if not url:
            continue
        scraper.guard_url(url, args.allow_private)
        if not args.ignore_robots:
            allowed, _ = scraper.robots_allows(url, args.timeout)
            if not allowed:
                raise ShotError(f"robots.txt disallows {url}; pass --ignore-robots deliberately")
        stem = target.get("name") or scraper.slugify(url)
        for width, height in viewports:
            suffix = f"-{width}x{height}" if len(viewports) > 1 else ""
            jobs.append({
                "url": url, "width": width, "height": height,
                "path": str(out_dir / f"{stem}{suffix}.png"),
                "wait_for": args.wait_for, "name": f"{stem}{suffix}",
                "subject": target.get("subject"), "notes": target.get("notes"),
            })

    if not jobs:
        raise ShotError("nothing to capture")
    driver = capture(jobs, args.timeout, args.full_page)

    captured = []
    for job in jobs:
        path = Path(job["path"])
        entry = {
            "name": job["name"], "url": job["url"],
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": f"webshot ({driver})", "title": job.get("title", ""),
            "viewport": f"{job['width']}x{job['height']}",
            "full_page": args.full_page,
        }
        if path.is_file():
            entry["bytes"] = path.stat().st_size
            entry["sha256"] = scraper.sha256_file(path)
        for key in ("subject", "notes"):
            if job.get(key):
                entry[key] = job[key]
        if args.catalogue:
            catalogue = Path(args.catalogue)
            entry["path"] = scraper.relative_to_catalogue(path, catalogue)
            scraper.catalogue_record(catalogue, entry)
        captured.append(entry)

    print(json.dumps({"driver": driver, "captured": len(captured), "shots": captured}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture a page as an image, with provenance.")
    parser.add_argument("url", nargs="?")
    parser.add_argument("--out", metavar="DIR", help="where the images are written")
    parser.add_argument("--viewport", action="append", metavar="WxH",
                        help=f"repeatable; default {DEFAULT_VIEWPORT}")
    parser.add_argument("--full-page", action="store_true", help="capture beyond the fold")
    parser.add_argument("--wait-for", metavar="SELECTOR",
                        help="wait for this selector before capturing")
    parser.add_argument("--targets", metavar="FILE", help="a collection to capture in turn")
    parser.add_argument("--catalogue", metavar="FILE", help="record provenance for each image")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--allow-private", action="store_true",
                        help="permit loopback and private addresses, for a local dev server")
    parser.add_argument("--ignore-robots", action="store_true")
    args = parser.parse_args(argv)

    if not args.url and not args.targets:
        parser.error("a URL is required unless --targets is used")
    try:
        return run(args)
    except ShotError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
