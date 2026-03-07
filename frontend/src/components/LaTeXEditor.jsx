import { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

const IconBack = () => (
    <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
        <path d="M19 12H5M12 19l-7-7 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
)
const IconDownload = () => (
    <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <polyline points="7 10 12 15 17 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
)
const IconPlay = () => (
    <svg width="18" height="18" fill="none" viewBox="0 0 24 24">
        <path d="M5 3l14 9-14 9V3z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
)

export default function LaTeXEditor({ jobId, onBack }) {
    const [source, setSource] = useState('')
    const [loadingSource, setLoadingSource] = useState(true)
    const [compiling, setCompiling] = useState(false)
    const [pdfUrl, setPdfUrl] = useState(null)
    const [error, setError] = useState(null)
    const [compileUnavailable, setCompileUnavailable] = useState(false)

    // Fetch initial LaTeX source
    useEffect(() => {
        if (!jobId) return

        const fetchSource = async () => {
            try {
                const res = await axios.get(`${API}/latex/${jobId}`)
                setSource(res.data.latex_source || '')
            } catch (err) {
                setError('Failed to load LaTeX source. It may no longer be available.')
            } finally {
                setLoadingSource(false)
            }
        }

        fetchSource()
    }, [jobId])

    // Compile LaTeX to PDF
    const handleCompile = async () => {
        if (!source.trim()) return
        setCompiling(true)
        setError(null)
        setCompileUnavailable(false)

        try {
            const res = await axios.post(`${API}/latex/compile`,
                { latex_source: source },
                { responseType: 'blob' }
            )

            // Cleanup old object URL
            if (pdfUrl) URL.revokeObjectURL(pdfUrl)

            const blob = new Blob([res.data], { type: 'application/pdf' })
            const url = URL.createObjectURL(blob)
            setPdfUrl(url)
        } catch (err) {
            if (err.response?.status === 501) {
                setCompileUnavailable(true)
            } else {
                // Since we requested a blob, we need to extract the JSON error message from it
                if (err.response?.data instanceof Blob) {
                    const text = await err.response.data.text()
                    try {
                        const json = JSON.parse(text)
                        setError(json.detail?.error || 'Compilation failed.')
                    } catch {
                        setError('Compilation failed.')
                    }
                } else {
                    setError('Compilation failed.')
                }
            }
        } finally {
            setCompiling(false)
        }
    }

    // Download raw .tex file
    const handleDownloadTex = () => {
        const blob = new Blob([source], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'manuscript.tex'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
    }

    // Download compiled PDF
    const handleDownloadPdf = () => {
        if (!pdfUrl) return
        const a = document.createElement('a')
        a.href = pdfUrl
        a.download = 'compiled_manuscript.pdf'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
    }

    // Cleanup object URL on unmount
    useEffect(() => {
        return () => {
            if (pdfUrl) URL.revokeObjectURL(pdfUrl)
        }
    }, [pdfUrl])

    return (
        <div className="flex flex-col h-[calc(100vh-64px)] bg-gray-50 overflow-hidden" style={{ fontFamily: 'Inter, sans-serif' }}>

            {/* Toolbar */}
            <div className="bg-white border-b px-6 py-3 flex items-center justify-between shrink-0 shadow-sm z-10">
                <div className="flex items-center gap-4">
                    <button onClick={onBack} className="text-gray-500 hover:text-gray-900 transition flex items-center gap-2 text-sm font-medium">
                        <IconBack /> Back to Results
                    </button>
                    <div className="h-6 w-px bg-gray-200" />
                    <h2 className="font-semibold text-gray-800">Advanced Editor</h2>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={handleDownloadTex}
                        disabled={loadingSource}
                        className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
                    >
                        <IconDownload /> Download .tex
                    </button>

                    <button
                        onClick={handleCompile}
                        disabled={compiling || loadingSource}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition shadow-sm"
                    >
                        {compiling ? (
                            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        ) : (
                            <IconPlay />
                        )}
                        Compile & Preview
                    </button>

                    {pdfUrl && (
                        <button
                            onClick={handleDownloadPdf}
                            className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition shadow-sm ml-2"
                        >
                            <IconDownload /> Download PDF
                        </button>
                    )}
                </div>
            </div>

            {/* Main Workspace */}
            <div className="flex-1 flex overflow-hidden">

                {/* Left Pane: Code Editor */}
                <div className="w-1/2 flex flex-col border-r bg-gray-900 text-gray-100 relative">
                    {loadingSource && (
                        <div className="absolute inset-0 z-10 bg-gray-900/50 backdrop-blur-sm flex items-center justify-center">
                            <div className="text-gray-300 flex items-center gap-3">
                                <div className="w-5 h-5 border-2 border-gray-500 border-t-gray-300 rounded-full animate-spin" />
                                Loading LaTeX source...
                            </div>
                        </div>
                    )}

                    <div className="px-4 py-2 bg-gray-800 border-b border-gray-700 text-xs font-mono text-gray-400 flex justify-between">
                        <span>manuscript.tex</span>
                        <span>LaTeX</span>
                    </div>

                    <textarea
                        value={source}
                        onChange={(e) => setSource(e.target.value)}
                        className="flex-1 w-full bg-transparent text-gray-200 p-4 font-mono text-sm leading-relaxed resize-none focus:outline-none"
                        spellCheck={false}
                        style={{
                            tabSize: 4,
                            scrollbarColor: '#4b5563 #111827'
                        }}
                    />
                </div>

                {/* Right Pane: Preview / Errors */}
                <div className="w-1/2 flex flex-col bg-gray-100 relative overflow-hidden">

                    <div className="px-4 py-2 bg-white border-b text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Preview Layout
                    </div>

                    {compiling && (
                        <div className="absolute inset-0 z-10 bg-white/80 backdrop-blur-sm flex flex-col items-center justify-center">
                            <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-4" />
                            <p className="text-gray-600 font-medium tracking-wide animate-pulse">Running pdflatex...</p>
                        </div>
                    )}

                    <div className="flex-1 p-4 overflow-auto flex items-center justify-center">
                        {compileUnavailable ? (
                            <div className="bg-white p-8 rounded-xl shadow-sm border border-orange-200 max-w-md text-center">
                                <div className="w-16 h-16 bg-orange-100 text-orange-600 rounded-full flex items-center justify-center mx-auto mb-4">
                                    <IconPlay />
                                </div>
                                <h3 className="text-lg font-semibold text-gray-900 mb-2">Live Compiler Unavailable</h3>
                                <p className="text-gray-600 text-sm mb-6 leading-relaxed">
                                    The backend server does not have <code>pdflatex</code> installed. Live preview compilation is disabled.
                                </p>
                                <button
                                    onClick={handleDownloadTex}
                                    className="bg-blue-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-blue-700 transition"
                                >
                                    Download .tex to compile locally
                                </button>
                            </div>
                        ) : error ? (
                            <div className="bg-red-50 p-6 rounded-xl border border-red-200 w-full max-w-lg self-start mt-8 mx-auto">
                                <h3 className="text-red-800 font-semibold mb-2 flex items-center gap-2">
                                    <span className="w-5 h-5 bg-red-100 rounded-full inline-flex items-center justify-center text-red-600 text-xs font-bold">!</span>
                                    Compilation Error
                                </h3>
                                <p className="text-red-700 text-sm mb-4">{error}</p>
                                <p className="text-red-600 text-xs bg-red-100/50 p-3 rounded font-mono break-words">
                                    Check your LaTeX syntax. Look for unescaped special characters (e.g., %, &amp;, $) or mismatched environments.
                                </p>
                            </div>
                        ) : pdfUrl ? (
                            <iframe
                                src={`${pdfUrl}#toolbar=0`}
                                className="w-full h-full bg-white shadow-lg rounded-sm border"
                                title="Compiled PDF Preview"
                            />
                        ) : (
                            <div className="text-center text-gray-400">
                                <div className="mb-4 opacity-50 flex justify-center">
                                    <svg width="48" height="48" fill="none" viewBox="0 0 24 24">
                                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                                        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                                    </svg>
                                </div>
                                <p>Click "Compile & Preview" to render the PDF.</p>
                            </div>
                        )}
                    </div>
                </div>

            </div>
        </div>
    )
}
