import { Card } from "../components/ui";
import { SectionHeader } from "../components/workbook";
import type { ScreenEntry } from "./screens";

/** An honest placeholder: the screen is planned and is not here yet. It shows no figures. */
export function NotBuilt({ screen }: { screen: ScreenEntry }) {
  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <SectionHeader title={screen.label} subtitle={screen.question} />
      <Card className="p-5" data-testid="not-built">
        <h3 className="text-sm font-semibold text-ft-brand">Not built yet</h3>
        <p className="mt-1 text-sm text-slate-600">
          This screen is planned and has not been built. Nothing is shown here rather than a figure that is not tied to the
          core's report. The Forecast screen is built and shows the same company and scenario.
        </p>
      </Card>
    </div>
  );
}
