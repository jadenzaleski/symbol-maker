'use strict';
/* A minimal zip writer (files stored without compression, fixed timestamps), so an edited .symbolset can be built in the
   browser. The files are a few KB of text, so compressing them would save nothing worth the code. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Zip = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const TABLE = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
    return t;
  })();

  function crc32(bytes) {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < bytes.length; i++) c = TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  const DOS_TIME = 0, DOS_DATE = ((2020 - 1980) << 9) | (1 << 5) | 1;       // 2020-01-01 00:00, like the published zips
  const UTF8 = 0x0800, UNIX_MADE_BY = (3 << 8) | 20, MODE_644 = (0o100644 << 16) >>> 0;

  /** files: [{ name, data: string | Uint8Array }] -> Uint8Array */
  function build(files) {
    const enc = new TextEncoder(), chunks = [], central = [];
    let offset = 0;
    for (const f of files) {
      const name = enc.encode(f.name), data = typeof f.data === 'string' ? enc.encode(f.data) : f.data, crc = crc32(data);
      const local = new DataView(new ArrayBuffer(30));
      [[0, 0x04034B50, 4], [4, 20, 2], [6, UTF8, 2], [8, 0, 2], [10, DOS_TIME, 2], [12, DOS_DATE, 2], [14, crc, 4],
       [18, data.length, 4], [22, data.length, 4], [26, name.length, 2], [28, 0, 2]].forEach(([o, v, n]) => (n === 4 ? local.setUint32(o, v, true) : local.setUint16(o, v, true)));
      chunks.push(new Uint8Array(local.buffer), name, data);
      const c = new DataView(new ArrayBuffer(46));
      [[0, 0x02014B50, 4], [4, UNIX_MADE_BY, 2], [6, 20, 2], [8, UTF8, 2], [10, 0, 2], [12, DOS_TIME, 2], [14, DOS_DATE, 2], [16, crc, 4],
       [20, data.length, 4], [24, data.length, 4], [28, name.length, 2], [30, 0, 2], [32, 0, 2], [34, 0, 2], [36, 0, 2], [38, MODE_644, 4],
       [42, offset, 4]].forEach(([o, v, n]) => (n === 4 ? c.setUint32(o, v, true) : c.setUint16(o, v, true)));
      central.push(new Uint8Array(c.buffer), name);
      offset += 30 + name.length + data.length;
    }
    const size = central.reduce((n, a) => n + a.length, 0);
    const end = new DataView(new ArrayBuffer(22));
    [[0, 0x06054B50, 4], [4, 0, 2], [6, 0, 2], [8, files.length, 2], [10, files.length, 2], [12, size, 4], [16, offset, 4], [20, 0, 2]]
      .forEach(([o, v, n]) => (n === 4 ? end.setUint32(o, v, true) : end.setUint16(o, v, true)));
    const all = [...chunks, ...central, new Uint8Array(end.buffer)];
    const out = new Uint8Array(all.reduce((n, a) => n + a.length, 0));
    let at = 0;
    for (const a of all) { out.set(a, at); at += a.length; }
    return out;
  }

  return { build, crc32 };
});
