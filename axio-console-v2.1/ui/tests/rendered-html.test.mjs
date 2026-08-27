import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";

async function withServer(run) {
  const port = 3300 + (process.pid % 200);
  const child = spawn(
    process.execPath,
    [
      fileURLToPath(
        new URL("../node_modules/next/dist/bin/next", import.meta.url),
      ),
      "start",
      "--hostname",
      "127.0.0.1",
      "--port",
      `${port}`,
    ],
    {
      cwd: fileURLToPath(new URL("..", import.meta.url)),
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  try {
    let lastError;
    for (let attempt = 0; attempt < 40; attempt += 1) {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/`);
        if (response.ok) {
          return await run(response, port);
        }
      } catch (error) {
        lastError = error;
      }
      await delay(250);
    }
    throw lastError ?? new Error("Next.js test server did not become ready.");
  } finally {
    child.kill();
  }
}

test("server-renders the AXIO application shell", async () => {
  await withServer(async (response, port) => {
    const html = await response.text();

    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
    assert.match(html, /<title>AXIO Console<\/title>/i);
    assert.match(html, /AXIO/);
    assert.match(html, /CONSOLE/);
    assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);

    const cssPath = html.match(/href="([^"]+\.css[^"]*)"/)?.[1];
    assert.ok(cssPath, "rendered page should include a stylesheet");
    const cssResponse = await fetch(`http://127.0.0.1:${port}${cssPath}`);
    assert.equal(cssResponse.status, 200);
    assert.match(
      cssResponse.headers.get("content-type") ?? "",
      /^text\/css\b/i,
    );
  });
});

test("keeps backend selection automatic in the client", async () => {
  const source = await readFile(
    new URL("../app/ConsoleApp.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /modelByMode: Record<Mode, string>/);
  assert.match(source, /cloudModes\[mode\]/);
  assert.match(source, /approval_required/);
  assert.match(source, /EventSource/);
});
