/**
 * Where a displayed value lives in a core-produced file: a JSON Pointer (RFC 6901)
 * with one addition, `{property=value}`, which picks the element of an array whose
 * property equals the value ("/forecasts/methods/{method=fitted model}/by_window/2026-09").
 * A path that leads nowhere throws; it never yields a quiet undefined.
 */
export class UnboundPath extends Error {
  constructor(readonly pointer: string, why: string) {
    super(`unbound path ${pointer}: ${why}`);
  }
}

const FILTER = /^\{([^=}]+)=(.*)\}$/;

function decode(segment: string): string {
  return segment.replace(/~1/g, "/").replace(/~0/g, "~");
}

/**
 * ``nullBelowNull``: a null the file holds makes everything below it null too (a range that is
 * null has a null low end). Only bindings that state how they say "unavailable" ask for this.
 */
export function resolvePointer(doc: unknown, pointer: string, options: { nullBelowNull?: boolean } = {}): unknown {
  if (!pointer.startsWith("/")) throw new UnboundPath(pointer, "a pointer must start with /");
  let node: unknown = doc;
  for (const raw of pointer.slice(1).split("/")) {
    if (node === null && options.nullBelowNull) return null;
    const filter = FILTER.exec(raw);
    if (Array.isArray(node)) {
      if (filter) {
        node = node.find(
          (item) => typeof item === "object" && item !== null && (item as Record<string, unknown>)[filter[1]] === filter[2],
        );
      } else {
        node = /^\d+$/.test(raw) ? node[Number(raw)] : undefined; // arithmetic-ok: an array index from a pointer, not a report value
      }
    } else if (typeof node === "object" && node !== null && !filter) {
      const key = decode(raw);
      node = Object.prototype.hasOwnProperty.call(node, key) ? (node as Record<string, unknown>)[key] : undefined;
    } else {
      node = undefined;
    }
    if (node === undefined) throw new UnboundPath(pointer, `nothing at ${raw}`);
  }
  return node;
}
