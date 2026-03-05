import { useState, useEffect } from "react";
import axios from "axios";
import { Download, RotateCcw, Zap, CheckCircle, XCircle, Sun, Moon } from "lucide-react";
import Upload from "./components/Upload.jsx";
import ComplianceScore from "./components/ComplianceScore.jsx";
import ChangesList from "./components/ChangesList.jsx";

const PIPELINE_STEPS = [
  "Ingesting document content...",
  "Parsing paper structure...",
  "Loading journal rules...",
  "Applying formatting fixes...",
  "Validating compliance...",
];

function PipelineProgress({ currentStep }) {
  return (
    <div className="space-y-5">
      <div className="flex justify-center">
        <div className="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
      <div className="space-y-3">
        {PIPELINE_STEPS.map((step, i) => (
          <div
            key={i}
            className={`flex items-center gap-3 text-sm transition-all duration-300
              ${i < currentStep
                ? "text-green-600 dark:text-green-400"
                : i === currentStep
                ? "text-blue-600 dark:text-blue-400"
                : "text-gray-400 dark:text-gray-700"}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full shrink-0
              ${i < currentStep
                ? "bg-green-600 dark:bg-green-400"
                : i === currentStep
                ? "bg-blue-600 dark:bg-blue-400 animate-pulse"
                : "bg-gray-300 dark:bg-gray-800"}`}
            />
            {step}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [state, setState] = useState("idle"); // idle | loading | success | error
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [pipelineStep, setPipelineStep] = useState(0);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [processingTime, setProcessingTime] = useState(null);
  const [isDark, setIsDark] = useState(true);

  // Apply dark class to <html> for Tailwind dark: variants
  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  // Simulate pipeline progress during loading
  useEffect(() => {
    if (state !== "loading") return;
    setPipelineStep(0);
    const interval = setInterval(() => {
      setPipelineStep((s) => (s < PIPELINE_STEPS.length - 1 ? s + 1 : s));
    }, 9000);
    return () => clearInterval(interval);
  }, [state]);

  async function handleFormat(file, journal) {
    setState("loading");
    setErrorMsg("");
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("journal", journal);

    try {
      const response = await axios.post("/format", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 0,
      });

      const data = response.data;
      setResult(data.compliance_report);
      setDownloadUrl(data.download_url);
      setProcessingTime(data.processing_time_seconds);
      setState("success");
    } catch (err) {
      const detail =
        err.response?.data?.detail ||
        err.message ||
        "Unknown error occurred.";
      setErrorMsg(detail);
      setState("error");
    }
  }

  function handleReset() {
    setState("idle");
    setResult(null);
    setErrorMsg("");
    setDownloadUrl("");
    setProcessingTime(null);
    setPipelineStep(0);
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100 transition-colors duration-200">
      {/* Header */}
      <header className="border-b border-gray-200 dark:border-gray-800/60 bg-white/80 dark:bg-gray-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-gray-900 dark:text-white tracking-tight">Agent Paperpal</h1>
              <p className="text-xs text-gray-500">Autonomous Manuscript Formatter</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 dark:text-gray-600">HackaMined 2026</span>
            <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800/40">
              AI-Powered
            </span>
            <button
              onClick={() => setIsDark((d) => !d)}
              className="ml-1 p-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
              aria-label="Toggle theme"
            >
              {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        {/* IDLE — Upload form */}
        {state === "idle" && (
          <div className="max-w-xl mx-auto animate-fade-in">
            <div className="text-center mb-10">
              <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-3">
                Format Your Manuscript
              </h2>
              <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md mx-auto leading-relaxed">
                Upload your research paper and select a journal style.
                Our 5-agent AI pipeline will autonomously detect, fix, and validate
                every formatting requirement.
              </p>
            </div>
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-6 shadow-sm dark:shadow-2xl dark:shadow-black/30">
              <Upload onSubmit={handleFormat} isLoading={false} />
            </div>

            {/* Journal badges */}
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {["APA 7th Edition", "IEEE", "Vancouver", "Springer", "Chicago"].map((j) => (
                <span key={j} className="px-2.5 py-1 text-xs rounded-full bg-gray-100 dark:bg-gray-900 text-gray-500 border border-gray-200 dark:border-gray-800">
                  {j}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* LOADING — Pipeline progress */}
        {state === "loading" && (
          <div className="max-w-sm mx-auto animate-fade-in">
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 p-8 shadow-sm dark:shadow-2xl dark:shadow-black/30 text-center space-y-6">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">Formatting in progress</h2>
                <p className="text-xs text-gray-500">This typically takes 45–90 seconds</p>
              </div>
              <PipelineProgress currentStep={pipelineStep} />
            </div>
          </div>
        )}

        {/* SUCCESS — Results */}
        {state === "success" && result && (
          <div className="animate-fade-in space-y-6">
            {/* Top bar */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
                <div>
                  <h2 className="text-base font-semibold text-gray-900 dark:text-white">Formatting complete</h2>
                  {processingTime && (
                    <p className="text-xs text-gray-500">Processed in {processingTime}s</p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleReset}
                  className="flex items-center gap-2 px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-800 rounded-xl transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  New document
                </button>
                {downloadUrl && (
                  <a
                    href={downloadUrl}
                    download
                    className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 rounded-xl transition-colors shadow-lg shadow-blue-900/30"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Download DOCX
                  </a>
                )}
              </div>
            </div>

            {/* Two-column layout */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <ComplianceScore report={result} />
              <ChangesList changes={result.changes_made || []} />
            </div>
          </div>
        )}

        {/* ERROR */}
        {state === "error" && (
          <div className="max-w-md mx-auto animate-fade-in">
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-red-200 dark:border-red-900/40 p-8 text-center space-y-4">
              <XCircle className="w-12 h-12 text-red-500 dark:text-red-400 mx-auto" />
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Formatting failed</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 break-words">{errorMsg}</p>
              </div>
              <button
                onClick={handleReset}
                className="w-full py-3 rounded-xl bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-sm text-gray-700 dark:text-gray-300 transition-colors"
              >
                Try again
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 dark:border-gray-800/40 mt-20 py-6 text-center text-xs text-gray-400 dark:text-gray-700">
        Agent Paperpal · HackaMined 2026 · Cactus Communications Track
      </footer>
    </div>
  );
}
