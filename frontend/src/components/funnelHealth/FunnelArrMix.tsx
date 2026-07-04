import { Card } from "../ui";
import { formatMoney } from "../../lib/format";
import type { FunnelHealthArrMix } from "../../lib/funnelHealthViewModel";

interface FunnelArrMixProps {
  arrMix: FunnelHealthArrMix;
}

export function FunnelArrMix({ arrMix }: FunnelArrMixProps) {
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold text-slate-800 tracking-tight mb-1">
        ARR Mix: Plan vs Trajectory
      </h3>
      {arrMix.hasBreakdown ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-3">
          {arrMix.quarters.map((quarter) => (
            <div key={quarter.quarter}>
              <p className="text-xs font-medium text-slate-700 mb-2">
                {quarter.quarter}
              </p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-slate-500 mb-2">Top-Down Plan</p>
                  <div className="space-y-1 text-sm">
                    <ArrMixLine label="Sales-Led" value={quarter.plan.salesLed} />
                    <ArrMixLine label="PLG" value={quarter.plan.plg} />
                    <ArrMixLine label="Expansion" value={quarter.plan.expansion} />
                  </div>
                </div>
                <div>
                  <p className="text-xs text-slate-500 mb-2">Trajectory Forecast</p>
                  <div className="space-y-1 text-sm">
                    <ArrMixLine
                      label="Sales-Led"
                      value={quarter.trajectory.salesLed}
                    />
                    <ArrMixLine label="PLG" value={quarter.trajectory.plg} />
                    <ArrMixLine
                      label="Expansion"
                      value={quarter.trajectory.expansion}
                    />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-500 mt-2">{arrMix.suppressedMessage}</p>
      )}
    </Card>
  );
}

function ArrMixLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-600">{label}</span>
      <span className="font-medium">{formatMoney(value)}</span>
    </div>
  );
}
