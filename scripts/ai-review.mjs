#!/usr/bin/env node
/**
 * Pull-request review via the xAI chat API.
 * Skips cleanly when XAI_API_KEY is unset so CI stays green before the owner
 * adds the secret. Posts with the Origin CLI when a pull request number is
 * available, and prints the note to the log (exit 0) when that CLI is missing.
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const MARKER = "<!-- audio-analyzer-ai-review -->";
const DIFF_CAP = 14_000;

export function reviewDecision(env) {
  if (!env.XAI_API_KEY?.trim()) return { action: "skip", reason: "XAI_API_KEY is not set" };
  return { action: "review" };
}

export function clipDiff(diff) {
  const text = diff.trim();
  if (text.length <= DIFF_CAP) return text;
  return `${text.slice(0, DIFF_CAP)}\n\n[diff truncated]`;
}

export function reviewPrompt(diff) {
  return [
    "You are reviewing a pull request for the AI Music & Audio Analysis Suite, a local client that sends audio to a RunPod Serverless worker.",
    "Comment only on real bugs: audio decode or base64 handling, handler error paths, crashed analysis, or secrets (API keys, endpoint IDs) leaking into logs, HTML, or commits.",
    "Skip style nits. Use short paragraphs. If nothing is wrong, say so in one sentence.",
    "",
    clipDiff(diff),
  ].join("\n");
}

function pullRequestNumber(env) {
  if (env.PR_NUMBER) return String(env.PR_NUMBER);
  if (!env.GITHUB_EVENT_PATH) return "";
  try {
    const event = JSON.parse(readFileSync(env.GITHUB_EVENT_PATH, "utf8"));
    return event.pull_request?.number ? String(event.pull_request.number) : "";
  } catch {
    return "";
  }
}

function diffAgainstBase(env) {
  const base = env.GITHUB_BASE_REF || env.BASE_REF || "main";
  try {
    execFileSync("git", ["fetch", "origin", base, "--depth", "50"], { stdio: "ignore" });
  } catch {
    // The checkout may already contain the base.
  }
  try {
    return execFileSync("git", ["diff", `origin/${base}...HEAD`], { encoding: "utf8", maxBuffer: 8_000_000 });
  } catch {
    return execFileSync("git", ["diff", "HEAD~1"], { encoding: "utf8", maxBuffer: 8_000_000 });
  }
}

async function askGrok(apiKey, diff) {
  const res = await fetch("https://api.x.ai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: "grok-4.5",
      max_tokens: 500,
      messages: [
        { role: "system", content: "You review code diffs. Be specific and brief." },
        { role: "user", content: reviewPrompt(diff) },
      ],
    }),
    signal: AbortSignal.timeout(45_000),
  });
  if (!res.ok) throw new Error(`xAI review failed (${res.status})`);
  const body = await res.json();
  const text = body?.choices?.[0]?.message?.content?.trim();
  if (!text) throw new Error("xAI review returned an empty note");
  return text;
}

export function commentDestination(env) {
  const number = pullRequestNumber(env);
  if (env.GITHUB_TOKEN?.trim() && env.GITHUB_REPOSITORY?.trim() && number) return "github";
  if (number) return "origin";
  return "stdout";
}

export function originCliAvailable() {
  try {
    execFileSync("origin", ["--help"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

function publishOnOrigin(number, body) {
  const file = execFileSync("mktemp", { encoding: "utf8" }).trim();
  try {
    writeFileSync(file, body);
    execFileSync(
      "origin",
      ["pr", "comment", String(number), "--body-file", file, "--edit-last", "--create-if-none"],
      { stdio: "inherit" },
    );
  } finally {
    try {
      execFileSync("rm", ["-f", file]);
    } catch {
      /* the temp file is only the review text */
    }
  }
}

async function publishOnGitHub(env, number, body) {
  const token = env.GITHUB_TOKEN.trim();
  const repo = env.GITHUB_REPOSITORY.trim();
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
  };
  const list = await fetch(`https://api.github.com/repos/${repo}/issues/${number}/comments?per_page=100`, { headers });
  if (!list.ok) throw new Error(`Could not list PR comments (${list.status})`);
  const comments = await list.json();
  const existing = Array.isArray(comments) ? comments.find((comment) => String(comment.body ?? "").includes(MARKER)) : null;
  const payload = JSON.stringify({ body });
  const url = existing
    ? `https://api.github.com/repos/${repo}/issues/comments/${existing.id}`
    : `https://api.github.com/repos/${repo}/issues/${number}/comments`;
  const sent = await fetch(url, { method: existing ? "PATCH" : "POST", headers, body: payload });
  if (!sent.ok) throw new Error(`Could not publish the review (${sent.status})`);
}

export async function publish(env, body) {
  const number = pullRequestNumber(env);
  const destination = commentDestination(env);
  if (destination === "stdout") {
    console.log(body);
    console.log("AI review printed locally. Set PR_NUMBER to comment on the Origin pull request.");
    return;
  }
  if (destination === "github") {
    try {
      await publishOnGitHub(env, number, body);
      return;
    } catch (error) {
      console.error(error instanceof Error ? error.message : error);
      console.log("GitHub comment failed. Falling back to the Origin CLI.");
    }
  }
  if (!originCliAvailable()) {
    console.log(body);
    console.log("AI review printed to the log: origin CLI is not available.");
    return;
  }
  try {
    publishOnOrigin(number, body);
  } catch (error) {
    console.log(body);
    console.error(error instanceof Error ? error.message : error);
    console.log("Origin comment failed. The review is in the log above.");
  }
}

async function main() {
  const decision = reviewDecision(process.env);
  if (decision.action === "skip") {
    console.log(`AI review skipped: ${decision.reason}`);
    return;
  }
  const diff = diffAgainstBase(process.env);
  if (!diff.trim()) {
    console.log("AI review skipped: empty diff");
    return;
  }
  const note = await askGrok(process.env.XAI_API_KEY.trim(), diff);
  const body = `${MARKER}\n**Grok review**\n\n${note}`;
  await publish(process.env, body);
}

const isDirect = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isDirect) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}
