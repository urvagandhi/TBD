import { useState, useEffect } from "react";
import { FileText, Search, BookOpen, Wrench, CheckSquare, CheckCircle, Clock } from "lucide-react";

const PIPELINE_STEPS = [
  {
    id: 0,
    label: "Reading document",
    sublabel: "Extracting text from your PDF/DOCX",
    Icon: FileText,
    duration: 10,
  },
  {
    id: 1,
    label: "Detecting structure",
    sublabel: "Identifying title, abstract, sections, citations",
    Icon: Search,
    duration: 12,
  },
  {
    id: 2,
    label: "Loading journal rules",
    sublabel: "Fetching formatting requirements",
    Icon: BookOpen,
    duration: 3,
  },
  {
    id: 3,
    label: "Applying formatting",
    sublabel: "Fixing fonts, headings, citations, references",
    Icon: Wrench,
    duration: 18,
  },
  {
    id: 4,
    label: "Validating compliance",
    sublabel: "Running 7 quality checks, generating score",
    Icon: CheckSquare,
    duration: 12,
  },
];

const TOTAL_STEPS = PIPELINE_STEPS.length - 1; // 0-indexed max

export default function ProcessingLoader({ currentStep, journal, filename }) {
  const [elapsed, setElapsed] = useState(0);

  // Elapsed timer — cleared on unmount
  useEffect(() => {
    const timer = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const elapsedStr = `${minutes}:${String(seconds).padStart(2, "0")}`;

  const progressPct = Math.round((currentStep / TOTAL_STEPS) * 100);
  const showLongWaitMsg = elapsed >= 60;

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 p-8 space-y-7">

      {/* Top — spinner + title */}
      <div className="text-center space-y-3">
        <div className="flex justify-center">
          <div className="w-12 h-12 rounded-full border-2 border-gray-700 border-t-blue-400 animate-spin" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">Formatting your paper...</h2>
          {journal && (
            <p className="text-sm text-gray-500 mt-1">Applying <span className="text-blue-400">{journal}</span> rules</p>
          )}
          {filename && (
            <p className="text-xs text-gray-700 mt-0.5 font-mono truncate max-w-xs mx-auto">{filename}</p>
          )}
        </div>
      </div>

      {/* Pipeline steps */}
      <div className="space-y-3">
        {PIPELINE_STEPS.map((step) => {
          const status =
            step.id < currentStep ? "done"
            : step.id === currentStep ? "active"
            : "pending";

          const { Icon } = step;

          return (
            <div
              key={step.id}
              className={`
                flex items-start gap-3 rounded-xl px-4 py-3 transition-all duration-300
                ${status === "active" ? "bg-blue-950/30 border border-blue-900/40" : "bg-transparent"}
              `}
            >
              {/* Status indicator */}
              <div className="shrink-0 mt-0.5">
                {status === "done" ? (
                  <CheckCircle className="w-4 h-4 text-green-500" />
                ) : status === "active" ? (
                  <div className="w-4 h-4 rounded-full border-2 border-blue-400 border-t-transparent animate-spin" />
                ) : (
                  <div className="w-4 h-4 rounded-full border border-gray-700 bg-gray-800" />
                )}
              </div>

              {/* Step icon */}
              <Icon
                className={`w-4 h-4 shrink-0 mt-0.5 ${
                  status === "done" ? "text-green-500"
                  : status === "active" ? "text-blue-400"
                  : "text-gray-700"
                }`}
              />

              {/* Labels */}
              <div className="min-w-0">
                <p className={`text-sm font-medium ${
                  status === "done" ? "text-gray-400"
                  : status === "active" ? "text-white"
                  : "text-gray-700"
                }`}>
                  {step.label}
                </p>
                {status === "active" && (
                  <p className="text-xs text-gray-500 mt-0.5">{step.sublabel}</p>
                )}
              </div>

              {/* Done badge */}
              {status === "done" && (
                <span className="ml-auto text-xs text-green-700 shrink-0">done</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="space-y-1.5">
        <div className="w-full bg-gray-800 rounded-full h-1.5">
          <div
            className="h-1.5 rounded-full bg-blue-500 transition-all duration-700"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-xs text-gray-700">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {elapsedStr} elapsed
          </span>
          <span>{progressPct}%</span>
        </div>
      </div>

      {/* Footer message */}
      <p className={`text-center text-xs transition-colors duration-500 ${showLongWaitMsg ? "text-yellow-600" : "text-gray-700"}`}>
        {showLongWaitMsg
          ? "Taking longer than usual. Large papers require more time..."
          : "This typically takes 40–60 seconds. Please wait..."}
      </p>

    </div>
  );
}
