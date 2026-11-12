import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { commentDestination, clipDiff, reviewDecision } from "./ai-review.mjs";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));

test("skips when XAI_API_KEY is missing or blank", () => {
  assert.deepEqual(reviewDecision({}), { action: "skip", reason: "XAI_API_KEY is not set" });
  assert.deepEqual(reviewDecision({ XAI_API_KEY: "   " }), {
    action: "skip",
    reason: "XAI_API_KEY is not set",
  });
});

test("reviews when XAI_API_KEY is set", () => {
  assert.deepEqual(reviewDecision({ XAI_API_KEY: "xai-test" }), { action: "review" });
});

test("clips long diffs", () => {
  const clipped = clipDiff(`x${"a".repeat(20_000)}`);
  assert.match(clipped, /\[diff truncated\]$/);
  assert.ok(clipped.length < 20_000);
});

test("prefers GitHub when a token and repository are present, otherwise Origin", () => {
  assert.equal(commentDestination({}), "stdout");
  assert.equal(commentDestination({ PR_NUMBER: "12" }), "origin");
  assert.equal(
    commentDestination({
      PR_NUMBER: "12",
      GITHUB_TOKEN: "ghp_test",
      GITHUB_REPOSITORY: "Phazzie/audio-analyzer-suite",
    }),
    "github",
  );
});

test("prints the review and exits cleanly when the origin CLI is missing", () => {
  const source = `
    const lines = [];
    console.log = (line) => lines.push(String(line));
    const { originCliAvailable, publish } = await import("./scripts/ai-review.mjs");
    if (originCliAvailable()) {
      console.error("origin is still on PATH");
      process.exit(2);
    }
    await publish({ PR_NUMBER: "7" }, "hello review");
    const logged = lines.join("\\n");
    if (!logged.includes("hello review") || !logged.includes("origin CLI is not available")) {
      console.error(logged);
      process.exit(1);
    }
  `;
  execFileSync(process.execPath, ["--input-type=module", "-e", source], {
    cwd: repoRoot,
    env: { ...process.env, PATH: "/usr/bin:/bin" },
    stdio: "inherit",
  });
});

test("the script exits 0 and prints a skip line when the key is unset", () => {
  const env = { ...process.env };
  delete env.XAI_API_KEY;
  const stdout = execFileSync("node", ["scripts/ai-review.mjs"], {
    cwd: repoRoot,
    env,
    encoding: "utf8",
  });
  assert.match(stdout, /AI review skipped: XAI_API_KEY is not set/);
});
