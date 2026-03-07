import axios from "axios";

// In dev, Vite proxy rewrites /api/* → http://localhost:8000/*
// In production, set VITE_BACKEND_URL to the real backend.
const BASE = import.meta.env.VITE_BACKEND_URL || "/api";

const http = axios.create({ baseURL: BASE, timeout: 30000 });

/**
 * Upload a DOCX blob to the backend.
 * @param {Blob} blob - The document file.
 * @param {string} filename - Original filename.
 * @returns {{ doc_id: string }}
 */
export async function uploadDocument(blob, filename) {
  const form = new FormData();
  form.append("file", blob, filename || "document.docx");
  const { data } = await http.post("/upload", form);
  return data;
}

/**
 * Start the formatting pipeline.
 * @param {string} docId
 * @param {string} journal - e.g. "APA 7th Edition"
 * @returns {{ job_id: string, poll_url: string }}
 */
export async function startFormat(docId, journal) {
  const form = new FormData();
  form.append("doc_id", docId);
  form.append("journal", journal);
  form.append("mode", "standard");
  const { data } = await http.post("/format", form);
  return data;
}

/**
 * Poll job status until complete or error.
 * @param {string} jobId
 * @param {(status: object) => void} onProgress - Called on each poll tick.
 * @param {AbortSignal} [signal] - Optional abort signal.
 * @returns {object} Final result payload.
 */
export async function pollUntilDone(jobId, onProgress, signal) {
  const INTERVAL = 2000;
  const MAX_POLLS = 600; // 20 minutes max

  for (let i = 0; i < MAX_POLLS; i++) {
    if (signal?.aborted) throw new Error("Cancelled");

    const { data } = await http.get(`/format/status/${jobId}`);
    onProgress?.(data);

    if (data.status === "completed" || data.status === "done") {
      return data;
    }
    if (data.status === "error" || data.status === "failed") {
      throw new Error(data.error || "Pipeline failed");
    }

    await new Promise((r) => setTimeout(r, INTERVAL));
  }

  throw new Error("Pipeline timed out after 5 minutes");
}

/**
 * Get the full result for a completed job.
 * @param {string} jobId
 * @returns {object} Result with compliance_report, download_url, etc.
 */
export async function getResult(jobId) {
  const { data } = await http.get(`/format/result/${jobId}`);
  return data;
}

/**
 * Download the formatted DOCX as an ArrayBuffer.
 * @param {string} downloadPath - e.g. "outputs/run_abc/formatted_paper.docx"
 * @returns {ArrayBuffer}
 */
export async function downloadDocx(downloadPath) {
  // Backend returns download_url as "/download/run_abc/file.docx"
  // Strip the leading /download/ if present to avoid double-prefix via proxy
  const cleanPath = downloadPath.replace(/^\/download\//, "");
  const { data } = await http.get(`/download/${cleanPath}`, {
    responseType: "arraybuffer",
  });
  return data;
}
