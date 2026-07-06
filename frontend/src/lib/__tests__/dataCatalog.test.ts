import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import { loadOrgProfileCatalog } from "../dataCatalog";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("data catalog", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("preserves manifest order while marking the explicit default profile", async () => {
    vi.stubEnv("VITE_DATA_BASE_URL", "/data");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const pathname = new URL(url, "http://localhost").pathname;
        if (pathname === "/data/profiles/index.json") {
          return jsonResponse({
            default: "sapling-industries",
            profiles: [
              { id: "sprout-labs", path: "./sprout-labs.json" },
              { id: "sapling-industries", path: "./sapling-industries.json" },
              { id: "mighty-oak-holdings", path: "./mighty-oak-holdings.json" },
            ],
          });
        }

        const id = pathname.match(/\/([^/]+)\.json$/)?.[1] ?? "";
        return jsonResponse({
          id,
          slug: id,
          name: id,
        });
      }),
    );

    const profiles = await loadOrgProfileCatalog();

    expect(profiles.map((profile) => profile.id)).toEqual([
      "sprout-labs",
      "sapling-industries",
      "mighty-oak-holdings",
    ]);
    expect(profiles.find((profile) => profile.id === "sapling-industries")?.isDefault).toBe(true);
    expect(profiles[0]?.isDefault).toBe(false);
  });

  it("ships exactly the three public personas with Sapling as the default", () => {
    const manifestPath = fileURLToPath(
      new URL("../../../public/data/profiles/index.json", import.meta.url),
    );
    const manifest = JSON.parse(readFileSync(manifestPath, "utf-8")) as {
      default?: string;
      profiles?: Array<{ id?: string }>;
    };

    expect(manifest.default).toBe("sapling-industries");
    expect(manifest.profiles?.map((profile) => profile.id)).toEqual([
      "sprout-labs",
      "sapling-industries",
      "mighty-oak-holdings",
    ]);

    for (const id of manifest.profiles?.map((profile) => profile.id) ?? []) {
      const profilePath = fileURLToPath(
        new URL(`../../../public/data/profiles/${id}.json`, import.meta.url),
      );
      const profile = JSON.parse(readFileSync(profilePath, "utf-8")) as { demo?: boolean };
      expect(profile.demo, `${id} profile is marked as a committed demo fixture`).toBe(true);
    }
  });
});
