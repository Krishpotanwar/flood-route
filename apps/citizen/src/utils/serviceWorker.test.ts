import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";

test("service worker isolates subpath caches and keeps report photos network-only", async () => {
  const scope = "https://example.com/app/";
  const prefix = `floodroute-${scope}-`;
  const handlers = new Map<string, (event: unknown) => void>();
  const deleted: string[] = [];
  let precached: string[] = [];
  let matched = "";
  let pending: Promise<unknown> = Promise.resolve();
  let response: Promise<Response | undefined> | undefined;
  const source = await readFile(new URL("../../public/sw.js", import.meta.url), "utf8");

  runInNewContext(source, {
    URL,
    self: {
      registration: { scope },
      skipWaiting() {},
      clients: { claim() {} },
      addEventListener(name: string, handler: (event: unknown) => void) {
        handlers.set(name, handler);
      },
    },
    caches: {
      open: async () => ({ addAll: async (urls: string[]) => { precached = urls; } }),
      keys: async () => [`${prefix}v3`, `${prefix}v4`, "another-app-cache"],
      delete: async (name: string) => { deleted.push(name); },
      match: async (url: string) => { matched = url; return new Response("offline shell"); },
    },
    fetch: async () => { throw new Error("offline"); },
  });

  const waitUntil = (promise: Promise<unknown>) => { pending = promise; };
  handlers.get("install")!({ waitUntil });
  await pending;
  assert.equal(precached.length, 4);
  assert.ok(precached.every((url) => url.startsWith(scope)));

  handlers.get("activate")!({ waitUntil });
  await pending;
  assert.deepEqual(deleted, [`${prefix}v3`]);

  const respondWith = (promise: Promise<Response | undefined>) => { response = promise; };
  handlers.get("fetch")!({
    request: { method: "GET", mode: "navigate", url: scope },
    respondWith,
  });
  assert.ok(response);
  assert.equal(await (await response)?.text(), "offline shell");
  assert.equal(matched, `${scope}index.html`);

  response = undefined;
  handlers.get("fetch")!({
    request: { method: "GET", url: "https://example.com/v1/reports/photo/ph_test.jpg" },
    respondWith,
  });
  assert.equal(response, undefined);
  handlers.get("fetch")!({
    request: { method: "GET", url: "https://tile.openstreetmap.org/12/2931/1898.png" },
    respondWith,
  });
  assert.equal(response, undefined);
});
