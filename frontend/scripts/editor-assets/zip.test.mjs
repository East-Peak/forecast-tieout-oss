import { inflateRawSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { crc32, zip } from "./zip.mjs";

/** A reader written from the format's description, not from the writer: the central directory, then each entry. */
function readZip(buf) {
  const eocd = buf.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  expect(eocd).toBeGreaterThanOrEqual(0);
  const count = buf.readUInt16LE(eocd + 10);
  let at = buf.readUInt32LE(eocd + 16);
  const out = {};
  for (let i = 0; i < count; i++) {
    expect(buf.readUInt32LE(at)).toBe(0x02014b50);
    const method = buf.readUInt16LE(at + 10);
    const crc = buf.readUInt32LE(at + 16);
    const size = buf.readUInt32LE(at + 20);
    const plain = buf.readUInt32LE(at + 24);
    const nameLength = buf.readUInt16LE(at + 28);
    const extra = buf.readUInt16LE(at + 30);
    const comment = buf.readUInt16LE(at + 32);
    const local = buf.readUInt32LE(at + 42);
    const name = buf.subarray(at + 46, at + 46 + nameLength).toString("utf8");
    const dataAt = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
    const raw = buf.subarray(dataAt, dataAt + size);
    const data = method === 8 ? inflateRawSync(raw) : raw;
    expect(data.length, `${name} length`).toBe(plain);
    expect(crc32(data), `${name} crc`).toBe(crc);
    out[name] = data.toString("utf8");
    at += 46 + nameLength + extra + comment;
  }
  return out;
}

describe("the zip writer", () => {
  it("writes entries a reader gets back unchanged, nested paths and non-ASCII text included", () => {
    const entries = [
      { name: "engine/tieout_core/a.py", data: Buffer.from("x = 1\n".repeat(100)) },
      { name: "engine/data-v2/c/deals.csv", data: Buffer.from("id,arr\n1,2\n") },
      { name: "note.txt", data: Buffer.from("café") },
      { name: "empty.txt", data: Buffer.alloc(0) },
    ];
    const read = readZip(zip(entries));
    expect(Object.keys(read)).toEqual(entries.map((e) => e.name).sort());
    for (const e of entries) expect(read[e.name]).toBe(e.data.toString("utf8"));
  });

  it("is the same bytes every time, whatever order the entries are given in", () => {
    const a = { name: "b.txt", data: Buffer.from("two") };
    const b = { name: "a.txt", data: Buffer.from("one") };
    expect(zip([a, b]).equals(zip([b, a]))).toBe(true);
  });

  it("checks against the standard CRC-32 of '123456789'", () => {
    expect(crc32(Buffer.from("123456789"))).toBe(0xcbf43926);
  });
});
