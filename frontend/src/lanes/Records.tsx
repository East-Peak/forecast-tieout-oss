import { Bound } from "../binding/Bound";
import type { Binding } from "../binding/Bound";
import { DEAL } from "./bindings";
import type { ColumnKey, LanesFile, RecordsFile } from "./types";
import type { Loaded } from "./useFile";

/** The deals a cell names, in the groups the records file keeps them in; a rate's are the cohort it was measured on. */
type SetName = "open" | "created" | "cohort" | "won_carried_in" | "won_created_in_period";
const CARRIED = { set: "won_carried_in", title: "Won from pipeline carried in", short: "carried in" } as const;
const CREATED = { set: "won_created_in_period", title: "Won from pipeline created in the period", short: "created in the period" } as const;
const GROUPS: Record<ColumnKey, Array<{ set: SetName; title: string; short?: string }>> = {
  open: [{ set: "open", title: "Open at the start of the period" }],
  created: [{ set: "created", title: "Created in the period" }],
  created_arr: [{ set: "created", title: "Created in the period" }],
  win_rate: [{ set: "cohort", title: "The cohort the rate was measured on" }],
  cycle: [CARRIED, CREATED],
  won: [CARRIED, CREATED],
  avg_won_arr: [CARRIED, CREATED],
  bookings: [CARRIED, CREATED],
};

const HEADS = ["Id", "Name", "Segment", "Owner", "Created", "Close", "Status"] as const;

/** Where in the records file a cell's lists are, and the pointers of each group (null where the file does not list that group). */
function groupsOf(records: RecordsFile, path: readonly string[], periodKey: string, column: ColumnKey) {
  const rowIndex = records.rows.findIndex((r) => r.path.join("/") === path.join("/"));
  const sets = rowIndex < 0 ? undefined : records.rows[rowIndex].periods[periodKey];
  return GROUPS[column].flatMap(({ set, title, short }) => {
    const ids = sets?.[set];
    return ids ? [{ title, short, ids, pointer: `/rows/${rowIndex}/periods/${periodKey}/${set}` }] : [];
  });
}

/** The first line under a cell's actual: how many deals stand behind it, group by group. Read from the lists, never added. */
export function RecordCount({ records, path, periodKey, column }: { records: Loaded<RecordsFile>; path: readonly string[]; periodKey: string; column: ColumnKey }) {
  if (records.status === "error") return <span className="block text-[11px] text-slate-500">The records could not be loaded.</span>;
  if (records.status !== "ready") return <span className="block text-[11px] text-slate-500">Loading the records.</span>;
  const groups = groupsOf(records.doc, path, periodKey, column);
  if (groups.length === 0) return <span className="block text-[11px] text-slate-500">No records are listed for this cell.</span>;
  return (
    <span className="block text-[11px] text-slate-600" data-testid="records-count">
      Deals behind the actual:{" "}
      {groups.map((g, i) => (
        <span key={g.pointer}>
          {i > 0 ? " and " : ""}
          <Bound binding={DEAL.count} row={g.pointer} className="font-medium tabular-nums text-slate-800" />
          {g.short ? ` ${g.short}` : ""}
        </span>
      ))}
    </span>
  );
}

function arrBinding(column: ColumnKey): Binding {
  return column === "created" || column === "created_arr" ? DEAL.arrFirst : DEAL.arr;
}

/** The segment's own name where the lanes file names it; otherwise the file's word for it. */
function Segment({ lanes, slug, id }: { lanes: LanesFile; slug: string; id: string }) {
  const index = lanes.periods[0].rows.findIndex((r) => r.kind === "segment" && r.path[1] === slug);
  return index < 0 ? <Bound binding={DEAL.segment} row={`/records/${id}`} /> : <Bound binding={DEAL.segmentLabel} row={`/periods/0/rows/${index}`} />;
}

/** The table of deals behind a cell: id, name, segment, owner, created, close, status, ARR. The browser lists them and adds nothing. */
export function Records({ records, lanes, path, periodKey, column }: { records: RecordsFile; lanes: LanesFile; path: readonly string[]; periodKey: string; column: ColumnKey }) {
  const groups = groupsOf(records, path, periodKey, column);
  const first = column === "created" || column === "created_arr";
  const arr = arrBinding(column);
  if (groups.length === 0) return null;
  return (
    <section className="mt-5" data-testid="records" data-state="ready">
      <h4 className="text-xs font-semibold uppercase text-slate-500">Records</h4>
      <p className="mt-1 text-[11px] leading-snug text-slate-500">
        <Bound binding={DEAL.caveat} />
      </p>
      {groups.map((g) => (
        <div key={g.pointer} className="mt-2" data-testid="record-group">
          <p className="text-xs font-medium text-slate-700">{g.title}</p>
          <div className="mt-1 max-h-72 overflow-auto rounded-ft border border-slate-200">
            <table className="w-full text-left text-[11px] tabular-nums">
              <thead className="sticky top-0 bg-slate-50 text-slate-500">
                <tr>
                  {HEADS.map((h) => (
                    <th key={h} scope="col" className="whitespace-nowrap px-2 py-1 font-medium">
                      {h}
                    </th>
                  ))}
                  <th scope="col" className="whitespace-nowrap px-2 py-1 text-right font-medium">
                    {first ? "First ARR" : "ARR"}
                  </th>
                </tr>
              </thead>
              <tbody>
                {g.ids.map((id) => {
                  const d = records.records[id]!;
                  const row = `/records/${id}`;
                  return (
                    <tr key={id} className="border-t border-slate-100" data-testid="record-row">
                      <td className="whitespace-nowrap px-2 py-1 text-slate-700"><Bound binding={DEAL.id} row={row} /></td>
                      <td className="whitespace-nowrap px-2 py-1"><Bound binding={DEAL.name} row={row} /></td>
                      <td className="whitespace-nowrap px-2 py-1"><Segment lanes={lanes} slug={d.segment} id={id} /></td>
                      <td className="whitespace-nowrap px-2 py-1"><Bound binding={DEAL.owner} row={row} /></td>
                      <td className="whitespace-nowrap px-2 py-1"><Bound binding={DEAL.created} row={row} /></td>
                      <td className="whitespace-nowrap px-2 py-1"><Bound binding={DEAL.close} row={row} /></td>
                      <td className="whitespace-nowrap px-2 py-1"><Bound binding={DEAL.status} row={row} /></td>
                      <td className="whitespace-nowrap px-2 py-1 text-right"><Bound binding={arr} row={row} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}
