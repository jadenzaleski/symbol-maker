// The (i) buttons: every key the page uses must have a title and a text, and no text may be left unused.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const site = path.join(here, '../../site');
const { TEXT } = createRequire(import.meta.url)('../../site/info.js');
const read = f => readFileSync(path.join(site, f), 'utf8');

function used() {
  const keys = new Set();
  for (const f of readdirSync(site).filter(f => /\.(html|js)$/.test(f) && f !== 'info.js')) {
    const s = read(f);
    for (const m of s.matchAll(/data-info="([\w-]+)"/g)) keys.add(m[1]);
    for (const m of s.matchAll(/Info\.button\('([\w-]+)'/g)) keys.add(m[1]);
  }
  return keys;
}

test('every info button on the page has a title and a text', () => {
  const keys = used();
  assert.ok(keys.size >= 10, `expected a good number of info buttons, found ${keys.size}`);
  for (const k of keys) {
    assert.ok(TEXT[k], `no text for "${k}"`);
    assert.ok(TEXT[k].title.trim().length > 0, `"${k}" has no title`);
    assert.ok(typeof TEXT[k].body === 'string', `"${k}" has no body`);
  }
});

test('no text is written that nothing shows', () => {
  const keys = used();
  for (const k of Object.keys(TEXT)) assert.ok(keys.has(k), `"${k}" is never used`);
});

test('the texts are short enough to be read in a popover', () => {
  for (const [k, t] of Object.entries(TEXT)) if (t.body) assert.ok(t.body.length < 700, `"${k}" is ${t.body.length} characters`);
});
