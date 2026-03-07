const STAGES = ["Ingest", "Parse", "Transform", "Validate"];

export default function ProgressBar({ progress, stage }) {
  const pct = Math.min(100, Math.max(0, progress || 0));
  const currentStage = stage || "Starting";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span>{currentStage}...</span>
        <span>{pct}%</span>
      </div>

      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-700">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex justify-between">
        {STAGES.map((s) => (
          <span
            key={s}
            className={`text-[10px] ${
              currentStage.toLowerCase().includes(s.toLowerCase())
                ? "font-semibold text-blue-400"
                : "text-gray-500"
            }`}
          >
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}
