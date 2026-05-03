import { describe, it, expect } from "vitest";
import { splitSegments } from "../segmentSplit";

describe("splitSegments", () => {
  it("90/10 split with different ACVs produces correct per-segment counts", () => {
    const result = splitSegments({
      created_pipe: 1_000_000,
      segment_share: { enterprise: 0.9, commercial: 0.1 },
      acv: { enterprise: 250_000, commercial: 75_000 },
    });
    expect(result.pipe_by_segment["enterprise"]).toBeCloseTo(900_000, 0);
    expect(result.pipe_by_segment["commercial"]).toBeCloseTo(100_000, 0);
    expect(result.count_by_segment["enterprise"]).toBeCloseTo(900_000 / 250_000, 3);
    expect(result.count_by_segment["commercial"]).toBeCloseTo(100_000 / 75_000, 3);
  });

  it("100/0 split with positive Com ACV returns zero Com count without 0/0", () => {
    const result = splitSegments({
      created_pipe: 1_000_000,
      segment_share: { enterprise: 1.0, commercial: 0.0 },
      acv: { enterprise: 250_000, commercial: 75_000 },
    });
    expect(result.pipe_by_segment["commercial"]).toBe(0);
    expect(result.count_by_segment["commercial"]).toBe(0);
    expect(result.count_by_segment["enterprise"]).toBe(4);
  });

  it("additivity: Ent-only + Com-only equal the mixed result for fixed created_pipe", () => {
    const ent_only = splitSegments({
      created_pipe: 900_000,
      segment_share: { enterprise: 1.0, commercial: 0.0 },
      acv: { enterprise: 250_000, commercial: 75_000 },
    });
    const com_only = splitSegments({
      created_pipe: 100_000,
      segment_share: { enterprise: 0.0, commercial: 1.0 },
      acv: { enterprise: 250_000, commercial: 75_000 },
    });
    const mixed = splitSegments({
      created_pipe: 1_000_000,
      segment_share: { enterprise: 0.9, commercial: 0.1 },
      acv: { enterprise: 250_000, commercial: 75_000 },
    });
    expect(ent_only.count_by_segment["enterprise"] + com_only.count_by_segment["commercial"]).toBeCloseTo(
      mixed.count_by_segment["enterprise"] + mixed.count_by_segment["commercial"],
      3,
    );
  });

  it("splits across 3 segments without literal access", () => {
    const segment_share = { enterprise: 0.5, commercial: 0.3, smb: 0.2 };
    const acv = { enterprise: 200_000, commercial: 80_000, smb: 30_000 };
    const result = splitSegments({ created_pipe: 1_000_000, segment_share, acv });
    expect(Object.keys(result.pipe_by_segment).sort()).toEqual(["commercial", "enterprise", "smb"]);
    expect(result.count_by_segment["smb"]).toBeGreaterThan(0);
    expect(result.total_count).toBeCloseTo(
      1_000_000 * 0.5 / 200_000 + 1_000_000 * 0.3 / 80_000 + 1_000_000 * 0.2 / 30_000,
      3,
    );
  });
});
