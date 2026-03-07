import React from 'react';

const Icons = {
    upload: (
        <svg width="24" height="24" fill="none" viewBox="0 0 24 24">
            <path d="M12 16V4M12 4L8 8M12 4L16 8M4 20H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    ),
    trash: (
        <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    ),
    file: (
        <svg width="24" height="24" fill="none" viewBox="0 0 24 24">
            <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9l-7-7z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M13 2v7h7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    )
};

export default function GuidelinesUpload({ file, setFile, extracting }) {
    const handleFileChange = (e) => {
        const f = e.target.files[0];
        if (f) setFile(f);
    };

    const removeFile = (e) => {
        e.stopPropagation();
        setFile(null);
    };

    return (
        <div className="guidelines-upload">
            {!file ? (
                <label className="gu-dropzone">
                    <input type="file" accept=".pdf" onChange={handleFileChange} style={{ display: 'none' }} />
                    <div className="gu-icon">{Icons.upload}</div>
                    <div className="gu-text">
                        <strong>Choose PDF Guidelines</strong>
                        <p>Upload the journal's author instructions</p>
                    </div>
                </label>
            ) : (
                <div className="gu-file-card">
                    <div className="gu-file-info">
                        <div className="gu-file-icon">{Icons.file}</div>
                        <div className="gu-file-name">
                            <span>{file.name}</span>
                            <small>{(file.size / 1024).toFixed(1)} KB</small>
                        </div>
                    </div>
                    <button className="gu-remove" onClick={removeFile} title="Remove file">
                        {Icons.trash}
                    </button>
                </div>
            )}

            {extracting && (
                <div className="gu-status">
                    <div className="loading-dots">
                        <span></span><span></span><span></span>
                    </div>
                    Analyzing formatting rules...
                </div>
            )}

            <style>{`
        .guidelines-upload {
          margin-top: 8px;
        }
        .gu-dropzone {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 24px;
          background: var(--bg-soft);
          border: 2px dashed var(--bg-subtle);
          border-radius: var(--radius);
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .gu-dropzone:hover {
          border-color: var(--blue);
          background: var(--blue-alpha);
        }
        .gu-icon {
          color: var(--blue);
          background: var(--blue-alpha);
          width: 48px;
          height: 48px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .gu-text strong {
          display: block;
          font-size: 0.95rem;
          color: var(--text-primary);
        }
        .gu-text p {
          font-size: 0.8rem;
          color: var(--text-secondary);
          margin: 0;
        }
        .gu-file-card {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px;
          background: var(--bg-soft);
          border: 1.5px solid var(--blue);
          border-radius: var(--radius);
        }
        .gu-file-info {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .gu-file-icon {
          color: var(--blue);
        }
        .gu-file-name span {
          display: block;
          font-weight: 600;
          font-size: 0.9rem;
        }
        .gu-file-name small {
          color: var(--text-secondary);
          font-size: 0.75rem;
        }
        .gu-remove {
          background: transparent;
          border: none;
          color: var(--text-secondary);
          cursor: pointer;
          padding: 8px;
          border-radius: var(--radius-sm);
          transition: all 0.2s;
        }
        .gu-remove:hover {
          background: rgba(239, 68, 68, 0.1);
          color: var(--error);
        }
        .gu-status {
          margin-top: 12px;
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.85rem;
          color: var(--blue);
          font-weight: 500;
        }
      `}</style>
        </div>
    );
}
