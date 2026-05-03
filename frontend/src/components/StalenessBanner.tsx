interface Props {
  staleDays: number;
}

export function StalenessBanner({ staleDays }: Props) {
  const isVeryStale = staleDays > 3;
  return (
    <div
      className={`px-4 py-2 text-sm text-center ${
        isVeryStale ? "bg-red-100 text-red-800" : "bg-yellow-100 text-yellow-800"
      }`}
    >
      {isVeryStale
        ? `Data is ${staleDays} days old. Run the engine to refresh.`
        : `Data last refreshed ${staleDays} day(s) ago. Some metrics may be outdated.`}
    </div>
  );
}
