import { existsSync } from "node:fs";
import { resolve } from "node:path";

const frontendRoot = resolve(import.meta.dirname, "..");
const protectedDataModeEnabled = process.env.VITE_PROTECTED_DATA_MODE === "supabase-private";
const requiredAssets = [
  resolve(frontendRoot, "public", "data", "profiles", "index.json"),
];

function ensureCheckedInAssets() {
  const missing = requiredAssets.filter((assetPath) => !existsSync(assetPath));
  if (missing.length === 0) {
    console.log(
      "[sync:data] Using checked-in frontend data bundle.",
    );
    return;
  }

  console.error("[sync:data] Missing required frontend data bundle assets:");
  missing.forEach((assetPath) => console.error(`  - ${assetPath}`));
  process.exit(1);
}

if (protectedDataModeEnabled) {
  console.log(
    "[sync:data] Protected data mode enabled. Skipping public frontend data sync for this build.",
  );
  process.exit(0);
}

ensureCheckedInAssets();
process.exit(0);
