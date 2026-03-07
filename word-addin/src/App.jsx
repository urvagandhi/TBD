import { useState, useRef, useCallback } from "react";

import JournalSelector from "./components/JournalSelector";
import FormatButton from "./components/FormatButton";
import ProgressBar from "./components/ProgressBar";
import ComplianceReport from "./components/ComplianceReport";
import ErrorBanner from "./components/ErrorBanner";

import { uploadDocument, startFormat, pollUntilDone, getResult, downloadDocx } from "./utils/api";
import { getDocumentAsBlob, getDocumentText, insertDocx, isOfficeReady } from "./utils/office";

const STATES = {
  IDLE: "idle",
  UPLOADING: "uploading",
  FORMATTING: "formatting",
  POLLING: "polling",
  RESULTS: "results",
  APPLYING: "applying",
  ERROR: "error",
};

const IconLogo = () => (
  <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
    <rect x="4" y="2" width="16" height="20" rx="3" fill="currentColor" opacity="0.15" />
    <path d="M8 7h8M8 11h8M8 15h5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const IconDownload = () => (
  <svg width="16" height="16" fill="none" viewBox="0 0 24 24">
    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <polyline points="7 10 12 15 17 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const IconCheck = () => (
  <svg width="16" height="16" fill="none" viewBox="0 0 24 24">
    <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

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

      setState(STATES.FORMATTING);
      setStage("Starting pipeline");
      setProgress(20);
      const { job_id } = await startFormat(doc_id, journal);

      setState(STATES.POLLING);
      const controller = new AbortController();
      abortRef.current = controller;

      const finalStatus = await pollUntilDone(
        job_id,
        (statusData) => {
          const p = statusData.progress || 0;
          setProgress(20 + Math.round(p * 0.7));
          setStage(statusData.step || statusData.message || "Processing");
        },
        controller.signal
      );

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
    <div style={{
      minHeight: "100vh", background: "var(--bg-soft)",
      fontFamily: "var(--font)",
      display: "flex", flexDirection: "column",
    }}>
      {/* Navbar */}
      <div style={{
        background: "rgba(255,255,255,0.9)", backdropFilter: "blur(16px)",
        borderBottom: "1px solid var(--border)",
        padding: "0 20px", height: 56,
        display: "flex", alignItems: "center", gap: 10,
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8,
          background: "linear-gradient(135deg, var(--orange), var(--orange-hover))",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 3px 10px rgba(249,115,22,0.3)",
          color: "#fff",
        }}>
          <IconLogo />
        </div>
        <div>
          <span style={{ fontSize: "0.95rem", fontWeight: 800, color: "var(--text)", letterSpacing: "-0.3px" }}>
            Agent Paperpal
          </span>
        </div>
        <div style={{
          marginLeft: "auto",
          fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.5px",
          color: "var(--orange)", background: "var(--orange-light)",
          border: "1px solid rgba(249,115,22,0.2)",
          borderRadius: "var(--radius-pill)", padding: "3px 10px",
        }}>
          WORD ADD-IN
        </div>
      </div>

      {/* Content */}
      <div style={{
        flex: 1, padding: "24px 20px",
        maxWidth: 400, margin: "0 auto", width: "100%",
      }}>
        {/* Card */}
        <div style={{
          background: "#fff", border: "1px solid var(--border)",
          borderRadius: "var(--radius)", padding: "28px 24px",
          boxShadow: "var(--shadow-lg)",
          animation: "fadeUp 0.5s ease",
        }}>
          {/* Journal selector — always visible */}
          <JournalSelector
            value={journal}
            onChange={setJournal}
            disabled={isWorking}
          />

          {/* Idle / Error — show format button */}
          {(state === STATES.IDLE || state === STATES.ERROR) && (
            <FormatButton
              onClick={handleFormat}
              disabled={!journal}
              loading={false}
            />
          )}

          {/* Error banner */}
          {state === STATES.ERROR && (
            <div style={{ marginTop: 16 }}>
              <ErrorBanner message={error} onRetry={reset} />
            </div>
          )}
        </div>

        {/* Working states — progress card */}
        {isWorking && (
          <div style={{ marginTop: 16 }}>
            <ProgressBar progress={progress} stage={stage} />
            <button
              onClick={reset}
              style={{
                display: "block", margin: "12px auto 0",
                background: "transparent", border: "none",
                fontSize: "0.8rem", fontWeight: 500,
                color: "var(--text-muted)", cursor: "pointer",
                fontFamily: "var(--font)",
                transition: "color 0.2s",
              }}
              onMouseEnter={(e) => e.target.style.color = "var(--text)"}
              onMouseLeave={(e) => e.target.style.color = "var(--text-muted)"}
            >
              Cancel
            </button>
          </div>
        )}

        {/* Results */}
        {state === STATES.RESULTS && (
          <div style={{ marginTop: 16, animation: "fadeUp 0.5s ease" }}>
            {/* Score card */}
            <div style={{
              background: "#fff", border: "1px solid var(--border)",
              borderRadius: "var(--radius)", padding: "28px 24px",
              boxShadow: "var(--shadow-lg)",
            }}>
              <ComplianceReport report={complianceReport} />
            </div>

            {/* Action buttons */}
            <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Apply to Document */}
              {isOfficeReady() && !applied && (
                <button
                  onClick={handleApply}
                  style={{
                    width: "100%", padding: "13px",
                    background: "linear-gradient(135deg, var(--success), #059669)",
                    color: "#fff", border: "none",
                    borderRadius: "var(--radius-sm)",
                    fontSize: "0.92rem", fontWeight: 700,
                    fontFamily: "var(--font)", cursor: "pointer",
                    boxShadow: "0 6px 20px rgba(16,185,129,0.3)",
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                    transition: "transform 0.2s, box-shadow 0.2s",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.transform = "translateY(-2px)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = "translateY(0)"; }}
                >
                  <IconCheck />
                  Apply to Document
                </button>
              )}

              {/* Success message */}
              {applied && (
                <div style={{
                  background: "var(--success-bg)",
                  border: "1px solid rgba(16,185,129,0.25)",
                  borderRadius: "var(--radius-sm)", padding: "12px 16px",
                  textAlign: "center", animation: "fadeUp 0.3s ease",
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                    <div style={{ color: "var(--success)" }}><IconCheck /></div>
                    <span style={{ fontSize: "0.88rem", fontWeight: 600, color: "var(--success)" }}>
                      Document updated successfully!
                    </span>
                  </div>
                </div>
              )}

              {/* Download DOCX */}
              <button
                onClick={handleDownload}
                style={{
                  width: "100%", padding: "13px",
                  background: "linear-gradient(135deg, var(--orange), #EA6C0A)",
                  color: "#fff", border: "none",
                  borderRadius: "var(--radius-pill)",
                  fontSize: "0.92rem", fontWeight: 700,
                  fontFamily: "var(--font)", cursor: "pointer",
                  boxShadow: "0 6px 20px rgba(249,115,22,0.3)",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                  transition: "transform 0.2s, box-shadow 0.2s",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 10px 28px rgba(249,115,22,0.4)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = "0 6px 20px rgba(249,115,22,0.3)"; }}
              >
                <IconDownload />
                Download DOCX
              </button>

              {/* Format Again */}
              <button
                onClick={reset}
                style={{
                  width: "100%", padding: "11px",
                  background: "var(--bg-muted)", color: "var(--text-secondary)",
                  border: "1.5px solid var(--border)",
                  borderRadius: "var(--radius-pill)",
                  fontSize: "0.88rem", fontWeight: 600,
                  fontFamily: "var(--font)", cursor: "pointer",
                  transition: "background 0.2s, color 0.2s, border-color 0.2s",
                }}
                onMouseEnter={(e) => { e.target.style.borderColor = "var(--orange)"; e.target.style.color = "var(--orange)"; e.target.style.background = "var(--orange-light)"; }}
                onMouseLeave={(e) => { e.target.style.borderColor = "var(--border)"; e.target.style.color = "var(--text-secondary)"; e.target.style.background = "var(--bg-muted)"; }}
              >
                Format Another Paper
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        borderTop: "1px solid var(--border)",
        padding: "12px 20px", textAlign: "center",
        fontSize: "0.7rem", fontWeight: 500,
        color: "var(--text-muted)",
      }}>
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
