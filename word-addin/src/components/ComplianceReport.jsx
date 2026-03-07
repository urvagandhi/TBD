export default function ComplianceReport({ report }) {
  if (!report) return null;

  const overall = report.overall_score ?? report.score ?? 0;
  const sections = report.sections || report.section_scores || {};

  const scoreColor = (s) => {
    if (s >= 80) return "text-green-400";
    if (s >= 60) return "text-yellow-400";
    return "text-red-400";
  };

  return (
    <div className="space-y-4">
      {/* Overall score */}
      <div className="text-center">
        <div className={`text-4xl font-bold ${scoreColor(overall)}`}>
          {overall}
        </div>
        <div className="text-xs text-gray-400">Overall Compliance Score</div>
      </div>

      {/* Score bar */}
      <div className="h-3 w-full overflow-hidden rounded-full bg-gray-700">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            overall >= 80
              ? "bg-green-500"
              : overall >= 60
              ? "bg-yellow-500"
              : "bg-red-500"
          }`}
          style={{ width: `${overall}%` }}
        />
      </div>

      {/* Section breakdown */}
      {Object.keys(sections).length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Section Scores
          </h3>
          {Object.entries(sections).map(([name, score]) => (
            <div key={name} className="flex items-center justify-between text-sm">
              <span className="text-gray-300 capitalize">
                {name.replace(/_/g, " ")}
              </span>
              <span className={`font-medium ${scoreColor(typeof score === "object" ? score.score : score)}`}>
                {typeof score === "object" ? score.score : score}/100
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
