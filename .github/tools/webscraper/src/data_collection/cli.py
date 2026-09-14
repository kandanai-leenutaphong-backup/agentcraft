from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .models import BrowserAction, ScrapeOptions
from .scraper import Scraper
from .storage import save_result, verify_result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Acquire public HTML using HTTP first, then guarded Chromium when rendering is needed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    command.add_argument("urls", nargs="*", help="public HTTP(S) URLs")
    command.add_argument("--input", type=Path, help="UTF-8 URL list (one per line) or JSON array of URLs")
    command.add_argument("--out", type=Path, default=Path("output"), help="acquisition output directory")
    command.add_argument("--verify", type=Path, metavar="RUN_DIRECTORY", help="verify a saved run without network access")
    command.add_argument("--raw", action="store_true", help="print one URL's HTML to stdout; receipt goes to stderr")
    command.add_argument("--mode", choices=("auto", "http", "browser"), default="auto")
    command.add_argument("--wait-for", dest="wait_selector", help="CSS readiness selector; use browser mode to require browser-side waiting")
    command.add_argument("--actions", type=Path, help="JSON array of ordered click/wait/scroll actions")
    command.add_argument("--click", action="append", default=[], metavar="CSS", help="click a selector after file-based actions; repeatable")
    command.add_argument("--screenshot", action="store_true", help="also capture the 1440x1000 browser viewport")
    command.add_argument("--headed", action="store_true", help="show Chromium; requires a working graphical display")
    command.add_argument("--browser-executable", help="explicit Chromium executable instead of Playwright's installed build")
    command.add_argument("--timeout", type=float, default=90, help="active per-URL time budget in seconds")
    command.add_argument("--request-timeout", type=float, default=20, help="per-request socket timeout in seconds")
    command.add_argument("--retries", type=int, default=2, help="additional attempts for transient failures")
    command.add_argument("--concurrency", type=int, default=4, help="simultaneous URL acquisitions")
    command.add_argument("--browser-concurrency", type=int, default=2, help="simultaneous isolated browser contexts")
    command.add_argument("--http-workers", type=int, default=8, help="maximum HTTP worker threads")
    command.add_argument("--max-bytes", type=int, default=16 * 1024 * 1024, help="encoded/decoded response and final DOM limit")
    command.add_argument("--max-total-bytes", type=int, default=64 * 1024 * 1024, help="aggregate decoded response budget per URL")
    command.add_argument("--max-requests", type=int, default=80, help="maximum transport attempts per acquisition")
    command.add_argument("--settle-ms", type=int, default=800, help="DOM quiet interval, bounded by a five-second settle window")
    return command


def load_urls(arguments) -> list[str]:
    urls = list(arguments.urls)
    if arguments.input:
        text = arguments.input.read_text(encoding="utf-8-sig")
        if arguments.input.suffix.lower() == ".json":
            items = json.loads(text)
            if not isinstance(items, list) or any(not isinstance(item, str) or not item.strip() for item in items):
                raise ValueError("input JSON must be an array of nonempty URL strings")
            urls.extend(items)
        else:
            urls.extend(line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    return urls


def load_options(arguments) -> ScrapeOptions:
    actions = []
    if arguments.actions:
        entries = json.loads(arguments.actions.read_text(encoding="utf-8-sig"))
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise ValueError("actions must be a JSON array of objects")
        try:
            actions.extend(BrowserAction(**entry) for entry in entries)
        except TypeError as error:
            raise ValueError("action objects accept kind, selector, and pixels only") from error
    actions.extend(BrowserAction("click", selector) for selector in arguments.click)
    names = (
        "mode", "timeout", "request_timeout", "retries", "concurrency", "browser_concurrency", "http_workers",
        "max_bytes", "max_total_bytes", "max_requests", "wait_selector", "settle_ms", "screenshot", "headed", "browser_executable",
    )
    return ScrapeOptions(**{name: getattr(arguments, name) for name in names}, actions=tuple(actions))


async def acquire(urls: list[str], options: ScrapeOptions, output: Path, raw: bool) -> int:
    failed = False
    async with Scraper(options) as scraper:
        async for result in scraper.fetch_many(urls):
            try:
                directory = await asyncio.to_thread(save_result, result, output, options)
            except OSError as error:
                failed = True
                print(json.dumps({"ok": False, "url": result.url, "error_code": "persistence_failed",
                                  "error": f"Output could not be committed and verified ({type(error).__name__})"}),
                      file=sys.stderr if raw else sys.stdout, flush=True)
                continue
            receipt = {
                "ok": result.ok, "url": result.url, "final_url": result.final_url,
                "method": result.method, "status": result.status, "elapsed_ms": result.elapsed_ms,
                "requests": result.requests, "bytes_received": result.bytes_received,
                "directory": str(directory), "html_path": str(directory / "page.html") if result.ok else None,
                "metadata_path": str(directory / "result.json"), "manifest_path": str(directory / "manifest.json"),
                "verified": True, "warnings": result.warnings, "blocked_requests": result.blocked_requests,
                "error_code": result.error_code, "error": result.error,
            }
            if raw and result.ok:
                sys.stdout.write(result.html)
                sys.stdout.flush()
            print(json.dumps(receipt, ensure_ascii=True), file=sys.stderr if raw else sys.stdout, flush=True)
            failed = failed or not result.ok
    return int(failed)


def main(argv: list[str] | None = None) -> int:
    command = parser()
    arguments = command.parse_args(argv)
    if arguments.verify:
        if arguments.urls or arguments.input or arguments.raw:
            command.error("--verify cannot be combined with URL acquisition")
        verification = verify_result(arguments.verify)
        print(json.dumps(verification, ensure_ascii=True))
        return int(not verification["ok"])
    try:
        urls = load_urls(arguments)
        options = load_options(arguments)
    except (ValueError, OSError) as error:
        command.error(str(error))
    if not urls:
        command.error("provide at least one URL or --input")
    if arguments.raw and len(urls) != 1:
        command.error("--raw requires exactly one URL")
    try:
        return asyncio.run(acquire(urls, options, arguments.out, arguments.raw))
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 141


if __name__ == "__main__":
    raise SystemExit(main())