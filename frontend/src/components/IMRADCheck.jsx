import { CheckCircle, XCircle } from "lucide-react";

const IMRAD_LABELS = {
  introduction: "Introduction",
  methods: "Methods",
  results: "Results",
  discussion: "Discussion",
};

export default function IMRADCheck({ imrad }) {
  // Edge case: null or undefined imrad
  if (!imrad) return null;

  const sections = Object.keys(IMRAD_LABELS);
  const allPresent = sections.every((s) => imrad[s]);
  const missingSections = sections.filter((s) => !imrad[s]);

  // Edge case: imrad_complete true but booleans say otherwise — use booleans as truth
  const isComplete = allPresent;

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 p-5 space-y-4">

      <h3 className="text-sm font-semibold text-white">IMRAD Structure Check</h3>

      {/* Section pills */}
      <div className="flex flex-wrap gap-2">
        {sections.map((s) => {
          const present = Boolean(imrad[s]);
          return (
            <div
              key={s}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${
                present
                  ? "bg-green-950/40 border-green-800/50 text-green-400"
                  : "bg-red-950/30 border-red-900/40 text-red-400"
              }`}
            >
              {present
                ? <CheckCircle className="w-3.5 h-3.5 shrink-0" />
                : <XCircle className="w-3.5 h-3.5 shrink-0" />
              }
              {IMRAD_LABELS[s]}
            </div>
          );
        })}
      </div>

      {/* Status banner */}
      {isComplete ? (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-green-950/30 border border-green-800/30 text-sm text-green-500">
          <CheckCircle className="w-4 h-4 shrink-0" />
          Complete IMRAD structure detected.
        </div>
      ) : (
        <div className="bg-yellow-950/20 border border-yellow-800/20 rounded-xl px-4 py-3 space-y-1">
          <p className="text-sm text-yellow-500 font-medium">Incomplete structure detected</p>
          {missingSections.length > 0 && (
            <p className="text-xs text-yellow-700">
              Missing: {missingSections.map((s) => IMRAD_LABELS[s]).join(", ")}.
              Consider adding {missingSections.length === 1 ? "a" : ""}{" "}
              {missingSections.map((s) => IMRAD_LABELS[s]).join("/")} section
              {missingSections.length > 1 ? "s" : ""}.
            </p>
          )}
        </div>
      )}

    </div>
  );
}
