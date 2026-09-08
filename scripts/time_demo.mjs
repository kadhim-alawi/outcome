// Measure when each row of the demo actually lands on screen.
//
//   python3 -m outcome.server &
//   npm install playwright && npx playwright install chromium
//   node scripts/time_demo.mjs            # default pace
//   node scripts/time_demo.mjs 5000       # recording pace
//
// The timings in docs/demo-script.md come from this rather than from a
// stopwatch. They were wrong by about six times when they were estimates: the
// whole run lands in under fifteen seconds at the default pace, while the shot
// list had budgeted two minutes for it, so the narration would have played over
// a finished screen.
//
// Re-run it after changing the pace, the scenario, or anything that adds a row.
import { chromium } from "playwright";

const pace = process.argv[2];
const url = `http://127.0.0.1:8765/${pace ? `?pace=${pace}` : ""}`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));

await page.goto(url, { waitUntil: "networkidle" });
await page.waitForSelector(".grid.constraint");

const beats = [];
await page.exposeFunction("beat", (text, ms) => beats.push({ text, ms }));

// Stamp each timeline row as the page appends it, rather than polling, so the
// numbers are when a viewer would actually see it.
await page.evaluate(() => {
  window.__start = performance.now();
  new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType === 1 && node.classList?.contains("step")) {
          const heading = node.querySelector("h3");
          window.beat(
            heading ? heading.textContent.trim() : "(row)",
            Math.round(performance.now() - window.__start),
          );
        }
      }
    }
  }).observe(document.getElementById("timeline"), { childList: true });
});

const startedAt = Date.now();
await page.click("#start");
await page.waitForSelector("#yes", { timeout: 120000 });
const toApproval = Date.now() - startedAt;
await page.evaluate(() =>
  window.beat("APPROVAL CARD", Math.round(performance.now() - window.__start)),
);

const approvedAt = Date.now();
await page.click("#yes");
await page.waitForSelector(".result.ok", { timeout: 120000 });
const afterApproval = Date.now() - approvedAt;
await page.evaluate(() =>
  window.beat("RESULT CARD", Math.round(performance.now() - window.__start)),
);

console.log(`\n${url}\n`);
console.log("  ms from Start   row");
for (const beat of beats) {
  console.log(`${String(beat.ms).padStart(15)}   ${beat.text.slice(0, 76)}`);
}
console.log("\n  Start -> approval card :", (toApproval / 1000).toFixed(1), "s");
console.log("  Approve -> result card :", (afterApproval / 1000).toFixed(1), "s");
console.log("  Whole run              :", ((toApproval + afterApproval) / 1000).toFixed(1), "s");
if (errors.length) {
  console.log("\n  PAGE ERRORS:", errors);
  process.exitCode = 1;
}
await browser.close();
