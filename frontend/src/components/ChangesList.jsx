import { useState } from "react";
import { CheckCheck, ChevronDown, ChevronUp } from "lucide-react";

const INITIAL_VISIBLE = 6;

export default function ChangesList({ changes }) {
  const [showAll, setShowAll] = useState(false);

  // Edge cases: null, undefined, or empty
  if (!changes || changes.length === 0) return null;

  const visibleChanges = showAll ? changes : changes.slice(0, INITIAL_VISIBLE);
  const hiddenCount = changes.length - INITIAL_VISIBLE;
  const hasMore = changes.length > INITIAL_VISIBLE;

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 p-5">

      <h3 className="flex items-center gap-2 text-sm font-semibold text-white mb-4">
        <CheckCheck className="w-4 h-4 text-green-400" />
        Changes Applied
        <span className="text-xs font-normal text-gray-500 ml-1">
          ({changes.length} correction{changes.length !== 1 ? "s" : ""})
        </span>
      </h3>

      <ol className="space-y-2">
        {visibleChanges.map((change, i) => (
          <li key={i} className="flex items-start gap-3 group">
            <span className="shrink-0 flex items-center justify-center w-5 h-5 rounded-full bg-blue-950 border border-blue-900/60 text-blue-400 text-xs font-bold mt-0.5">
              {i + 1}
            </span>
            <span className="text-sm text-gray-400 leading-relaxed group-hover:text-gray-300 transition-colors font-mono">
              {change}
            </span>
          </li>
        ))}
      </ol>

      {hasMore && (
        <button
          onClick={() => setShowAll((s) => !s)}
          className="mt-4 flex items-center gap-1.5 text-xs text-gray-600 hover:text-gray-400 transition-colors"
        >
          {showAll ? (
            <><ChevronUp className="w-3.5 h-3.5" /> Show less</>
          ) : (
            <><ChevronDown className="w-3.5 h-3.5" /> Show {hiddenCount} more changes</>
          )}
        </button>
      )}

    </div>
  );
}
