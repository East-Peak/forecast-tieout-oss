interface Props {
  onDownloadJSON: () => void;
  onDownloadCSV: () => void;
  onDownloadAuditReport: () => void;
  onDownloadXLSX: () => void;
}

export function ExportDownloads({
  onDownloadJSON,
  onDownloadCSV,
  onDownloadAuditReport,
  onDownloadXLSX,
}: Props) {
  return (
    <div className="flex flex-wrap gap-3">
      <button
        onClick={onDownloadXLSX}
        className="flex items-center gap-2 rounded-lg border border-violet-300 bg-slate-50 px-4 py-2.5 text-sm font-medium text-violet-600 transition-colors hover:bg-violet-50"
      >
        Download XLSX (Auditable Workbook)
      </button>
      <button
        onClick={onDownloadJSON}
        className="flex items-center gap-2 rounded-lg border border-blue-300 bg-slate-50 px-4 py-2.5 text-sm font-medium text-blue-600 transition-colors hover:bg-blue-50"
      >
        Download JSON (Saved Snapshot)
      </button>
      <button
        onClick={onDownloadCSV}
        className="flex items-center gap-2 rounded-lg border border-emerald-300 bg-slate-50 px-4 py-2.5 text-sm font-medium text-emerald-600 transition-colors hover:bg-emerald-50"
      >
        Download CSV (Active Scenario)
      </button>
      <button
        onClick={onDownloadAuditReport}
        className="flex items-center gap-2 rounded-lg border border-amber-300 bg-slate-50 px-4 py-2.5 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-50"
      >
        Download Audit Report (Saved Snapshot)
      </button>
    </div>
  );
}
