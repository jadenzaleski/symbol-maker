// The zip writer used for edited .symbolset downloads. Checked against Python's own zipfile, an independent reader.
import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';

const Zip = createRequire(import.meta.url)('../../site/zip.js');
const PY = `import sys, json, zipfile
z = zipfile.ZipFile(sys.argv[1])
print(json.dumps({"bad": z.testzip(), "files": {i.filename: z.read(i).decode("utf-8") for i in z.infolist()}}))`;

function readBack(bytes) {
  const dir = mkdtempSync(path.join(tmpdir(), 'zip-'));
  try {
    writeFileSync(path.join(dir, 'a.zip'), bytes);
    return JSON.parse(execFileSync('python3', ['-I', '-c', PY, path.join(dir, 'a.zip')], { encoding: 'utf8' }));
  } finally { rmSync(dir, { recursive: true, force: true }); }
}

test('a zip made here opens, passes its checksums and holds exactly what was put in, names and text intact', () => {
  const files = [{ name: 'heart.symbolset/Contents.json', data: '{\n  "a": 1\n}' },
                 { name: 'heart.symbolset/heart.svg', data: '<svg>é — 日本</svg>\n'.repeat(500) },
                 { name: 'LICENSE-lucide.txt', data: '' }];
  const r = readBack(Zip.build(files));
  assert.equal(r.bad, null);
  assert.deepEqual(r.files, Object.fromEntries(files.map(f => [f.name, f.data])));
});

test('the same input gives the same bytes (no clock inside)', () => {
  const f = [{ name: 'a.txt', data: 'x' }];
  assert.deepEqual(Zip.build(f), Zip.build(f));
});

test('crc32 matches the standard check value', () => {
  assert.equal(Zip.crc32(new TextEncoder().encode('123456789')), 0xCBF43926);
});
