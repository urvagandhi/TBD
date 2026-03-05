import { useState, useEffect } from "react";
import { CheckCircle, AlertCircle, XCircle, ChevronDown, ChevronUp } from "lucide-react";

// Fixed section display order — always shown even if missing from API
const SECTION_ORDER = [
  { key: "document_format", label: "Document Format" },
  { key: "abstract",        label: "Abstract" },
  { key: "headings",        label: "Headings" },
  { key: "citations",       label: "Citations" },
  { key: "references",      label: "References" },
  { key: "figures",         label: "Figures" },
  { key: "tables",          label: "Tables" },
];

const MAX_VISIBLE_ISSUES = 3;

function getScoreColors(score) {
  if (score >= 90) return { text: "text-green-400", bg: "bg-green-500", ring: "ring-green-500/20" };
  if (score >= 70) return { text: "text-yellow-400", bg: "bg-yellow-500", ring: "ring-yellow-500/20" };
  return { text: "text-red-400", bg: "bg-red-500", ring: "ring-red-500/20" };
}

function getScoreIcon(score) {
  if (score >= 90) return <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />;
  if (score >= 70) return <AlertCircle className="w-4 h-4 text-yellow-400 shrink-0" />;
  return <XCircle className="w-4 h-4 text-red-400 shrink-0" />;
}

// Animated bar — transitions from 0 → score on mount
function AnimatedBar({ score, colorClass }) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setWidth(score), 80);
    return () => clearTimeout(t);
  }, [score]);
  return (
    <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-700 ${colorClass}`}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

// Section row with collapsible issues (collapse after MAX_VISIBLE_ISSUES)
function SectionRow({ label, score, issues }) {
  const [showAll, setShowAll] = useState(false);
  const colors = getScoreColors(score ?? 0);
  const hasIssues = issues && issues.length > 0;
  const visibleIssues = showAll ? issues : issues.slice(0, MAX_VISIBLE_ISSUES);
  const hiddenCount = issues.length - MAX_VISIBLE_ISSUES;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        {getScoreIcon(score ?? 0)}
        <span className="text-sm text-gray-300 flex-1">{label}</span>
        <span className={`text-xs font-semibold tabular-nums ${typeof score === "number" ? colors.text : "text-gray-600"}`}>
          {typeof score === "number" ? `${score}/100` : "N/A"}
        </span>
      </div>
      {typeof score === "number" && (
        <AnimatedBar score={score} colorClass={colors.bg} />
      )}
      {hasIssues && (
        <div className="pl-6 space-y-0.5">
          {visibleIssues.map((issue, i) => (
            <p key={i} className="text-xs text-yellow-600 flex items-start gap-1">
              <span className="shrink-0 mt-0.5">·</span>
              <span>{issue}</span>
            </p>
          ))}
          {issues.length > MAX_VISIBLE_ISSUES && (
            <button
              onClick={() => setShowAll((s) => !s)}
              className="flex items-center gap-1 text-xs text-gray-600 hover:text-gray-400 transition-colors mt-1"
            >
              {showAll ? (
                <><ChevronUp className="w-3 h-3" /> Show less</>
              ) : (
                <><ChevronDown className="w-3 h-3" /> Show {hiddenCount} more</>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function SkeletonRow() {
  return (
    <div className="space-y-1.5 animate-pulse">
      <div className="flex items-center gap-2">
        <div className="w-4 h-4 rounded-full bg-gray-800" />
        <div className="h-3 bg-gray-800 rounded flex-1" />
        <div className="w-12 h-3 bg-gray-800 rounded" />
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full" />
    </div>
  );
}

export default function ComplianceScore({ report }) {
  const [overallWidth, setOverallWidth] = useState(0);

  const overallScore = report?.overall_score ?? 0;
  const breakdown = report?.breakdown ?? {};
  const submissionReady = report?.submission_ready;
  const overallColors = getScoreColors(overallScore);

  useEffect(() => {
    if (!report) return;
    const t = setTimeout(() => setOverallWidth(overallScore), 100);
    return () => clearTimeout(t);
  }, [overallScore, report]);

  const scoreLabel =
    overallScore === 100 ? "Perfect!" :
    overallScore >= 90 ? "Excellent compliance" :
    overallScore >= 70 ? "Good — minor issues remain" :
    "Needs improvement";

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6 space-y-5">

      {/* Header row */}
      <div className="flex items-start justify-between">
        <h2 className="text-base font-semibold text-white">Compliance Score</h2>
        {report ? (
          <div className="text-right">
            <div className={`text-3xl font-bold tabular-nums ${overallColors.text}`}>
              {overallScore}
              <span className="text-lg text-gray-600">/100</span>
            </div>
            <div className="text-xs text-gray-500 mt-0.5">{scoreLabel}</div>
          </div>
        ) : (
          <div className="w-20 h-8 bg-gray-800 rounded animate-pulse" />
        )}
      </div>

      {/* Overall progress bar */}
      {report ? (
        <div className="w-full bg-gray-800 rounded-full h-2.5 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${overallColors.bg}`}
            style={{ width: `${overallWidth}%` }}
          />
        </div>
      ) : (
        <div className="h-2.5 bg-gray-800 rounded-full animate-pulse" />
      )}

      {/* Submission ready banner */}
      {report && typeof submissionReady === "boolean" && (
        <div className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-sm font-medium ${
          submissionReady
            ? "bg-green-950/40 border-green-800/50 text-green-400"
            : "bg-yellow-950/30 border-yellow-800/30 text-yellow-500"
        }`}>
          {submissionReady ? (
            <><CheckCircle className="w-4 h-4 shrink-0" /> Submission Ready — score meets 80+ threshold</>
          ) : (
            <><AlertCircle className="w-4 h-4 shrink-0" /> Not yet submission ready — resolve issues to reach 80+</>
          )}
        </div>
      )}

      {/* Section breakdown — fixed 7-section order */}
      <div className="space-y-4 pt-2 border-t border-gray-800">
        <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wider">Section Breakdown</h3>
        {report ? (
          SECTION_ORDER.map(({ key, label }) => {
            const val = breakdown[key];
            return (
              <SectionRow
                key={key}
                label={label}
                score={val?.score}
                issues={val?.issues || []}
              />
            );
          })
        ) : (
          SECTION_ORDER.map(({ key }) => <SkeletonRow key={key} />)
        )}
      </div>

      {/* Citation consistency */}
      {report?.citation_consistency && (() => {
        const { orphan_citations = [], uncited_references = [] } = report.citation_consistency;
        if (!orphan_citations.length && !uncited_references.length) return null;
        return (
          <div className="space-y-3 pt-2 border-t border-gray-800">
            <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wider">Citation Consistency</h3>
            {orphan_citations.length > 0 && (
              <div>
                <p className="text-xs text-yellow-600 font-medium mb-1">Orphan citations</p>
                <ul className="space-y-0.5">
                  {orphan_citations.map((c, i) => <li key={i} className="text-xs text-gray-500">· {c}</li>)}
                </ul>
              </div>
            )}
            {uncited_references.length > 0 && (
              <div>
                <p className="text-xs text-yellow-600 font-medium mb-1">Uncited references</p>
                <ul className="space-y-0.5">
                  {uncited_references.map((r, i) => <li key={i} className="text-xs text-gray-500">· {r}</li>)}
                </ul>
              </div>
            )}
          </div>
        );
      })()}

      {/* Warnings */}
      {report?.warnings?.length > 0 && (
        <div className="bg-yellow-950/20 border border-yellow-900/30 rounded-xl p-4 space-y-2">
          <h3 className="flex items-center gap-2 text-xs font-semibold text-yellow-500 uppercase tracking-wider">
            <AlertCircle className="w-3.5 h-3.5" />
            Warnings
          </h3>
          <ul className="space-y-1">
            {report.warnings.map((w, i) => (
              <li key={i} className="text-xs text-yellow-600/80">· {w}</li>
            ))}
          </ul>
        </div>
      )}

    </div>
  );
}
