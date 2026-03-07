import { useState, useRef, useCallback } from "react";

import JournalSelector from "./components/JournalSelector";
import FormatButton from "./components/FormatButton";
import ProgressBar from "./components/ProgressBar";
import ComplianceReport from "./components/ComplianceReport";
import ErrorBanner from "./components/ErrorBanner";

import { uploadDocument, startFormat, pollUntilDone, getResult, downloadDocx } from "./utils/api";
import { getDocumentAsBlob, getDocumentText, insertDocx, isOfficeReady } from "./utils/office";

// IDLE → UPLOADING → FORMATTING → POLLING → RESULTS
// Any stage can → ERROR → IDLE
const STATES = {
  IDLE: "idle",
  UPLOADING: "uploading",
  FORMATTING: "formatting",
  POLLING: "polling",
  RESULTS: "results",
  APPLYING: "applying",
  ERROR: "error",
};

export default function App() {
  const [journal, setJournal] = useState("");
  const [state, setState] = useState(STATES.IDLE);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [applied, setApplied] = useState(false);

  const abortRef = useRef(null);

  const reset = useCallback(() => {
    setState(STATES.IDLE);
    setProgress(0);
    setStage("");
    setResult(null);
    setError("");
    setApplied(false);
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const handleFormat = useCallback(async () => {
    if (!journal) {
      setError("Please select a journal style.");
      setState(STATES.ERROR);
      return;
    }

    const officeAvailable = isOfficeReady();

    try {
      // --- Upload ---
      setState(STATES.UPLOADING);
      setProgress(0);
      setStage("Reading document");

      let blob;
      if (officeAvailable) {
        const text = await getDocumentText();
        if (!text || text.trim().length < 100) {
          throw new Error("Document is too short (minimum 100 characters). Please add more content.");
        }
        blob = await getDocumentAsBlob();
      } else {
        throw new Error(
          "Office.js is not available. Please open this add-in inside Microsoft Word."
        );
      }

      setStage("Uploading");
      setProgress(10);
      const { doc_id } = await uploadDocument(blob, "document.docx");

      // --- Start format ---
      setState(STATES.FORMATTING);
      setStage("Starting pipeline");
      setProgress(20);
      const { job_id } = await startFormat(doc_id, journal);

      // --- Poll ---
      setState(STATES.POLLING);
      const controller = new AbortController();
      abortRef.current = controller;

      const finalStatus = await pollUntilDone(
        job_id,
        (statusData) => {
          const p = statusData.progress || 0;
          setProgress(20 + Math.round(p * 0.7)); // 20-90%
          setStage(statusData.step || statusData.message || "Processing");
        },
        controller.signal
      );

      // --- Get results ---
      setProgress(95);
      setStage("Fetching results");

      let fullResult;
      if (finalStatus.result) {
        fullResult = finalStatus.result;
      } else {
        fullResult = await getResult(job_id);
      }

      setResult(fullResult);
      setProgress(100);
      setState(STATES.RESULTS);
    } catch (err) {
      if (err.message === "Cancelled") return;
      console.error("Format error:", err);
      setError(
        err.response?.data?.detail ||
        err.response?.data?.error ||
        err.message ||
        "Something went wrong"
      );
      setState(STATES.ERROR);
    }
  }, [journal]);

  const handleApply = useCallback(async () => {
    if (!result) return;

    try {
      setState(STATES.APPLYING);
      const downloadUrl =
        result.download_url || result.download_path || result.formatted_file;

      if (!downloadUrl) {
        throw new Error("No formatted file available to download.");
      }

      const buffer = await downloadDocx(downloadUrl);
      const base64 = arrayBufferToBase64(buffer);
      const success = await insertDocx(base64);

      if (success) {
        setApplied(true);
        setState(STATES.RESULTS);
      } else {
        throw new Error("Could not insert into document. Try downloading instead.");
      }
    } catch (err) {
      console.error("Apply error:", err);
      setError(err.message);
      setState(STATES.ERROR);
    }
  }, [result]);

  const handleDownload = useCallback(async () => {
    if (!result) return;

    try {
      const downloadUrl =
        result.download_url || result.download_path || result.formatted_file;
      if (!downloadUrl) return;

      const buffer = await downloadDocx(downloadUrl);
      const blob = new Blob([buffer], {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "formatted_paper.docx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download error:", err);
      setError(err.message);
      setState(STATES.ERROR);
    }
  }, [result]);

  const isWorking =
    state === STATES.UPLOADING ||
    state === STATES.FORMATTING ||
    state === STATES.POLLING ||
    state === STATES.APPLYING;

  const complianceReport =
    result?.compliance_report || result?.result?.compliance_report || null;

  return (
    <div className="flex min-h-screen flex-col bg-gray-950 p-4 text-gray-100">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-lg font-bold text-white">Agent Paperpal</h1>
        <p className="text-xs text-gray-400">
          Format your manuscript to any journal style
        </p>
      </div>

      <div className="flex flex-1 flex-col gap-4">
        {/* Journal selector — always visible */}
        <JournalSelector
          value={journal}
          onChange={setJournal}
          disabled={isWorking}
        />

        {/* Idle state — show format button */}
        {(state === STATES.IDLE || state === STATES.ERROR) && (
          <FormatButton
            onClick={handleFormat}
            disabled={!journal}
            loading={false}
          />
        )}

        {/* Working states — show progress */}
        {isWorking && (
          <>
            <ProgressBar progress={progress} stage={stage} />
            <button
              onClick={reset}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              Cancel
            </button>
          </>
        )}

        {/* Error */}
        {state === STATES.ERROR && (
          <ErrorBanner message={error} onRetry={reset} />
        )}

        {/* Results */}
        {state === STATES.RESULTS && (
          <div className="space-y-4">
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
              <ComplianceReport report={complianceReport} />
            </div>

            {/* Action buttons */}
            <div className="space-y-2">
              {isOfficeReady() && !applied && (
                <button
                  onClick={handleApply}
                  className="w-full rounded-lg bg-green-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-green-500"
                >
                  Apply to Document
                </button>
              )}

              {applied && (
                <div className="rounded-lg border border-green-800 bg-green-950/50 p-3 text-center text-sm text-green-300">
                  Document updated successfully!
                </div>
              )}

              <button
                onClick={handleDownload}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm font-medium text-gray-200 transition hover:bg-gray-700"
              >
                Download DOCX
              </button>

              <button
                onClick={reset}
                className="w-full text-xs text-gray-500 hover:text-gray-300"
              >
                Format Again
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="mt-6 border-t border-gray-800 pt-3 text-center text-[10px] text-gray-600">
        HackaMined 2026 &middot; Cactus Communications
      </div>
    </div>
  );
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}
