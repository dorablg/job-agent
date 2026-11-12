// Runs the extension's shared logic (extension/core.js) under Node: node tests/js/core_test.js <blob.json> <password>
// Checks that a blob written by Python (agent/secure.py) decrypts in WebCrypto, and the listing matcher.
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const [blobFile, password] = process.argv.slice(2);
const ctx = { crypto: globalThis.crypto, atob, TextEncoder, TextDecoder, fetch: async () => { throw new Error("no network"); }, console };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname + "/../../extension/core.js", "utf8") + ";this.FLOUS = FLOUS;", ctx);
const F = ctx.FLOUS;

(async () => {
  const blob = JSON.parse(fs.readFileSync(blobFile, "utf8"));
  const key = await F.deriveKey(password, blob);
  const D = await F.decryptBlob(key, blob);
  assert.strictEqual(D.listings[0].title, "Junior Data Analyst");
  await assert.rejects(async () => F.decryptBlob(await F.deriveKey("wrong", blob), blob), /Wrong dashboard password/);

  const page = { host: "jobs.acme.com", url: "https://example.com/job?src=x", title: "Junior Data Analyst - Acme", text: "Apply to Acme" };
  assert.strictEqual(F.matchListing(D, page).id, "x");
  assert.strictEqual(F.matchListing(D, { host: "other.org", url: "https://other.org", title: "Chef", text: "Bake" }), null);
  console.log("core.js OK");
})().catch(e => { console.error(e); process.exit(1); });
