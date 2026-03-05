import { useState, useEffect } from "react";
import axios from "axios";
import { Zap, Download, RotateCcw, CheckCircle } from "lucide-react";
import Upload from "./components/Upload.jsx";
import ProcessingLoader from "./components/ProcessingLoader.jsx";
import ComplianceScore from "./components/ComplianceScore.jsx";
import ChangesList from "./components/ChangesList.jsx";
import IMRADCheck from "./components/IMRADCheck.jsx";

// Vite proxy handles /health, /format, /download → backend at localhost:8000
const FORMAT_TIMEOUT_MS = 0; // 0 = no timeout — pipeline can take as long as needed

const FALLBACK_JOURNALS = [
  "APA 7th Edition",
  "IEEE",
  "Vancouver",
  "Springer",
  "Chicago 17th Edition",
];

// Apply dark class permanently — ui-ux-agent mandates always-dark theme
if (typeof document !== "undefined") {
  document.documentElement.classList.add("dark");
}

export default function App() {
  const [appState, setAppState] = useState("idle"); // idle | loading | success | error
  const [file, setFile] = useState(null);
  const [journal, setJournal] = useState("");
  const [journals, setJournals] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null); // { message, code, step }
  const [loadingStep, setLoadingStep] = useState(0);

  // Fetch supported journals from /health on mount; fallback on failure
  useEffect(() => {
    const fetchJournals = async () => {
      try {
        const res = await axios.get("/health", { timeout: 5000 });
        setJournals(res.data.supported_journals || FALLBACK_JOURNALS);
      } catch {
        setJournals(FALLBACK_JOURNALS);
      }
    };
    fetchJournals();
  }, []);

  const handleFormat = async () => {
    if (!file || !journal) return;

    setAppState("loading");
    setLoadingStep(0);
    setError(null);
    setResult(null);

    // Advance step indicator per approximate pipeline timings
    // Ingest=10s, Parse=10s, Interpret=2s, Transform=15s, Validate=10s
    const stepTimings = [10000, 10000, 2000, 15000, 10000];
    let stepIndex = 0;
    const stepInterval = setInterval(() => {
      stepIndex++;
      if (stepIndex < 5) {
        setLoadingStep(stepIndex);
      } else {
        clearInterval(stepInterval);
      }
    }, stepTimings[stepIndex] || 10000);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("journal", journal);

      const response = await axios.post("/format", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: FORMAT_TIMEOUT_MS,
      });

      clearInterval(stepInterval);
      setResult(response.data);
      setAppState("success");
    } catch (err) {
      clearInterval(stepInterval);

      let errorObj = {
        message: "An unexpected error occurred. Please try again.",
        code: "unknown_error",
        step: null,
      };

      if (
        err.code === "ERR_NETWORK" ||
        err.message === "Network Error" ||
        err.response?.status === 502 ||
        err.response?.status === 503
      ) {
        // 502/503 = Vite proxy couldn't reach backend (ECONNREFUSED)
        errorObj = {
          message: "Cannot connect to the backend server. Make sure it is running on port 8000.",
          code: "network_error",
          step: null,
        };
      } else if (err.response) {
        const detail = err.response.data?.detail || err.response.data;
        if (typeof detail === "object" && detail !== null) {
          errorObj = {
            message: detail.error || detail.message || "Processing failed.",
            code: `http_${err.response.status}`,
            step: detail.step || null,
          };
        } else {
          errorObj = {
            message: String(detail),
            code: `http_${err.response.status}`,
            step: null,
          };
        }
      }

      setError(errorObj);
      setAppState("error");
    }
  };

  const handleReset = () => {
    setAppState("idle");
    setFile(null);
    setJournal("");
    setResult(null);
    setError(null);
    setLoadingStep(0);
  };

  const handleDownload = () => {
    if (!result?.download_url) return;
    // Vite proxy forwards /download/* to backend
    window.open(result.download_url, "_blank");
  };

  const compliance_report = result?.compliance_report;
  const changes_made = result?.changes_made || compliance_report?.changes_made || [];

  return (
    <div className="min-h-screen bg-gray-950 text-white">

      {/* Header — always visible */}
      <header className="border-b border-gray-800 bg-gray-950/90 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shrink-0">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <div>
              <div className="text-sm font-bold text-white tracking-tight">Agent Paperpal</div>
              <div className="text-xs text-gray-500 font-mono">HackaMined 2026 · Cactus Communications</div>
            </div>
          </div>

          {appState === "success" && result?.processing_time_seconds && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-green-950 border border-green-800 text-green-400 text-xs font-semibold">
              <CheckCircle className="w-3.5 h-3.5" />
              Formatted in {result.processing_time_seconds}s
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-6 py-10">

        {/* IDLE — Upload form */}
        {appState === "idle" && (
          <div className="max-w-xl mx-auto animate-fade-in">
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold text-white mb-2">Format Your Manuscript</h1>
              <p className="text-gray-400 text-sm leading-relaxed max-w-md mx-auto">
                Upload a research paper and select a journal style.
                Our 5-agent AI pipeline autonomously detects, fixes, and validates
                every formatting requirement.
              </p>
            </div>
            <div className="bg-gray-900 rounded-2xl border border-gray-800 p-6">
              <Upload
                file={file}
                setFile={setFile}
                journal={journal}
                setJournal={setJournal}
                journals={journals}
                onSubmit={handleFormat}
              />
            </div>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {(journals.length > 0 ? journals : FALLBACK_JOURNALS).map((j) => (
                <span
                  key={j}
                  className="px-2.5 py-1 text-xs rounded-full bg-gray-900 text-gray-500 border border-gray-800"
                >
                  {j}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* LOADING — Pipeline progress */}
        {appState === "loading" && (
          <div className="max-w-lg mx-auto animate-fade-in">
            <ProcessingLoader
              currentStep={loadingStep}
              journal={journal}
              filename={file?.name}
            />
          </div>
        )}

        {/* ERROR */}
        {appState === "error" && (
          <div className="max-w-md mx-auto animate-fade-in">
            <ErrorDisplay error={error} onRetry={handleReset} />
          </div>
        )}

        {/* SUCCESS */}
        {appState === "success" && result && (
          <div className="animate-fade-in space-y-5">
            <SuccessView
              result={result}
              complianceReport={compliance_report}
              changesMade={changes_made}
              onDownload={handleDownload}
              onReset={handleReset}
            />
          </div>
        )}

      </main>

      <footer className="border-t border-gray-800 mt-20 py-6 text-center text-xs text-gray-700">
        Agent Paperpal · HackaMined 2026 · Cactus Communications Track
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ErrorDisplay — inline, one-off component
// ---------------------------------------------------------------------------
function ErrorDisplay({ error, onRetry }) {
  return (
    <div className="bg-gray-900 rounded-2xl border border-red-900/40 p-8 text-center space-y-4">
      <div className="w-14 h-14 rounded-full bg-red-950 border border-red-900/60 flex items-center justify-center mx-auto">
        <span className="text-red-400 text-2xl font-bold select-none">!</span>
      </div>
      <div>
        <h2 className="text-lg font-semibold text-white mb-3">Processing Failed</h2>
        <div className="bg-red-950/40 border border-red-900/40 rounded-xl px-4 py-3 text-sm text-red-300 leading-relaxed text-left">
          {error?.message || "An unexpected error occurred."}
          {error?.step && (
            <div className="mt-2 text-xs text-red-500 font-mono">
              Failed at step: {error.step}
            </div>
          )}
        </div>
      </div>
      <button
        onClick={onRetry}
        className="px-8 py-3 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-semibold transition-colors"
      >
        Try Again
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SuccessView — inline, one-off component
// ---------------------------------------------------------------------------
function SuccessView({ result, complianceReport, changesMade, onDownload, onReset }) {
  return (
    <>
      {/* Download Banner */}
      <div className="bg-green-950/50 border border-green-800/60 rounded-2xl p-5 flex items-center justify-between flex-wrap gap-4">
        <div>
          <div className="text-base font-bold text-green-400 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 shrink-0" />
            Paper Formatted Successfully
          </div>
          <div className="text-sm text-green-600 mt-1">
            Reformatted to comply with journal standards.
          </div>
        </div>
        <div className="flex gap-3 flex-wrap">
          <button
            onClick={onDownload}
            className="flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-500 text-black text-sm font-bold rounded-xl transition-colors"
          >
            <Download className="w-4 h-4" />
            Download .docx
          </button>
          <button
            onClick={onReset}
            className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-xl transition-colors border border-gray-700"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Format Another
          </button>
        </div>
      </div>

      {/* Compliance Score Dashboard */}
      <ComplianceScore report={complianceReport} />

      {/* IMRAD Structure Check */}
      {complianceReport?.imrad_check && (
        <IMRADCheck imrad={complianceReport.imrad_check} />
      )}

      {/* Changes Applied */}
      {changesMade?.length > 0 && (
        <ChangesList changes={changesMade} />
      )}

      {/* Recommendations */}
      {complianceReport?.recommendations?.length > 0 && (
        <RecommendationsCard recs={complianceReport.recommendations} />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// RecommendationsCard — inline, one-off component
// ---------------------------------------------------------------------------
function RecommendationsCard({ recs }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5">
      <h3 className="text-sm font-semibold text-yellow-500 mb-3">Recommendations</h3>
      <ul className="space-y-2">
        {recs.map((rec, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-gray-400">
            <span className="text-yellow-500 shrink-0 mt-0.5">→</span>
            <span>{rec}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
