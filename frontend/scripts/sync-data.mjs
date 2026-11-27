import { existsSync } from "node:fs";
import { resolve } from "node:path";

const frontendRoot = resolve(import.meta.dirname, "..");
const requiredAssets = [
  resolve(frontendRoot, "public", "data", "reports", "index.json"),
];

function ensureCheckedInAssets() {
  const missing = requiredAssets.filter((assetPath) => !existsSync(assetPath));
  if (missing.length === 0) {
    console.log(
      "[sync:data] Using the checked-in report files (python -m engine.scripts.generate_app_reports writes them).",
    );
    return;
  }

  console.error("[sync:data] Missing required report files:");
  missing.forEach((assetPath) => console.error(`  - ${assetPath}`));
  process.exit(1);
}

ensureCheckedInAssets();
process.exit(0);
