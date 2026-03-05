import { useState, useRef } from "react";
import { Upload as UploadIcon, FileText, X, ChevronDown, AlertTriangle } from "lucide-react";

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const WARN_FILE_SIZE = 5 * 1024 * 1024; // 5 MB — soft warning only
const ALLOWED_EXTENSIONS = ["pdf", "docx"];

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function truncateFilename(name, maxLen = 40) {
  if (name.length <= maxLen) return name;
  const ext = name.lastIndexOf(".");
  const extension = ext > -1 ? name.slice(ext) : "";
  const base = ext > -1 ? name.slice(0, ext) : name;
  const keep = maxLen - extension.length - 3;
  return base.slice(0, keep) + "..." + extension;
}

function isValidFile(f) {
  const ext = f.name.split(".").pop().toLowerCase();
  return ALLOWED_EXTENSIONS.includes(ext);
}

export default function Upload({ file, setFile, journal, setJournal, journals, onSubmit }) {
  const [isDragging, setIsDragging] = useState(false);
  const [fileError, setFileError] = useState("");
  const fileInputRef = useRef(null);

  const canSubmit = file && journal;
  const isLargeFile = file && file.size > WARN_FILE_SIZE;

  function handleFileSelect(f) {
    if (!f) return;
    if (!isValidFile(f)) {
      setFileError("Only PDF and DOCX files are accepted.");
      setFile(null);
      return;
    }
    if (f.size > MAX_FILE_SIZE) {
      setFileError("File exceeds the 10 MB limit.");
      setFile(null);
      return;
    }
    setFileError("");
    setFile(f);
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    // Only use the first file; ignore the rest
    const dropped = e.dataTransfer.files[0];
    handleFileSelect(dropped);
  }

  function handleInputChange(e) {
    handleFileSelect(e.target.files?.[0]);
    // Reset so same file can be re-selected
    e.target.value = "";
  }

  function handleDragOver(e) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e) {
    // Only clear dragging if leaving the container (not entering a child)
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setIsDragging(false);
    }
  }

  return (
    <div className="space-y-5">

      {/* Drop Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`
          relative cursor-pointer rounded-xl border-2 border-dashed p-10 text-center
          transition-all duration-200 select-none
          ${isDragging
            ? "border-blue-400 bg-blue-950/20"
            : file
            ? "border-green-700/50 bg-green-950/10"
            : "border-gray-700 bg-gray-900/50 hover:border-gray-600 hover:bg-gray-800/30"
          }
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx"
          className="hidden"
          onChange={handleInputChange}
        />

        {file ? (
          <div className="flex flex-col items-center gap-3">
            <FileText className="w-10 h-10 text-green-500" />
            <div>
              <p className="text-sm font-semibold text-green-400" title={file.name}>
                {truncateFilename(file.name)}
              </p>
              <p className="text-xs text-gray-500 mt-1">{formatFileSize(file.size)}</p>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setFile(null);
                setFileError("");
              }}
              className="flex items-center gap-1 text-xs text-gray-600 hover:text-red-400 transition-colors mt-1"
            >
              <X className="w-3 h-3" />
              Remove
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <UploadIcon className="w-10 h-10 text-gray-600" />
            <div>
              <p className="text-sm font-medium text-gray-300">
                Drag &amp; drop your paper here
              </p>
              <p className="text-xs text-gray-600 mt-1">or click to browse</p>
              <p className="text-xs text-gray-700 mt-2">PDF or DOCX · Max 10 MB</p>
            </div>
          </div>
        )}
      </div>

      {/* File validation error */}
      {fileError && (
        <div className="flex items-center gap-2 px-3 py-2 bg-red-950/40 border border-red-900/40 rounded-lg text-xs text-red-400">
          <X className="w-3.5 h-3.5 shrink-0" />
          {fileError}
        </div>
      )}

      {/* Large file soft warning */}
      {isLargeFile && !fileError && (
        <div className="flex items-start gap-2 px-3 py-2 bg-yellow-950/30 border border-yellow-900/30 rounded-lg text-xs text-yellow-500">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          Large file ({formatFileSize(file.size)}) — processing may take up to 60 seconds.
        </div>
      )}

      {/* Journal Selector */}
      <div>
        <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
          Target Journal Style
        </label>
        <div className="relative">
          <select
            value={journal}
            onChange={(e) => setJournal(e.target.value)}
            className="
              w-full appearance-none bg-gray-900 border border-gray-700 rounded-xl
              px-4 py-3 pr-10 text-sm text-white
              focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30
              transition-colors cursor-pointer
            "
          >
            {journals.length === 0 ? (
              <option value="" disabled>Loading journals...</option>
            ) : (
              <>
                <option value="" disabled>Select a journal style...</option>
                {journals.map((j) => (
                  <option key={j} value={j}>{j}</option>
                ))}
              </>
            )}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
        </div>
      </div>

      {/* Submit Button */}
      <div>
        <button
          type="button"
          onClick={onSubmit}
          disabled={!canSubmit}
          className={`
            w-full py-3.5 rounded-xl font-semibold text-sm transition-all duration-200
            ${canSubmit
              ? "bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-900/20 active:scale-[0.99] cursor-pointer"
              : "bg-gray-800 text-gray-600 cursor-not-allowed"
            }
          `}
        >
          Format My Paper
        </button>
        <p className="text-center text-xs text-gray-700 mt-2">Processing takes ~45 seconds</p>
      </div>

    </div>
  );
}
