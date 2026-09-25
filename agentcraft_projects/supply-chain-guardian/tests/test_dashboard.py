"""Headless browser regression tests using an existing Chrome installation."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from agent.dashboard import INTERACTIVE_PAGE


BROWSER_CHECKS = r"""
(async () => {
  const results = [];
  function check(condition, name) {
    if (!condition) throw new Error(name);
    results.push(name);
  }
  try {
    check(requests.length === 0, "zero fetches on page load");
    check(document.querySelectorAll(".chat-row.agent").length === 1, "one static greeting");
    check(document.querySelectorAll(".chat-suggestions button").length === 3, "greeting suggestions");

    const host = document.createElement("div");
    document.body.appendChild(host);
    const payload = {"<img src=x onerror=alert(1)>": [null, false, 0, "<script>unsafe</scr" + "ipt>", {nested: "value"}]};
    host.innerHTML = renderReqResp({request: {method: "POST", url: "/example", body: payload}, raw_response: payload});
    check(host.querySelectorAll("details").length === 2, "separate request and response details");
    check([...host.querySelectorAll("details")].every(el => !el.open), "JSON collapsed by default");
    const block = host.querySelector("details");
    block.querySelector("summary").click();
    check(block.open && !block.querySelector(".json-readable").hidden, "expand defaults to readable");
    check(block.querySelectorAll("ul ul").length > 0, "nested readable lists");
    check(!host.querySelector("img, script"), "escaped JSON keys and strings");
    check(host.textContent.includes("<img src=x onerror=alert(1)>"), "literal readable key");
    block.querySelectorAll("button")[1].click();
    check(block.querySelector(".json-readable").hidden && !block.querySelector(".json-raw").hidden, "raw toggle");
    check(block.querySelector(".json-raw").textContent === JSON.stringify(payload, null, 2), "pretty raw JSON");
    block.querySelectorAll("button")[0].click();
    check(!block.querySelector(".json-readable").hidden, "readable toggle");
    check(host.querySelectorAll("details")[1].querySelector(".json-raw").hidden, "independent toggles");

    for (const value of [null, false, 0, "", "hello", [], {}, [1, {a: true}]]) {
      host.innerHTML = renderReqResp({raw_response: value});
      check(host.querySelector(".json-raw").textContent === JSON.stringify(value, null, 2),
            "JSON shape " + JSON.stringify(value));
    }
    host.innerHTML = renderReqResp({request: {method: "GET", url: "/example"}});
    check(!host.querySelector("details") && host.textContent.includes("No raw response"), "missing response");
    host.innerHTML = renderJsonBlock("Large", {value: "<".repeat(4000)});
    check(host.querySelector(".json-raw").textContent.length < 2600, "raw truncation");
    check(host.querySelector(".json-readable").textContent.includes("(truncated)"), "readable truncation");
    let deep = null;
    for (let i = 0; i < 100; i++) deep = {child: deep};
    check(renderJsonReadable(deep).includes("(truncated)"), "readable depth bound");

    const evidence = {mocked: true, data: null};
    host.innerHTML = renderEvidenceDetail({
      scenario_id: "test", work_iq_evidence: evidence, web_iq_evidence: evidence,
      foundry_iq_evidence: evidence, fabric_iq_evidence: evidence, trace: []
    });
    for (const source of ["fabric", "foundry", "work", "web"]) {
      host.querySelector("details.evidence-detail").open = false;
      jumpTo("ev-" + source + "-test");
      check(host.querySelector("details.evidence-detail").open, source + " citation opens outer details");
    }

    document.querySelector(".chat-suggestions button").click();
    check(requests.length === 1 && JSON.parse(requests[0].options.body).message === "list", "suggestion sends command");
    check(document.querySelector(".thinking") && document.getElementById("chat-send").disabled, "thinking indicator");
    document.getElementById("chat-input").value = "help";
    await sendChat();
    check(requests.length === 1, "duplicate send blocked");
    requests[0].resolve({ok: true, json: async () => ({
      reply: "Heading\n\n- first\n- <img src=x>\n\nLast paragraph",
      suggestions: ["explain 1", "help"], action_taken: false
    })});
    await new Promise(resolve => setTimeout(resolve, 0));
    const latest = document.querySelector(".chat-row.agent:last-child");
    check(!document.querySelector(".thinking") && !document.getElementById("chat-send").disabled, "thinking replaced");
    check(latest.querySelectorAll("p").length === 2 && latest.querySelectorAll("li").length === 2, "paragraphs and bullets");
    check(!latest.querySelector("img") && latest.textContent.includes("<img src=x>"), "safe chat text");
    check(document.querySelectorAll(".chat-suggestions").length === 1, "only latest suggestions");
    check(requests.length === 1, "read-only chat does not refresh incidents");

    document.getElementById("chat-input").value = "help";
    const failed = sendChat();
    requests[1].resolve({ok: false, status: 503, json: async () => ({detail: "Unavailable"})});
    await failed;
    check(!document.querySelector(".thinking") && document.getElementById("chat-log").textContent.includes("Unavailable"),
          "HTTP error removes thinking and reports error");
    document.getElementById("chat-input").value = "help";
    const disconnected = sendChat();
    requests[2].reject(new Error("offline"));
    await disconnected;
    check(!document.querySelector(".thinking") && !document.getElementById("chat-send").disabled, "network error cleanup");

    let loads = 0;
    load = () => { loads++; };
    document.getElementById("chat-input").value = "reprobe 1";
    const changed = sendChat();
    requests[3].resolve({ok: true, json: async () => ({reply: "Updated", action_taken: true})});
    await changed;
    check(loads === 1, "explicit action refreshes cards and accepts legacy response");
    check(requests.every(r => r.url === "/chat"), "no incident or activity fetch without explicit action");
    document.getElementById("test-results").textContent = "PASS " + results.length + " browser checks";
  } catch (error) {
    document.getElementById("test-results").textContent = "FAIL " + error.message + " after " + results.join(", ");
  }
})();
"""


class DashboardTests(unittest.TestCase):
    def test_browser_controls(self):
        chrome = os.environ.get("CHROME_BIN") or shutil.which("google-chrome") or shutil.which("chromium")
        if not chrome:
            candidate = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            chrome = candidate if Path(candidate).is_file() else None
        if not chrome:
            self.skipTest("Existing Chrome required; set CHROME_BIN")
        bootstrap = """<script>
const requests = [];
window.fetch = (url, options) => new Promise((resolve, reject) => requests.push({url, options, resolve, reject}));
</script>"""
        page = INTERACTIVE_PAGE.replace("<script>", bootstrap + "<script>", 1)
        page = page.replace("</body>", '<pre id="test-results">PENDING</pre><script>' + BROWSER_CHECKS + "</script></body>")
        with tempfile.TemporaryDirectory(prefix="guardian-browser-") as directory:
            path = Path(directory) / "test.html"
            path.write_text(page, encoding="utf-8")
            result = subprocess.run(
                [chrome, "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                 "--disable-background-networking", "--disable-extensions", "--disable-component-update",
                 "--virtual-time-budget=3000", "--dump-dom", path.as_uri()],
                capture_output=True, text=True, timeout=45,
            )
        match = re.search(r'<pre id="test-results">(.*?)</pre>', result.stdout, re.S)
        self.assertIsNotNone(match, result.stderr[-1500:])
        self.assertTrue(match.group(1).startswith("PASS "), match.group(1))
        print(match.group(1))
