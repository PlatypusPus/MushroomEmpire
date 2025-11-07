"use client";
import { TryTab } from "./Sidebar";
import { useState, useRef, useCallback, useEffect } from "react";
import {
  saveLatestUpload,
  getLatestUpload,
  deleteLatestUpload,
} from "../../lib/indexeddb";
import {
  analyzeDataset,
  cleanDataset,
  detectPII,
  getReportUrl,
  type AnalyzeResponse,
  type CleanResponse,
  type DetectPIIResponse,
} from "../../lib/api";

interface CenterPanelProps {
  tab: TryTab;
  onAnalyze?: () => void;
}

interface UploadedFileMeta {
  name: string;
  size: number;
  type: string;
  contentPreview: string;
}

interface TablePreviewData {
  headers: string[];
  rows: string[][];
  origin: "csv";
}

export function CenterPanel({ tab, onAnalyze }: CenterPanelProps) {
  const PREVIEW_BYTES = 64 * 1024; // read first 64KB slice for large-file preview
  const [fileMeta, setFileMeta] = useState<UploadedFileMeta | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState<number>(0);
  const [progressLabel, setProgressLabel] = useState<string>("Processing");
  const [tablePreview, setTablePreview] = useState<TablePreviewData | null>(
    null,
  );
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [loadedFromCache, setLoadedFromCache] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Analysis results
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResponse | null>(
    null,
  );
  const [cleanResult, setCleanResult] = useState<CleanResponse | null>(null);
  const [piiDetectionResult, setPIIDetectionResult] =
    useState<DetectPIIResponse | null>(null);

  const reset = () => {
    setFileMeta(null);
    setUploadedFile(null);
    setProgress(0);
    setProgressLabel("Processing");
    setTablePreview(null);
    setError(null);
    setPIIDetectionResult(null);
  };

  // Handle API calls
  const handleAnalyze = async () => {
    if (!uploadedFile) {
      setError("No file uploaded");
      return;
    }

    setIsProcessing(true);
    setError(null);
    setProgressLabel("Analyzing dataset...");

    try {
      const result = await analyzeDataset(uploadedFile);
      setAnalyzeResult(result);
      setProgressLabel("Analysis complete!");
      onAnalyze?.(); // Navigate to bias-analysis tab
    } catch (err: any) {
      setError(err.message || "Analysis failed");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDetectPII = async () => {
    if (!uploadedFile) {
      setError("No file uploaded");
      return;
    }

    setIsProcessing(true);
    setError(null);
    setProgressLabel("Detecting PII...");

    try {
      const result = await detectPII(uploadedFile);
      setPIIDetectionResult(result);
      setProgressLabel("PII detection complete!");
    } catch (err: any) {
      setError(err.message || "PII detection failed");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleClean = async () => {
    if (!uploadedFile) {
      setError("No file uploaded");
      return;
    }

    setIsProcessing(true);
    setError(null);
    setProgressLabel("Cleaning dataset...");

    try {
      const result = await cleanDataset(uploadedFile);
      setCleanResult(result);
      setProgressLabel("Cleaning complete!");
    } catch (err: any) {
      setError(err.message || "Cleaning failed");
    } finally {
      setIsProcessing(false);
    }
  };
  function tryParseCSV(
    text: string,
    maxRows = 50,
    maxCols = 40,
  ): TablePreviewData | null {
    const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
    if (lines.length < 2) return null;
    const commaDensity = lines
      .slice(0, 10)
      .filter((l) => l.includes(",")).length;
    if (commaDensity < 2) return null;
    const parseLine = (line: string) => {
      const out: string[] = [];
      let cur = "";
      let inQuotes = false;
      for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') {
          if (inQuotes && line[i + 1] === '"') {
            cur += '"';
            i++;
          } else {
            inQuotes = !inQuotes;
          }
        } else if (ch === "," && !inQuotes) {
          out.push(cur);
          cur = "";
        } else {
          cur += ch;
        }
      }
      out.push(cur);
      return out.map((c) => c.trim());
    };
    const raw = lines.slice(0, maxRows).map(parseLine);
    if (raw.length === 0) return null;
    const headers = raw[0];
    const colCount = Math.min(headers.length, maxCols);
    const rows = raw.slice(1).map((r) => r.slice(0, colCount));
    return { headers: headers.slice(0, colCount), rows, origin: "csv" };
  }

  // We no longer build table preview for JSON; revert JSON to raw text view.

  const processFile = useCallback(async (f: File) => {
    if (!f) return;
    const isCSV = /\.csv$/i.test(f.name);

    if (!isCSV) {
      try {
        setProgressLabel("Uploading file...");
        setIsProcessing(true);
        setError(null);

        const formData = new FormData();
        formData.append("file", f);

        const res = await fetch("http://localhost:8000/api/files", {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const errText = await res.text();
          throw new Error(errText || "Upload failed");
        }

        // The backend returns a CSV file
        const blob = await res.blob();
        const downloadUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = "dataset.csv";
        document.body.appendChild(a);
        a.click();
        a.remove();

        setProgressLabel("File processed successfully");
      } catch (err: any) {
        setError(err.message || "File processing failed");
      } finally {
        setIsProcessing(false);
      }
      return; // stop further processing since we’re done
    }

    setProgress(0);
    setUploadedFile(f); // Save the file for API calls

    // For large files, show a progress bar while reading the file stream (no preview)
    if (f.size > 1024 * 1024) {
      setProgressLabel("Uploading");
      const metaObj: UploadedFileMeta = {
        name: f.name,
        size: f.size,
        type: f.type || "unknown",
        contentPreview: `Loading partial preview (first ${Math.round(PREVIEW_BYTES / 1024)}KB)...`,
      };
      setFileMeta(metaObj);
      setTablePreview(null);
      // Save to IndexedDB immediately so it persists without needing full read
      (async () => {
        try {
          await saveLatestUpload(f, metaObj);
        } catch {}
      })();
      // Read head slice for partial preview & possible CSV table extraction
      try {
        const headBlob = f.slice(0, PREVIEW_BYTES);
        const headReader = new FileReader();
        headReader.onload = async () => {
          try {
            const buf = headReader.result as ArrayBuffer;
            const decoder = new TextDecoder();
            const text = decoder.decode(buf);
            setFileMeta((prev) =>
              prev ? { ...prev, contentPreview: text.slice(0, 4000) } : prev,
            );
            if (isCSV) {
              const parsed = tryParseCSV(text);
              setTablePreview(parsed);
            } else {
              setTablePreview(null);
            }
            try {
              await saveLatestUpload(f, {
                ...metaObj,
                contentPreview: text.slice(0, 4000),
              });
            } catch {}
          } catch {
            /* ignore */
          }
        };
        headReader.readAsArrayBuffer(headBlob);
      } catch {
        /* ignore */
      }
      // Use streaming read for progress without buffering entire file in memory
      try {
        const stream: ReadableStream<Uint8Array> | undefined =
          typeof (f as any).stream === "function"
            ? (f as any).stream()
            : undefined;
        if (stream && typeof stream.getReader === "function") {
          const reader = stream.getReader();
          let loaded = 0;
          const total = f.size || 1;
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            loaded += value ? value.length : 0;
            const pct = Math.min(100, Math.round((loaded / total) * 100));
            setProgress(pct);
          }
          setProgress(100);
        } else {
          // Fallback to FileReader progress events
          const reader = new FileReader();
          reader.onprogress = (evt) => {
            if (evt.lengthComputable) {
              const pct = Math.min(
                100,
                Math.round((evt.loaded / evt.total) * 100),
              );
              setProgress(pct);
            } else {
              setProgress((p) => (p < 90 ? p + 5 : p));
            }
          };
          reader.onloadend = () => setProgress(100);
          reader.onerror = () => setProgress(0);
          reader.readAsArrayBuffer(f);
        }
      } catch {
        setProgress(100);
      }
      return;
    }
    const reader = new FileReader();
    reader.onprogress = (evt) => {
      if (evt.lengthComputable) {
        const pct = Math.min(100, Math.round((evt.loaded / evt.total) * 100));
        setProgress(pct);
      } else {
        setProgress((p) => (p < 90 ? p + 5 : p));
      }
    };
    reader.onload = async () => {
      try {
        const buf = reader.result as ArrayBuffer;
        const decoder = new TextDecoder();
        const text = decoder.decode(buf);
        const metaObj: UploadedFileMeta = {
          name: f.name,
          size: f.size,
          type: f.type || "unknown",
          contentPreview: text.slice(0, 4000),
        };
        setFileMeta(metaObj);
        if (isCSV) {
          const parsed = tryParseCSV(text);
          setTablePreview(parsed);
        } else {
          setTablePreview(null);
        }
        // Save file blob and meta to browser cache (IndexedDB)
        try {
          await saveLatestUpload(f, metaObj);
        } catch {}
        setProgressLabel("Processing");
        setProgress(100);
      } catch (e) {
        const metaObj: UploadedFileMeta = {
          name: f.name,
          size: f.size,
          type: f.type || "unknown",
          contentPreview: "Unable to decode preview.",
        };
        setFileMeta(metaObj);
        setTablePreview(null);
        try {
          await saveLatestUpload(f, metaObj);
        } catch {}
        setProgressLabel("Processing");
        setProgress(100);
      }
    };
    reader.onerror = () => {
      setProgress(0);
    };
    reader.readAsArrayBuffer(f);
  }, []);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    processFile(f as File);
  }

  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const onDragLeave = () => setIsDragging(false);
  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    processFile(f as File);
  };

  // Load last cached upload on mount (processing tab only)
  useEffect(() => {
    let ignore = false;
    if (tab !== "processing") return;
    (async () => {
      try {
        const { file, meta } = await getLatestUpload();
        if (!ignore && meta) {
          setFileMeta(meta as UploadedFileMeta);
          if (file) {
            setUploadedFile(file);
          }
          setLoadedFromCache(true);
        }
      } catch {}
    })();
    return () => {
      ignore = true;
    };
  }, [tab]);
  function renderTabContent() {
    switch (tab) {
      case "processing":
        return (
          <div className="space-y-4 max-w-[1100px] xl:max-w-[1200px] w-full mx-auto">
            <h2 className="text-xl font-semibold">Upload & Process Data</h2>
            <p className="text-sm text-slate-600">
              Upload a CSV / JSON / text file. We will later parse, detect PII,
              and queue analyses.
            </p>
            <div className="flex flex-col gap-3 min-w-0">
              <div
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
                className={
                  "rounded-lg border-2 border-dashed p-6 text-center transition-colors " +
                  (isDragging
                    ? "border-brand-600 bg-brand-50"
                    : "border-slate-300 hover:border-brand-300")
                }
              >
                <p className="text-sm text-slate-600">
                  Drag & drop a CSV / JSON / TXT here, or click to browse.
                </p>
                <div className="mt-3">
                  <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    className="inline-flex items-center rounded-md bg-brand-600 px-4 py-2 text-white text-sm font-medium shadow hover:bg-brand-500"
                  >
                    Choose file
                  </button>
                </div>
              </div>
              <input
                ref={inputRef}
                type="file"
                accept=".csv,.json,.txt"
                onChange={handleFileChange}
                className="hidden"
                aria-hidden
              />
              {progress > 0 && (
                <div className="w-full">
                  <div className="h-2 w-full rounded-full bg-slate-200 overflow-hidden">
                    <div
                      className="h-2 bg-brand-600 transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {progressLabel} {progress}%
                  </div>
                </div>
              )}
              {fileMeta && (
                <div className="rounded-md border border-slate-200 p-4 bg-white shadow-sm">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm font-medium">{fileMeta.name}</div>
                    <div className="text-xs text-slate-500">
                      {Math.round(fileMeta.size / 1024)} KB
                    </div>
                  </div>
                  {loadedFromCache && (
                    <div className="mb-2 text-[11px] text-brand-700">
                      Loaded from browser cache
                    </div>
                  )}
                  <div className="mb-3 text-xs text-slate-500">
                    {fileMeta.type || "Unknown type"}
                  </div>
                  {/* Table preview when structured data detected; otherwise show text */}
                  {tablePreview && tablePreview.origin === "csv" ? (
                    <div className="max-h-64 w-full min-w-0 overflow-x-auto overflow-y-auto rounded-md bg-slate-50">
                      <table className="min-w-full text-xs">
                        <thead className="sticky top-0 bg-slate-100">
                          <tr>
                            {tablePreview.headers.map((h, idx) => (
                              <th
                                key={idx}
                                className="text-left font-semibold px-3 py-2 border-b border-slate-200 whitespace-nowrap"
                              >
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {tablePreview.rows.map((r, i) => (
                            <tr
                              key={i}
                              className={i % 2 === 0 ? "" : "bg-slate-100/50"}
                            >
                              {r.map((c, j) => (
                                <td
                                  key={j}
                                  className="px-3 py-1.5 border-b border-slate-100 whitespace-nowrap max-w-[24ch] overflow-hidden text-ellipsis"
                                >
                                  {c}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <pre className="max-h-64 overflow-auto text-xs bg-slate-50 p-3 rounded-md whitespace-pre-wrap leading-relaxed">
                      {fileMeta.contentPreview || "(no preview)"}
                    </pre>
                  )}

                  {error && (
                    <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
                      ❌ {error}
                    </div>
                  )}

                  {piiDetectionResult && (
                    <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-md text-sm text-blue-700">
                      🔍 PII Detection complete! Found{" "}
                      {piiDetectionResult.summary.risky_columns_found} risky
                      columns in {piiDetectionResult.file_type.toUpperCase()}{" "}
                      file.
                      <div className="mt-1 text-xs">
                        <span className="font-semibold text-red-700">
                          {piiDetectionResult.summary.high_risk_count} HIGH
                        </span>{" "}
                        •
                        <span className="font-semibold text-orange-600 ml-1">
                          {piiDetectionResult.summary.medium_risk_count} MEDIUM
                        </span>{" "}
                        •
                        <span className="font-semibold text-yellow-600 ml-1">
                          {piiDetectionResult.summary.low_risk_count} LOW
                        </span>
                      </div>
                      <p className="mt-2 text-xs">
                        Review detected risks in the "Bias & Risk Mitigation"
                        tab to choose anonymization strategies.
                      </p>
                    </div>
                  )}

                  {analyzeResult && (
                    <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-md text-sm text-green-700">
                      ✅ Analysis complete! View results in tabs.
                      <a
                        href={getReportUrl(analyzeResult.report_file)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ml-2 underline"
                      >
                        Download Report
                      </a>
                    </div>
                  )}

                  {cleanResult && (
                    <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-md text-sm text-green-700">
                      ✅ Cleaning complete!{" "}
                      {cleanResult.summary.total_cells_affected} cells
                      anonymized.
                      <div className="mt-2 flex gap-2">
                        <a
                          href={getReportUrl(cleanResult.files.cleaned_csv)}
                          download
                          className="underline"
                        >
                          Download Cleaned CSV
                        </a>
                        <a
                          href={getReportUrl(cleanResult.files.audit_report)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline"
                        >
                          View Audit Report
                        </a>
                      </div>
                    </div>
                  )}

                  <div className="mt-3 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={async () => {
                        reset();
                        try {
                          await deleteLatestUpload();
                        } catch {}
                        setLoadedFromCache(false);
                        setAnalyzeResult(null);
                        setCleanResult(null);
                        setPIIDetectionResult(null);
                      }}
                      className="text-xs rounded-md border px-3 py-1.5 hover:bg-slate-50"
                    >
                      Clear
                    </button>
                    <button
                      type="button"
                      onClick={handleDetectPII}
                      disabled={isProcessing}
                      className="text-xs rounded-md bg-blue-600 text-white px-3 py-1.5 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isProcessing ? "Processing..." : "🔍 Detect PII"}
                    </button>
                    <button
                      type="button"
                      onClick={handleAnalyze}
                      disabled={isProcessing}
                      className="text-xs rounded-md bg-brand-600 text-white px-3 py-1.5 hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isProcessing ? "Processing..." : "⚡ Analyze"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      case "bias-analysis":
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold mb-2">
                Bias & Fairness Analysis
              </h2>
              <p className="text-sm text-slate-600">
                Comprehensive evaluation of algorithmic fairness across
                demographic groups
              </p>
            </div>

            {analyzeResult ? (
              <div className="space-y-6">
                {/* Overall Bias Score Card */}
                <div className="p-6 bg-gradient-to-br from-purple-50 to-indigo-50 rounded-xl border-2 border-purple-200">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-sm font-medium text-purple-700 mb-1">
                        Overall Bias Score
                      </div>
                      <div className="text-5xl font-bold text-purple-900">
                        {(
                          analyzeResult.bias_metrics.overall_bias_score * 100
                        ).toFixed(1)}
                        %
                      </div>
                      <div className="mt-3 flex items-center gap-2">
                        {analyzeResult.bias_metrics.overall_bias_score < 0.3 ? (
                          <>
                            <span className="px-3 py-1 bg-green-100 text-green-800 text-xs font-semibold rounded-full">
                              ✓ Low Bias
                            </span>
                            <span className="text-sm text-slate-600">
                              Excellent fairness
                            </span>
                          </>
                        ) : analyzeResult.bias_metrics.overall_bias_score <
                          0.5 ? (
                          <>
                            <span className="px-3 py-1 bg-yellow-100 text-yellow-800 text-xs font-semibold rounded-full">
                              ⚠ Moderate Bias
                            </span>
                            <span className="text-sm text-slate-600">
                              Monitor recommended
                            </span>
                          </>
                        ) : (
                          <>
                            <span className="px-3 py-1 bg-red-100 text-red-800 text-xs font-semibold rounded-full">
                              ✗ High Bias
                            </span>
                            <span className="text-sm text-slate-600">
                              Action required
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-slate-600 mb-1">
                        Violations
                      </div>
                      <div
                        className={`text-3xl font-bold ${analyzeResult.bias_metrics.violations_detected.length > 0 ? "text-red-600" : "text-green-600"}`}
                      >
                        {analyzeResult.bias_metrics.violations_detected.length}
                      </div>
                    </div>
                  </div>

                  {/* Interpretation */}
                  <div className="mt-4 p-4 bg-white/70 rounded-lg">
                    <div className="text-xs font-semibold text-purple-800 mb-1">
                      INTERPRETATION
                    </div>
                    <p className="text-sm text-slate-700">
                      {analyzeResult.bias_metrics.overall_bias_score < 0.3
                        ? "Your model demonstrates strong fairness across demographic groups. Continue monitoring to ensure consistent performance."
                        : analyzeResult.bias_metrics.overall_bias_score < 0.5
                          ? "Moderate bias detected. Review fairness metrics below and consider implementing mitigation strategies to reduce disparities."
                          : "Significant bias detected. Immediate action required to address fairness concerns before deployment. Review all violation details below."}
                    </p>
                  </div>
                </div>

                {/* Model Performance Metrics */}
                <div className="p-6 bg-white rounded-xl border border-slate-200 shadow-sm">
                  <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                    <span className="text-blue-600">📊</span>
                    Model Performance Metrics
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-4 bg-blue-50 rounded-lg">
                      <div className="text-xs text-blue-700 font-semibold mb-1">
                        ACCURACY
                      </div>
                      <div className="text-2xl font-bold text-blue-900">
                        {(
                          analyzeResult.model_performance.accuracy * 100
                        ).toFixed(1)}
                        %
                      </div>
                      <div className="text-xs text-slate-600 mt-1">
                        Overall correctness
                      </div>
                    </div>
                    <div className="p-4 bg-green-50 rounded-lg">
                      <div className="text-xs text-green-700 font-semibold mb-1">
                        PRECISION
                      </div>
                      <div className="text-2xl font-bold text-green-900">
                        {(
                          analyzeResult.model_performance.precision * 100
                        ).toFixed(1)}
                        %
                      </div>
                      <div className="text-xs text-slate-600 mt-1">
                        Positive prediction accuracy
                      </div>
                    </div>
                    <div className="p-4 bg-purple-50 rounded-lg">
                      <div className="text-xs text-purple-700 font-semibold mb-1">
                        RECALL
                      </div>
                      <div className="text-2xl font-bold text-purple-900">
                        {(analyzeResult.model_performance.recall * 100).toFixed(
                          1,
                        )}
                        %
                      </div>
                      <div className="text-xs text-slate-600 mt-1">
                        True positive detection rate
                      </div>
                    </div>
                    <div className="p-4 bg-orange-50 rounded-lg">
                      <div className="text-xs text-orange-700 font-semibold mb-1">
                        F1 SCORE
                      </div>
                      <div className="text-2xl font-bold text-orange-900">
                        {(
                          analyzeResult.model_performance.f1_score * 100
                        ).toFixed(1)}
                        %
                      </div>
                      <div className="text-xs text-slate-600 mt-1">
                        Balanced metric
                      </div>
                    </div>
                  </div>
                </div>

                {/* Fairness Metrics */}
                {Object.keys(analyzeResult.bias_metrics.disparate_impact)
                  .length > 0 && (
                  <div className="p-6 bg-white rounded-xl border border-slate-200 shadow-sm">
                    <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                      <span className="text-purple-600">⚖️</span>
                      Fairness Metrics by Protected Attribute
                    </h3>

                    {Object.entries(
                      analyzeResult.bias_metrics.disparate_impact,
                    ).map(([attr, metrics]: [string, any]) => (
                      <div
                        key={attr}
                        className="mb-6 last:mb-0 p-4 bg-slate-50 rounded-lg"
                      >
                        <div className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
                          <span className="px-2 py-1 bg-purple-100 text-purple-800 text-xs rounded">
                            {attr.toUpperCase()}
                          </span>
                        </div>

                        {/* Disparate Impact */}
                        {metrics?.disparate_impact?.value !== undefined && (
                          <div className="mb-3 p-3 bg-white rounded border border-slate-200">
                            <div className="flex items-center justify-between mb-2">
                              <div>
                                <div className="text-xs font-semibold text-slate-600">
                                  DISPARATE IMPACT RATIO
                                </div>
                                <div className="text-2xl font-bold text-slate-900">
                                  {metrics.disparate_impact.value.toFixed(3)}
                                </div>
                              </div>
                              <div
                                className={`px-3 py-1 rounded-full text-xs font-semibold ${
                                  metrics.disparate_impact.fair
                                    ? "bg-green-100 text-green-800"
                                    : "bg-red-100 text-red-800"
                                }`}
                              >
                                {metrics.disparate_impact.fair
                                  ? "✓ FAIR"
                                  : "✗ UNFAIR"}
                              </div>
                            </div>
                            <div className="text-xs text-slate-600 mb-2">
                              {metrics.disparate_impact.interpretation ||
                                "Ratio of positive rates between groups"}
                            </div>
                            <div className="text-xs text-slate-500 bg-blue-50 p-2 rounded">
                              <strong>Fair Range:</strong>{" "}
                              {metrics.disparate_impact.threshold || 0.8} -{" "}
                              {(
                                1 / (metrics.disparate_impact.threshold || 0.8)
                              ).toFixed(2)}
                              {metrics.disparate_impact.fair
                                ? " • This ratio indicates balanced treatment across groups."
                                : " • Ratio outside fair range suggests one group receives significantly different outcomes."}
                            </div>
                          </div>
                        )}

                        {/* Statistical Parity */}
                        {metrics?.statistical_parity_difference?.value !==
                          undefined && (
                          <div className="mb-3 p-3 bg-white rounded border border-slate-200">
                            <div className="flex items-center justify-between mb-2">
                              <div>
                                <div className="text-xs font-semibold text-slate-600">
                                  STATISTICAL PARITY DIFFERENCE
                                </div>
                                <div className="text-2xl font-bold text-slate-900">
                                  {metrics.statistical_parity_difference.value.toFixed(
                                    3,
                                  )}
                                </div>
                              </div>
                              <div
                                className={`px-3 py-1 rounded-full text-xs font-semibold ${
                                  metrics.statistical_parity_difference.fair
                                    ? "bg-green-100 text-green-800"
                                    : "bg-red-100 text-red-800"
                                }`}
                              >
                                {metrics.statistical_parity_difference.fair
                                  ? "✓ FAIR"
                                  : "✗ UNFAIR"}
                              </div>
                            </div>
                            <div className="text-xs text-slate-600 mb-2">
                              {metrics.statistical_parity_difference
                                .interpretation ||
                                "Difference in positive rates"}
                            </div>
                            <div className="text-xs text-slate-500 bg-blue-50 p-2 rounded">
                              <strong>Fair Threshold:</strong> ±
                              {metrics.statistical_parity_difference
                                .threshold || 0.1}
                              {metrics.statistical_parity_difference.fair
                                ? " • Difference within acceptable range for equal treatment."
                                : " • Significant difference in positive outcome rates between groups."}
                            </div>
                          </div>
                        )}

                        {/* Group Metrics */}
                        {metrics.group_metrics && (
                          <div className="p-3 bg-white rounded border border-slate-200">
                            <div className="text-xs font-semibold text-slate-600 mb-2">
                              GROUP PERFORMANCE
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {Object.entries(metrics.group_metrics).map(
                                ([group, groupMetrics]: [string, any]) => (
                                  <div
                                    key={group}
                                    className="p-2 bg-slate-50 rounded"
                                  >
                                    <div className="font-medium text-sm text-slate-800">
                                      {group}
                                    </div>
                                    <div className="text-xs text-slate-600 mt-1">
                                      <div>
                                        Positive Rate:{" "}
                                        <strong>
                                          {groupMetrics.positive_rate !==
                                          undefined
                                            ? (
                                                groupMetrics.positive_rate * 100
                                              ).toFixed(1)
                                            : "N/A"}
                                          %
                                        </strong>
                                      </div>
                                      <div>
                                        Sample Size:{" "}
                                        <strong>
                                          {groupMetrics.sample_size ?? "N/A"}
                                        </strong>
                                      </div>
                                      {groupMetrics.tpr !== undefined && (
                                        <div>
                                          True Positive Rate:{" "}
                                          <strong>
                                            {(groupMetrics.tpr * 100).toFixed(
                                              1,
                                            )}
                                            %
                                          </strong>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                ),
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Violations */}
                {analyzeResult.bias_metrics.violations_detected.length > 0 && (
                  <div className="p-6 bg-red-50 rounded-xl border-2 border-red-200">
                    <h3 className="font-bold text-lg mb-4 flex items-center gap-2 text-red-800">
                      <span>⚠️</span>
                      Fairness Violations Detected
                    </h3>
                    <div className="space-y-4">
                      {analyzeResult.bias_metrics.violations_detected.map(
                        (violation: any, i: number) => {
                          // Map bias violations to relevant GDPR articles
                          const gdprArticles = [
                            {
                              article:
                                "Article 5(1)(a) - Lawfulness, Fairness, and Transparency",
                              explanation:
                                "Personal data must be processed fairly. Algorithmic bias violates the fairness principle.",
                            },
                            {
                              article: "Article 22 - Automated Decision-Making",
                              explanation:
                                "Individuals have the right not to be subject to decisions based solely on automated processing that produce legal or similarly significant effects, especially if discriminatory.",
                            },
                            {
                              article:
                                "Recital 71 - Safeguards Against Discrimination",
                              explanation:
                                "Automated decision-making should not be based on special categories of data and should include safeguards to prevent discriminatory effects.",
                            },
                          ];

                          // Add ECOA if dealing with credit/lending
                          const isCredit =
                            violation.attribute &&
                            (violation.attribute
                              .toLowerCase()
                              .includes("credit") ||
                              violation.attribute
                                .toLowerCase()
                                .includes("loan") ||
                              violation.attribute
                                .toLowerCase()
                                .includes("income"));

                          return (
                            <div
                              key={i}
                              className="p-5 bg-white rounded-xl border-2 border-red-300 shadow-sm hover:shadow-md transition-all"
                            >
                              {/* Violation Header */}
                              <div className="flex items-start gap-3 mb-4">
                                <span
                                  className={`px-3 py-1 rounded-full text-xs font-black shadow-sm ${
                                    violation.severity === "HIGH"
                                      ? "bg-red-600 text-white"
                                      : violation.severity === "MEDIUM"
                                        ? "bg-orange-600 text-white"
                                        : "bg-yellow-600 text-white"
                                  }`}
                                >
                                  {violation.severity}
                                </span>
                                <div className="flex-1">
                                  <div className="font-bold text-lg text-slate-900">
                                    {violation.attribute}: {violation.metric}
                                  </div>
                                  <div className="text-sm text-slate-700 mt-1">
                                    {violation.message}
                                  </div>
                                </div>
                              </div>

                              {/* Violation Details */}
                              {violation.details && (
                                <div className="mb-4 p-3 bg-slate-50 rounded-lg border border-slate-200">
                                  <div className="text-xs font-semibold text-slate-600 mb-1">
                                    📊 TECHNICAL DETAILS
                                  </div>
                                  <div className="text-sm text-slate-700">
                                    {violation.details}
                                  </div>
                                </div>
                              )}

                              {/* GDPR Articles Violated */}
                              <div className="mb-4 p-4 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
                                <div className="text-xs font-bold text-blue-800 mb-3 flex items-center gap-2">
                                  <span>⚖️</span>
                                  GDPR ARTICLES VIOLATED
                                </div>
                                <div className="space-y-2">
                                  {gdprArticles.map((gdpr, idx) => (
                                    <div
                                      key={idx}
                                      className="p-2 bg-white/70 rounded border border-blue-200"
                                    >
                                      <div className="font-semibold text-xs text-blue-900">
                                        {gdpr.article}
                                      </div>
                                      <div className="text-xs text-slate-700 mt-1">
                                        {gdpr.explanation}
                                      </div>
                                    </div>
                                  ))}
                                  {isCredit && (
                                    <div className="p-2 bg-white/70 rounded border border-orange-200">
                                      <div className="font-semibold text-xs text-orange-900">
                                        ECOA (Equal Credit Opportunity Act)
                                      </div>
                                      <div className="text-xs text-slate-700 mt-1">
                                        Prohibits discrimination in credit
                                        decisions based on protected
                                        characteristics. This bias violation may
                                        constitute illegal discrimination.
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* Recommendations */}
                              <div className="p-3 bg-gradient-to-r from-green-50 to-emerald-50 rounded-lg border border-green-200">
                                <div className="text-xs font-semibold text-green-800 mb-2">
                                  ✓ RECOMMENDED ACTIONS
                                </div>
                                <ul className="text-sm text-slate-700 space-y-1">
                                  <li className="flex items-start gap-2">
                                    <span className="text-green-600">•</span>
                                    <span>
                                      Investigate and remediate bias in the{" "}
                                      {violation.attribute} attribute
                                    </span>
                                  </li>
                                  <li className="flex items-start gap-2">
                                    <span className="text-green-600">•</span>
                                    <span>
                                      Implement fairness constraints during
                                      model training
                                    </span>
                                  </li>
                                  <li className="flex items-start gap-2">
                                    <span className="text-green-600">•</span>
                                    <span>
                                      Consider rebalancing dataset or applying
                                      bias mitigation techniques
                                    </span>
                                  </li>
                                  <li className="flex items-start gap-2">
                                    <span className="text-green-600">•</span>
                                    <span>
                                      Document fairness assessment in GDPR
                                      Article 35 DPIA (Data Protection Impact
                                      Assessment)
                                    </span>
                                  </li>
                                  {violation.severity === "HIGH" && (
                                    <li className="flex items-start gap-2">
                                      <span className="text-red-600">•</span>
                                      <span className="text-red-700 font-semibold">
                                        URGENT: This high-severity violation
                                        requires immediate attention before
                                        deployment
                                      </span>
                                    </li>
                                  )}
                                </ul>
                              </div>
                            </div>
                          );
                        },
                      )}
                    </div>
                  </div>
                )}

                {/* Key Insights */}
                <div className="p-6 bg-gradient-to-br from-blue-50 to-cyan-50 rounded-xl border border-blue-200">
                  <h3 className="font-bold text-lg mb-3 flex items-center gap-2 text-blue-900">
                    <span>💡</span>
                    Key Insights
                  </h3>
                  <ul className="space-y-2 text-sm text-slate-700">
                    <li className="flex items-start gap-2">
                      <span className="text-blue-600 mt-0.5">•</span>
                      <span>
                        <strong>
                          Bias Score{" "}
                          {(
                            analyzeResult.bias_metrics.overall_bias_score * 100
                          ).toFixed(1)}
                          %
                        </strong>{" "}
                        indicates
                        {analyzeResult.bias_metrics.overall_bias_score < 0.3
                          ? " strong fairness with minimal disparities across groups."
                          : analyzeResult.bias_metrics.overall_bias_score < 0.5
                            ? " moderate disparities that should be monitored and addressed."
                            : " significant unfairness requiring immediate remediation before deployment."}
                      </span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-blue-600 mt-0.5">•</span>
                      <span>
                        <strong>
                          Model achieves{" "}
                          {(
                            analyzeResult.model_performance.accuracy * 100
                          ).toFixed(1)}
                          % accuracy
                        </strong>
                        , but fairness metrics reveal how performance varies
                        across demographic groups.
                      </span>
                    </li>
                    {analyzeResult.bias_metrics.violations_detected.length >
                    0 ? (
                      <li className="flex items-start gap-2">
                        <span className="text-red-600 mt-0.5">•</span>
                        <span className="text-red-700">
                          <strong>
                            {
                              analyzeResult.bias_metrics.violations_detected
                                .length
                            }{" "}
                            violation(s)
                          </strong>{" "}
                          detected. Review mitigation tab for recommended
                          actions to improve fairness.
                        </span>
                      </li>
                    ) : (
                      <li className="flex items-start gap-2">
                        <span className="text-green-600 mt-0.5">•</span>
                        <span className="text-green-700">
                          <strong>No violations detected.</strong> Model meets
                          fairness thresholds across all protected attributes.
                        </span>
                      </li>
                    )}
                  </ul>
                </div>
              </div>
            ) : (
              <div className="text-center py-12">
                <div className="text-6xl mb-4">📊</div>
                <p className="text-slate-600 mb-2">No analysis results yet</p>
                <p className="text-sm text-slate-500">
                  Upload a dataset and click "Analyze" to see bias and fairness
                  metrics
                </p>
              </div>
            )}
          </div>
        );
      case "risk-analysis":
        return (
          <div className="space-y-6">
            {analyzeResult ? (
              <div className="space-y-6">
                {/* Header: RISK ANALYSIS SUMMARY */}
                <div className="relative overflow-hidden rounded-xl border-2 border-slate-300 bg-gradient-to-br from-slate-800 via-slate-700 to-slate-900 p-8 shadow-2xl">
                  <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-br from-blue-500/10 to-purple-500/10 rounded-full blur-3xl"></div>
                  <div className="relative">
                    <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-600">
                      <span className="text-4xl">🔒</span>
                      <h2 className="text-3xl font-black text-white tracking-tight">
                        RISK ANALYSIS SUMMARY
                      </h2>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      {/* Overall Risk */}
                      <div className="bg-white/10 backdrop-blur-sm rounded-xl p-5 border border-white/20">
                        <div className="text-sm font-medium text-slate-300 mb-2">
                          📊 Overall Risk
                        </div>
                        <div className="text-5xl font-black text-white mb-2">
                          {(
                            analyzeResult.risk_assessment.overall_risk_score *
                            100
                          ).toFixed(1)}
                          %
                        </div>
                        <div
                          className={`inline-flex px-3 py-1 rounded-full text-xs font-bold ${
                            analyzeResult.risk_assessment.risk_level ===
                            "CRITICAL"
                              ? "bg-red-500 text-white"
                              : analyzeResult.risk_assessment.risk_level ===
                                  "HIGH"
                                ? "bg-orange-500 text-white"
                                : analyzeResult.risk_assessment.risk_level ===
                                    "MEDIUM"
                                  ? "bg-yellow-500 text-slate-900"
                                  : "bg-green-500 text-white"
                          }`}
                        >
                          {analyzeResult.risk_assessment.risk_level}
                        </div>
                      </div>

                      {/* Presidio Status */}
                      <div className="bg-white/10 backdrop-blur-sm rounded-xl p-5 border border-white/20">
                        <div className="text-sm font-medium text-slate-300 mb-2">
                          🔒 Detection Engine
                        </div>
                        <div className="text-2xl font-bold text-white mb-2">
                          {analyzeResult.risk_assessment.presidio_enabled
                            ? "Presidio"
                            : "Regex"}
                        </div>
                        <div
                          className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold ${
                            analyzeResult.risk_assessment.presidio_enabled
                              ? "bg-blue-500 text-white"
                              : "bg-slate-600 text-slate-200"
                          }`}
                        >
                          <span
                            className={`w-2 h-2 rounded-full ${
                              analyzeResult.risk_assessment.presidio_enabled
                                ? "bg-white animate-pulse"
                                : "bg-slate-400"
                            }`}
                          ></span>
                          {analyzeResult.risk_assessment.presidio_enabled
                            ? "Enhanced"
                            : "Standard"}
                        </div>
                      </div>

                      {/* Violations */}
                      <div className="bg-white/10 backdrop-blur-sm rounded-xl p-5 border border-white/20">
                        <div className="text-sm font-medium text-slate-300 mb-2">
                          ⚠️ Violations
                        </div>
                        <div
                          className={`text-5xl font-black mb-2 ${
                            (analyzeResult.risk_assessment.violations?.length ||
                              0) > 0
                              ? "text-red-400"
                              : "text-green-400"
                          }`}
                        >
                          {analyzeResult.risk_assessment.violations?.length ||
                            0}
                        </div>
                        <div className="text-xs text-slate-300">
                          {analyzeResult.risk_assessment.violations?.filter(
                            (v: any) => v.severity === "CRITICAL",
                          ).length || 0}{" "}
                          Critical Issues
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                {/* Risk Categories Grid with Enhanced Design */}
                <div className="bg-white rounded-xl border-2 border-slate-200 p-6 shadow-lg">
                  <div className="flex items-center gap-2 mb-6">
                    <span className="text-2xl">📈</span>
                    <h3 className="text-xl font-bold text-slate-800">
                      Category Scores
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {Object.entries(
                      analyzeResult.risk_assessment.risk_categories || {},
                    ).map(([category, score]: [string, any]) => {
                      const riskPct = score * 100;
                      const riskLevel =
                        riskPct >= 70
                          ? "CRITICAL"
                          : riskPct >= 50
                            ? "HIGH"
                            : riskPct >= 30
                              ? "MEDIUM"
                              : "LOW";
                      const categoryConfig: Record<
                        string,
                        { icon: string; label: string; color: string }
                      > = {
                        privacy: { icon: "�", label: "Privacy", color: "blue" },
                        ethical: {
                          icon: "🟠",
                          label: "Ethical",
                          color: "purple",
                        },
                        compliance: {
                          icon: "�",
                          label: "Compliance",
                          color: "indigo",
                        },
                        security: {
                          icon: "�",
                          label: "Security",
                          color: "cyan",
                        },
                        operational: {
                          icon: "🟠",
                          label: "Operational",
                          color: "orange",
                        },
                        data_quality: {
                          icon: "�",
                          label: "Data Quality",
                          color: "green",
                        },
                      };

                      const config = categoryConfig[category] || {
                        icon: "📌",
                        label: category,
                        color: "slate",
                      };

                      // Dynamic emoji based on risk level
                      const riskEmoji =
                        riskPct < 25 ? "🟢" : riskPct < 50 ? "🟡" : "🟠";

                      return (
                        <div
                          key={category}
                          className={`relative overflow-hidden rounded-xl border-2 p-5 transition-all hover:shadow-xl hover:scale-105 ${
                            riskLevel === "CRITICAL"
                              ? "border-red-300 bg-gradient-to-br from-red-50 via-white to-red-50"
                              : riskLevel === "HIGH"
                                ? "border-orange-300 bg-gradient-to-br from-orange-50 via-white to-orange-50"
                                : riskLevel === "MEDIUM"
                                  ? "border-yellow-300 bg-gradient-to-br from-yellow-50 via-white to-yellow-50"
                                  : "border-green-300 bg-gradient-to-br from-green-50 via-white to-green-50"
                          }`}
                        >
                          <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-white/50 to-transparent rounded-full blur-2xl"></div>

                          <div className="relative">
                            <div className="flex items-start justify-between mb-3">
                              <span className="text-3xl">{riskEmoji}</span>
                              <span
                                className={`text-xs font-black px-2.5 py-1 rounded-full shadow-sm ${
                                  riskLevel === "CRITICAL"
                                    ? "bg-red-600 text-white"
                                    : riskLevel === "HIGH"
                                      ? "bg-orange-600 text-white"
                                      : riskLevel === "MEDIUM"
                                        ? "bg-yellow-600 text-white"
                                        : "bg-green-600 text-white"
                                }`}
                              >
                                {riskLevel}
                              </span>
                            </div>

                            <div className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-2">
                              {config.label}
                            </div>

                            <div className="text-4xl font-black bg-gradient-to-r from-slate-800 to-slate-600 bg-clip-text text-transparent mb-3">
                              {riskPct.toFixed(1)}%
                            </div>

                            {/* Progress Bar */}
                            <div className="relative h-2 bg-slate-200 rounded-full overflow-hidden shadow-inner">
                              <div
                                className={`absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-out ${
                                  riskLevel === "CRITICAL"
                                    ? "bg-gradient-to-r from-red-500 via-red-600 to-red-700"
                                    : riskLevel === "HIGH"
                                      ? "bg-gradient-to-r from-orange-500 via-orange-600 to-orange-700"
                                      : riskLevel === "MEDIUM"
                                        ? "bg-gradient-to-r from-yellow-500 via-yellow-600 to-yellow-700"
                                        : "bg-gradient-to-r from-green-500 via-green-600 to-green-700"
                                }`}
                                style={{ width: `${Math.min(riskPct, 100)}%` }}
                              >
                                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-pulse"></div>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
                {/* Risky Features Analysis - Feature-Level Risk Display */}
                {analyzeResult.risk_assessment.privacy_risks && (
                  <div className="bg-white rounded-xl border-2 border-slate-200 p-6 shadow-lg">
                    <div className="flex items-center gap-2 mb-6">
                      <span className="text-2xl">⚠️</span>
                      <h3 className="text-xl font-bold text-slate-800">
                        Risky Features & Columns
                      </h3>
                      <span className="ml-auto px-3 py-1 bg-red-100 text-red-700 rounded-full text-xs font-semibold">
                        {typeof analyzeResult.risk_assessment.privacy_risks ===
                          "object" &&
                        !Array.isArray(
                          analyzeResult.risk_assessment.privacy_risks,
                        )
                          ? analyzeResult.risk_assessment.privacy_risks
                              .pii_count || 0
                          : Array.isArray(
                                analyzeResult.risk_assessment.privacy_risks,
                              )
                            ? analyzeResult.risk_assessment.privacy_risks.length
                            : 0}{" "}
                        Risky Features Found
                      </span>
                    </div>

                    {/* Risky Features List */}
                    {typeof analyzeResult.risk_assessment.privacy_risks ===
                      "object" &&
                    !Array.isArray(
                      analyzeResult.risk_assessment.privacy_risks,
                    ) &&
                    analyzeResult.risk_assessment.privacy_risks.pii_detected &&
                    analyzeResult.risk_assessment.privacy_risks.pii_detected
                      .length > 0 ? (
                      <div className="space-y-4">
                        {/* Privacy Risk Metrics Summary */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 bg-gradient-to-br from-red-50 to-orange-50 rounded-lg border-2 border-red-200">
                          <div className="text-center">
                            <div className="text-xs text-slate-600 mb-1 font-semibold">
                              Re-Identification Risk
                            </div>
                            <div
                              className={`text-3xl font-black ${
                                (analyzeResult.risk_assessment.privacy_risks
                                  .reidentification_risk || 0) > 0.7
                                  ? "text-red-600"
                                  : (analyzeResult.risk_assessment.privacy_risks
                                        .reidentification_risk || 0) > 0.4
                                    ? "text-orange-600"
                                    : "text-green-600"
                              }`}
                            >
                              {analyzeResult.risk_assessment.privacy_risks
                                .reidentification_risk
                                ? (
                                    analyzeResult.risk_assessment.privacy_risks
                                      .reidentification_risk * 100
                                  ).toFixed(0)
                                : 0}
                              %
                            </div>
                            <div className="text-xs text-slate-500 mt-1">
                              Can individuals be identified?
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-xs text-slate-600 mb-1 font-semibold">
                              Data Minimization
                            </div>
                            <div
                              className={`text-3xl font-black ${
                                (analyzeResult.risk_assessment.privacy_risks
                                  .data_minimization_score || 0) > 0.7
                                  ? "text-green-600"
                                  : (analyzeResult.risk_assessment.privacy_risks
                                        .data_minimization_score || 0) > 0.4
                                    ? "text-orange-600"
                                    : "text-red-600"
                              }`}
                            >
                              {analyzeResult.risk_assessment.privacy_risks
                                .data_minimization_score
                                ? (
                                    analyzeResult.risk_assessment.privacy_risks
                                      .data_minimization_score * 100
                                  ).toFixed(0)
                                : 0}
                              %
                            </div>
                            <div className="text-xs text-slate-500 mt-1">
                              Collecting only necessary data
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-xs text-slate-600 mb-1 font-semibold">
                              Anonymization Level
                            </div>
                            <div
                              className={`text-sm font-black px-3 py-1 rounded-full inline-block ${
                                analyzeResult.risk_assessment.privacy_risks
                                  .anonymization_level === "FULL"
                                  ? "bg-green-100 text-green-700"
                                  : analyzeResult.risk_assessment.privacy_risks
                                        .anonymization_level === "PARTIAL"
                                    ? "bg-yellow-100 text-yellow-700"
                                    : "bg-red-100 text-red-700"
                              }`}
                            >
                              {analyzeResult.risk_assessment.privacy_risks
                                .anonymization_level || "NONE"}
                            </div>
                            <div className="text-xs text-slate-500 mt-1">
                              Protection applied
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-xs text-slate-600 mb-1 font-semibold">
                              Detection Method
                            </div>
                            <div className="text-sm font-bold text-slate-800 px-3 py-1 bg-white rounded border-2 border-slate-300 inline-block">
                              {analyzeResult.risk_assessment.privacy_risks
                                .detection_method || "Auto"}
                            </div>
                            <div className="text-xs text-slate-500 mt-1">
                              Analysis engine used
                            </div>
                          </div>
                        </div>

                        {/* Individual Risky Features */}
                        <div className="space-y-3">
                          <h4 className="font-bold text-slate-700 flex items-center gap-2">
                            <span>🔍</span> Detailed Feature Risk Analysis
                          </h4>
                          {analyzeResult.risk_assessment.privacy_risks.pii_detected.map(
                            (pii: any, idx: number) => {
                              // Map PII types to risk explanations with GDPR Article references
                              const riskExplanations: Record<
                                string,
                                {
                                  why: string;
                                  impact: string;
                                  gdprArticles: string[];
                                  actions: string[];
                                }
                              > = {
                                EMAIL_ADDRESS: {
                                  why: "Email addresses are direct identifiers that can be used to contact and track individuals across systems, creating privacy risks.",
                                  impact:
                                    "HIGH RISK: Can lead to identity theft, phishing attacks, unauthorized marketing, and privacy violations under GDPR Article 6.",
                                  gdprArticles: [
                                    "Article 4(1) - Definition of Personal Data: Email is personally identifiable information",
                                    "Article 6 - Lawful Basis Required: Processing requires consent, contract, or legitimate interest",
                                    "Article 7 - Consent Conditions: Must obtain explicit, informed consent",
                                    "Article 17 - Right to Erasure: Users can request email deletion",
                                    "Article 21 - Right to Object: Users can opt out of email processing",
                                  ],
                                  actions: [
                                    "Encrypt email addresses",
                                    "Hash or pseudonymize for analytics",
                                    "Implement consent management",
                                    "Enable right to erasure",
                                    "Provide opt-out mechanisms",
                                  ],
                                },
                                EMAIL: {
                                  why: "Email addresses are direct identifiers that can be used to contact and track individuals across systems.",
                                  impact:
                                    "HIGH RISK: Can lead to identity theft, phishing attacks, unauthorized marketing, and privacy violations.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data Definition",
                                    "Article 6 - Lawful Basis for Processing",
                                    "Article 7 - Conditions for Consent",
                                    "Article 17 - Right to Erasure",
                                  ],
                                  actions: [
                                    "Encrypt email addresses",
                                    "Implement consent management",
                                    "Enable deletion on request",
                                    "Apply data minimization",
                                  ],
                                },
                                PHONE_NUMBER: {
                                  why: "Phone numbers directly identify individuals and enable real-time contact, creating opportunities for harassment and fraud.",
                                  impact:
                                    "HIGH RISK: Enables unwanted contact, harassment, SIM swapping attacks, location tracking, and telemarketing violations.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Phone numbers identify natural persons",
                                    "Article 6 - Lawfulness of Processing: Requires lawful basis",
                                    "Article 32 - Security of Processing: Must implement appropriate security measures",
                                    "Article 21 - Right to Object to Processing",
                                    "ePrivacy Directive - Consent required for electronic communications",
                                  ],
                                  actions: [
                                    "Remove if not essential",
                                    "Apply tokenization",
                                    "Restrict access controls",
                                    "Implement call verification",
                                    "Enable number suppression",
                                  ],
                                },
                                PHONE: {
                                  why: "Phone numbers are direct personal identifiers enabling contact and tracking.",
                                  impact:
                                    "HIGH RISK: Harassment, fraud, and unauthorized marketing.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data",
                                    "Article 6 - Lawful Processing",
                                    "Article 32 - Security Measures",
                                  ],
                                  actions: [
                                    "Tokenize phone numbers",
                                    "Implement access controls",
                                    "Enable opt-out",
                                  ],
                                },
                                PERSON: {
                                  why: "Personal names are primary identifiers. Combined with other quasi-identifiers (age, location), they enable complete re-identification.",
                                  impact:
                                    "MEDIUM-HIGH RISK: When combined with location, age, or other quasi-identifiers, creates high re-identification risk violating k-anonymity.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Names identify natural persons",
                                    "Article 5(1)(c) - Data Minimization: Collect only necessary data",
                                    "Article 5(1)(e) - Storage Limitation: Keep only as long as necessary",
                                    "Article 25 - Data Protection by Design and Default",
                                    "Article 32(1)(a) - Pseudonymization and encryption requirements",
                                  ],
                                  actions: [
                                    "Use pseudonyms or IDs",
                                    "Apply k-anonymity techniques (k≥5)",
                                    "Separate name from sensitive attributes",
                                    "Implement access logging",
                                    "Apply l-diversity for protection",
                                  ],
                                },
                                NAME: {
                                  why: "Names are direct personal identifiers that enable individual identification.",
                                  impact:
                                    "MEDIUM-HIGH RISK: Re-identification when combined with other data.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data",
                                    "Article 5(1)(c) - Data Minimization",
                                    "Article 25 - Data Protection by Design",
                                  ],
                                  actions: [
                                    "Use pseudonyms",
                                    "Apply k-anonymity",
                                    "Implement access logging",
                                  ],
                                },
                                LOCATION: {
                                  why: "Location data reveals where individuals live, work, and travel, exposing personal patterns, habits, and sensitive locations (hospitals, religious sites).",
                                  impact:
                                    "HIGH RISK: Can expose home addresses, workplaces, medical facilities, places of worship, creating discrimination and stalking risks.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Location identifies individuals",
                                    "Article 9(1) - Special Categories: Location at sensitive sites reveals protected characteristics",
                                    "Article 32 - Security Measures: Encryption and access controls required",
                                    "Article 35 - Data Protection Impact Assessment: Required for location tracking",
                                    "Recital 30 - Online identifiers and location data",
                                  ],
                                  actions: [
                                    "Generalize to zip code or city level",
                                    "Apply geographic masking",
                                    "Remove precise coordinates",
                                    "Implement geofencing",
                                    "Conduct DPIA",
                                    "Apply differential privacy",
                                  ],
                                },
                                ADDRESS: {
                                  why: "Physical addresses directly identify individuals and their home locations.",
                                  impact:
                                    "HIGH RISK: Enables stalking, burglary, and privacy violations.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data",
                                    "Article 9 - Special Categories (if sensitive location)",
                                    "Article 32 - Security Measures",
                                  ],
                                  actions: [
                                    "Generalize to zip code",
                                    "Apply geographic masking",
                                    "Restrict access",
                                  ],
                                },
                                SSN: {
                                  why: "Social Security Numbers are PERMANENT unique identifiers used across critical systems (banking, taxes, healthcare, employment).",
                                  impact:
                                    "CRITICAL RISK: Enables complete identity theft, fraudulent credit, tax fraud, medical identity theft, and unauthorized government benefits access.",
                                  gdprArticles: [
                                    "Article 9(1) - Special Category Data: Often linked to health/financial data",
                                    "Article 32 - Security of Processing: Encryption, access controls, pseudonymization mandatory",
                                    "Article 33 - Breach Notification: Immediate notification required",
                                    "Article 34 - Data Subject Notification: Notify individuals of breaches",
                                    "Article 35 - Data Protection Impact Assessment: DPIA required",
                                    "Recital 75 - High risk to rights and freedoms",
                                  ],
                                  actions: [
                                    "REMOVE IMMEDIATELY if possible",
                                    "Encrypt with AES-256",
                                    "Never display in full",
                                    "Implement strict access controls",
                                    "Conduct DPIA",
                                    "Enable breach detection",
                                    "Maintain audit logs",
                                  ],
                                },
                                US_SSN: {
                                  why: "US Social Security Numbers are permanent government identifiers linked to financial, medical, employment, and government benefits.",
                                  impact:
                                    "CRITICAL RISK: Highest identity theft risk. Compromise leads to decades of fraud, financial damage, and cannot be changed.",
                                  gdprArticles: [
                                    "Article 9(1) - Special Category: Links to health and financial data",
                                    "Article 32 - Security Measures: State-of-the-art encryption required",
                                    "Article 33 - Breach Notification: 72-hour notification to supervisory authority",
                                    "Article 34 - Communication to Data Subjects: Immediate notification",
                                    "Article 35 - DPIA: Mandatory impact assessment",
                                  ],
                                  actions: [
                                    "Encrypt end-to-end with AES-256",
                                    "Use last 4 digits only for display",
                                    "Implement multi-factor authentication",
                                    "Enable breach detection",
                                    "Create comprehensive audit trails",
                                    "Apply tokenization",
                                    "Conduct annual security audits",
                                  ],
                                },
                                CREDIT_CARD: {
                                  why: "Credit card numbers provide direct access to financial accounts and purchasing power, subject to PCI-DSS and GDPR.",
                                  impact:
                                    "CRITICAL RISK: Financial fraud, unauthorized transactions, PCI-DSS violations (fines up to $500K/month), GDPR violations (4% global revenue).",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Financial identifiers",
                                    "Article 32 - Security of Processing: PCI-DSS Level 1 compliance mandatory",
                                    "Article 33 - Breach Notification: Immediate reporting required",
                                    "Article 34 - Data Subject Notification",
                                    "PCI-DSS Standards: Cannot store CVV, must tokenize",
                                  ],
                                  actions: [
                                    "Tokenize immediately",
                                    "Never store CVV/CVC",
                                    "Use PCI-compliant vault",
                                    "Implement fraud detection",
                                    "Apply end-to-end encryption",
                                    "Use 3D Secure",
                                    "Maintain PCI-DSS certification",
                                    "Conduct quarterly security scans",
                                  ],
                                },
                                CARD: {
                                  why: "Card numbers enable direct financial access.",
                                  impact:
                                    "CRITICAL RISK: Financial fraud and PCI-DSS violations.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data",
                                    "Article 32 - Security Measures",
                                    "PCI-DSS Compliance",
                                  ],
                                  actions: [
                                    "Tokenize immediately",
                                    "Use PCI-compliant vault",
                                    "Never store CVV",
                                  ],
                                },
                                IP_ADDRESS: {
                                  why: "IP addresses are online identifiers that track user behavior, reveal location, and enable device fingerprinting across websites.",
                                  impact:
                                    "MEDIUM RISK: Enables tracking across websites, reveals approximate location, can be linked to individuals, violates ePrivacy Directive.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Online identifier",
                                    "Article 6 - Lawful Basis: Requires consent or legitimate interest",
                                    "ePrivacy Directive - Consent for cookies and tracking",
                                    "Recital 30 - Online identifiers and IP addresses",
                                    "Article 21 - Right to Object to profiling",
                                  ],
                                  actions: [
                                    "Truncate last octet for IPv4",
                                    "Hash for analytics",
                                    "Implement IP anonymization",
                                    "Reduce retention period to 90 days",
                                    "Provide opt-out for tracking",
                                    "Apply differential privacy",
                                  ],
                                },
                                IP: {
                                  why: "IP addresses are online identifiers enabling tracking.",
                                  impact:
                                    "MEDIUM RISK: Cross-site tracking and location revelation.",
                                  gdprArticles: [
                                    "Article 4(1) - Online Identifier",
                                    "Article 6 - Lawful Basis",
                                    "ePrivacy Directive",
                                  ],
                                  actions: [
                                    "Truncate IP addresses",
                                    "Hash for analytics",
                                    "Reduce retention",
                                  ],
                                },
                                MEDICAL_LICENSE: {
                                  why: "Medical information is SPECIAL CATEGORY DATA under GDPR Article 9, requiring the highest level of protection due to discrimination risks.",
                                  impact:
                                    "CRITICAL RISK: Health data breach leads to discrimination, insurance denial, employment issues, severe privacy violations, and HIPAA fines.",
                                  gdprArticles: [
                                    "Article 9(1) - Special Category (Health Data): Explicit consent required",
                                    "Article 9(2)(h) - Health/social care exception",
                                    "Article 32 - Security of Processing: Encryption mandatory",
                                    "Article 35 - DPIA: Impact assessment required",
                                    "Article 25 - Data Protection by Design",
                                    "HIPAA Compliance (if applicable)",
                                  ],
                                  actions: [
                                    "Encrypt with healthcare-grade security (AES-256)",
                                    "Implement role-based access control (RBAC)",
                                    "Conduct Data Protection Impact Assessment",
                                    "Apply strict retention policies",
                                    "Ensure HIPAA compliance",
                                    "Use de-identification techniques",
                                    "Maintain comprehensive audit logs",
                                  ],
                                },
                                MEDICAL: {
                                  why: "Medical data is special category data requiring explicit consent.",
                                  impact:
                                    "CRITICAL RISK: Discrimination and severe privacy violations.",
                                  gdprArticles: [
                                    "Article 9(1) - Special Category (Health)",
                                    "Article 32 - Security",
                                    "Article 35 - DPIA Required",
                                  ],
                                  actions: [
                                    "Encrypt data",
                                    "Implement RBAC",
                                    "Conduct DPIA",
                                  ],
                                },
                                US_DRIVER_LICENSE: {
                                  why: "Driver license numbers are government-issued identifiers used for identity verification across financial, healthcare, and government systems.",
                                  impact:
                                    "HIGH RISK: Identity fraud, fake ID creation, unauthorized access to services, and DMV record access.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Government identifier",
                                    "Article 6 - Lawful Processing: Document lawful basis",
                                    "Article 32 - Security Measures: Encryption and access controls",
                                    "Article 15 - Right of Access: Individuals can request data",
                                    "Article 17 - Right to Erasure: Deletion on request",
                                  ],
                                  actions: [
                                    "Hash or encrypt license numbers",
                                    "Limit to identity verification only",
                                    "Never display in full",
                                    "Implement verification logging",
                                    "Apply pseudonymization",
                                    "Enable deletion mechanisms",
                                  ],
                                },
                                LICENSE: {
                                  why: "License numbers are government identifiers.",
                                  impact:
                                    "HIGH RISK: Identity fraud and unauthorized access.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data",
                                    "Article 6 - Lawful Processing",
                                    "Article 32 - Security",
                                  ],
                                  actions: [
                                    "Hash license numbers",
                                    "Limit to verification",
                                    "Never display in full",
                                  ],
                                },
                                US_PASSPORT: {
                                  why: "Passport numbers are international identity documents used for travel and high-security identification, recognized globally.",
                                  impact:
                                    "CRITICAL RISK: International identity fraud, unauthorized travel booking, visa fraud, and access to secure facilities.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Unique government identifier",
                                    "Article 32 - Security Measures: State-of-the-art encryption required",
                                    "Article 35 - Impact Assessment: DPIA for high-risk processing",
                                    "Article 5(1)(f) - Integrity and Confidentiality",
                                    "Cross-border data transfer regulations",
                                  ],
                                  actions: [
                                    "Encrypt with strong encryption (AES-256)",
                                    "Restrict access to authorized personnel only",
                                    "Implement tamper detection",
                                    "Apply geographic access controls",
                                    "Maintain detailed audit trails",
                                    "Use tokenization",
                                    "Implement MFA for access",
                                  ],
                                },
                                PASSPORT: {
                                  why: "Passport numbers enable international identification.",
                                  impact:
                                    "CRITICAL RISK: International fraud and unauthorized travel.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data",
                                    "Article 32 - Security Measures",
                                    "Article 35 - Impact Assessment",
                                  ],
                                  actions: [
                                    "Encrypt passports",
                                    "Restrict access",
                                    "Implement tamper detection",
                                  ],
                                },
                                US_BANK_NUMBER: {
                                  why: "Bank account numbers provide DIRECT ACCESS to financial accounts and enable ACH transfers, wire transfers, and direct debits.",
                                  impact:
                                    "CRITICAL RISK: Unauthorized withdrawals, ACH fraud, wire transfer fraud, complete account takeover, and financial ruin.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Financial identifier",
                                    "Article 32 - Security Measures: Encryption and tokenization mandatory",
                                    "Article 33 - Breach Notification: 72-hour notification",
                                    "Article 34 - Data Subject Notification: Immediate alert to account holders",
                                    "PSD2 - Strong Customer Authentication required",
                                  ],
                                  actions: [
                                    "Tokenize immediately",
                                    "Never display account numbers",
                                    "Use secure payment gateways",
                                    "Implement transaction monitoring",
                                    "Apply multi-factor authentication",
                                    "Use Strong Customer Authentication (SCA)",
                                    "Enable fraud alerts",
                                    "Encrypt at rest and in transit",
                                  ],
                                },
                                BANK_ACCOUNT: {
                                  why: "Bank account numbers enable direct financial access.",
                                  impact:
                                    "CRITICAL RISK: Financial fraud and account takeover.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data",
                                    "Article 32 - Security Measures",
                                    "Article 33 - Breach Notification",
                                  ],
                                  actions: [
                                    "Tokenize accounts",
                                    "Never display numbers",
                                    "Implement MFA",
                                  ],
                                },
                                DOB: {
                                  why: "Date of birth is a quasi-identifier that combined with other data enables re-identification and age-based discrimination.",
                                  impact:
                                    "MEDIUM-HIGH RISK: Combined with name and zip code, enables 87% re-identification rate. Age discrimination risk.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Quasi-identifier",
                                    "Article 5(1)(c) - Data Minimization: Use age ranges instead",
                                    "Article 9 - Special Categories: Can reveal protected characteristics",
                                    "Article 22 - Automated Decision-Making: Age-based profiling restrictions",
                                    "Recital 26 - Pseudonymization reduces risks",
                                  ],
                                  actions: [
                                    "Use age ranges instead of exact DOB",
                                    "Apply k-anonymity (k≥5)",
                                    "Generalize to year or month",
                                    "Separate from other identifiers",
                                    "Implement access controls",
                                    "Apply l-diversity",
                                  ],
                                },
                                ZIP_CODE: {
                                  why: "ZIP codes are geographic quasi-identifiers. Research shows 87% of US population uniquely identified by ZIP + DOB + Gender.",
                                  impact:
                                    "MEDIUM RISK: When combined with DOB and gender, enables 87% re-identification. Reveals socioeconomic status and demographics.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Quasi-identifier",
                                    "Article 5(1)(c) - Data Minimization",
                                    "Article 32(1)(a) - Pseudonymization",
                                    "Recital 26 - Anonymization techniques",
                                    "Article 25 - Data Protection by Default",
                                  ],
                                  actions: [
                                    "Generalize to first 3 digits",
                                    "Use geographic aggregation",
                                    "Apply k-anonymity",
                                    "Combine with other anonymization techniques",
                                    "Separate from name and DOB",
                                  ],
                                },
                                IBAN_CODE: {
                                  why: "IBAN (International Bank Account Number) provides access to bank accounts across European Economic Area.",
                                  impact:
                                    "CRITICAL RISK: International financial fraud, SEPA direct debit fraud, and cross-border money theft.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data",
                                    "Article 32 - Security of Processing",
                                    "Article 33 - Breach Notification",
                                    "PSD2 - Strong Customer Authentication",
                                  ],
                                  actions: [
                                    "Tokenize IBAN",
                                    "Implement SCA",
                                    "Use secure payment processors",
                                    "Enable fraud monitoring",
                                    "Apply encryption",
                                  ],
                                },
                                CRYPTO: {
                                  why: "Cryptocurrency addresses and wallets are permanent financial identifiers that cannot be changed if compromised.",
                                  impact:
                                    "CRITICAL RISK: Irreversible financial theft, no fraud protection, transaction history exposure, wallet draining.",
                                  gdprArticles: [
                                    "Article 4(1) - Personal Data: Cryptocurrency addresses can identify individuals",
                                    "Article 5(1)(f) - Security Principle",
                                    "Article 32 - Security Measures: Multi-signature and cold storage",
                                    "Article 17 - Right to Erasure: Blockchain immutability challenges",
                                  ],
                                  actions: [
                                    "Use multi-signature wallets",
                                    "Implement cold storage",
                                    "Never display private keys",
                                    "Use hardware security modules",
                                    "Apply address rotation",
                                    "Implement withdrawal limits",
                                  ],
                                },
                              };

                              // Fallback for unmapped PII types
                              const riskInfo = riskExplanations[pii.type] ||
                                riskExplanations[pii.type.toUpperCase()] || {
                                  why: "This data type contains personal information that could identify individuals or reveal sensitive patterns according to GDPR Article 4(1).",
                                  impact:
                                    "POTENTIAL RISK: May violate privacy regulations if not properly protected. Could enable tracking, profiling, or discrimination.",
                                  gdprArticles: [
                                    "Article 4(1) - Definition of Personal Data",
                                    "Article 5 - Principles: Lawfulness, Fairness, Transparency",
                                    "Article 6 - Lawful Basis Required for Processing",
                                    "Article 24 - Responsibility of the Controller",
                                    "Article 25 - Data Protection by Design and Default",
                                  ],
                                  actions: [
                                    "Review necessity of this data field",
                                    "Apply appropriate anonymization techniques",
                                    "Implement access controls and audit logging",
                                    "Document lawful basis for processing",
                                    "Conduct Privacy Impact Assessment",
                                  ],
                                };

                              return (
                                <div
                                  key={idx}
                                  className={`group relative overflow-hidden rounded-xl border-2 p-6 transition-all hover:shadow-xl ${
                                    pii.severity === "CRITICAL"
                                      ? "bg-gradient-to-br from-red-50 via-white to-red-100 border-red-400"
                                      : pii.severity === "HIGH"
                                        ? "bg-gradient-to-br from-orange-50 via-white to-orange-100 border-orange-400"
                                        : pii.severity === "MEDIUM"
                                          ? "bg-gradient-to-br from-yellow-50 via-white to-yellow-100 border-yellow-400"
                                          : "bg-gradient-to-br from-blue-50 via-white to-blue-100 border-blue-400"
                                  }`}
                                >
                                  <div className="absolute top-0 right-0 w-40 h-40 bg-white/30 rounded-full blur-3xl"></div>

                                  <div className="relative">
                                    {/* Feature Header */}
                                    <div className="flex items-start justify-between mb-4">
                                      <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-2">
                                          <span className="text-3xl">
                                            {pii.severity === "CRITICAL"
                                              ? "🔴"
                                              : pii.severity === "HIGH"
                                                ? "🟠"
                                                : pii.severity === "MEDIUM"
                                                  ? "🟡"
                                                  : "🔵"}
                                          </span>
                                          <div>
                                            <div className="font-mono text-xl font-black text-slate-800">
                                              {pii.column}
                                            </div>
                                            <div className="text-sm text-slate-600 mt-1">
                                              <span className="font-semibold">
                                                PII Type:
                                              </span>{" "}
                                              {pii.type.replace(/_/g, " ")}
                                              {pii.occurrences && (
                                                <>
                                                  <span className="mx-2">
                                                    •
                                                  </span>
                                                  <span className="font-semibold">
                                                    Found in:
                                                  </span>{" "}
                                                  {pii.occurrences} rows
                                                </>
                                              )}
                                              {pii.confidence && (
                                                <>
                                                  <span className="mx-2">
                                                    •
                                                  </span>
                                                  <span className="font-semibold">
                                                    Confidence:
                                                  </span>{" "}
                                                  {(
                                                    pii.confidence * 100
                                                  ).toFixed(0)}
                                                  %
                                                </>
                                              )}
                                            </div>
                                          </div>
                                        </div>
                                      </div>
                                      <span
                                        className={`px-4 py-2 rounded-full text-xs font-black shadow-lg ${
                                          pii.severity === "CRITICAL"
                                            ? "bg-red-600 text-white"
                                            : pii.severity === "HIGH"
                                              ? "bg-orange-600 text-white"
                                              : pii.severity === "MEDIUM"
                                                ? "bg-yellow-600 text-white"
                                                : "bg-blue-600 text-white"
                                        }`}
                                      >
                                        {pii.severity} RISK
                                      </span>
                                    </div>

                                    {/* Why is this risky? */}
                                    <div className="mb-4 p-4 bg-white rounded-lg border-2 border-slate-200">
                                      <div className="flex items-start gap-2 mb-2">
                                        <span className="text-xl">❓</span>
                                        <div className="flex-1">
                                          <div className="text-sm font-black text-slate-700 mb-2">
                                            WHY IS THIS FEATURE RISKY?
                                          </div>
                                          <p className="text-sm text-slate-700 leading-relaxed">
                                            {riskInfo.why}
                                          </p>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Impact */}
                                    <div className="mb-4 p-4 bg-gradient-to-r from-red-50 to-orange-50 rounded-lg border-2 border-red-200">
                                      <div className="flex items-start gap-2 mb-2">
                                        <span className="text-xl">⚠️</span>
                                        <div className="flex-1">
                                          <div className="text-sm font-black text-red-800 mb-2">
                                            POTENTIAL IMPACT IF EXPOSED
                                          </div>
                                          <p className="text-sm text-slate-800 leading-relaxed font-semibold">
                                            {riskInfo.impact}
                                          </p>
                                        </div>
                                      </div>
                                    </div>

                                    {/* GDPR Articles Violated */}
                                    <div className="mb-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border-2 border-blue-200">
                                      <div className="flex items-start gap-2 mb-2">
                                        <span className="text-xl">⚖️</span>
                                        <div className="flex-1">
                                          <div className="text-sm font-black text-blue-800 mb-2">
                                            GDPR ARTICLES VIOLATED / APPLICABLE
                                          </div>
                                          <div className="space-y-1">
                                            {riskInfo.gdprArticles.map(
                                              (article, i) => (
                                                <div
                                                  key={i}
                                                  className="flex items-start gap-2"
                                                >
                                                  <span className="text-blue-600 mt-1">
                                                    •
                                                  </span>
                                                  <span className="text-sm text-slate-800 font-semibold">
                                                    {article}
                                                  </span>
                                                </div>
                                              ),
                                            )}
                                          </div>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Recommended Actions */}
                                    <div className="p-4 bg-gradient-to-r from-green-50 to-emerald-50 rounded-lg border-2 border-green-300">
                                      <div className="flex items-start gap-2 mb-3">
                                        <span className="text-xl">✅</span>
                                        <div className="flex-1">
                                          <div className="text-sm font-black text-green-800 mb-2">
                                            RECOMMENDED ACTIONS TO REDUCE RISK
                                          </div>
                                          <ul className="space-y-2">
                                            {riskInfo.actions.map(
                                              (action, i) => (
                                                <li
                                                  key={i}
                                                  className="flex items-start gap-2"
                                                >
                                                  <span className="text-green-600 font-bold mt-0.5">
                                                    {i + 1}.
                                                  </span>
                                                  <span className="text-sm text-slate-800 font-medium">
                                                    {action}
                                                  </span>
                                                </li>
                                              ),
                                            )}
                                          </ul>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              );
                            },
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="text-sm text-slate-600 bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-3">
                        <span className="text-2xl">✓</span>
                        <div>
                          <div className="font-semibold text-green-800">
                            No PII Detected
                          </div>
                          <div className="text-xs text-slate-600 mt-1">
                            Dataset appears to be free of personally
                            identifiable information
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}{" "}
                {/* Violations Section with Enhanced Design */}
                {analyzeResult.risk_assessment.violations &&
                  analyzeResult.risk_assessment.violations.length > 0 && (
                    <div className="bg-gradient-to-br from-red-50 via-white to-orange-50 rounded-xl border-2 border-red-200 p-6 shadow-lg">
                      <div className="flex items-center gap-3 mb-5">
                        <span className="text-3xl">⚠️</span>
                        <h3 className="text-xl font-bold text-slate-800">
                          Violations
                        </h3>
                        <span className="ml-auto px-4 py-1.5 bg-red-600 text-white rounded-full text-sm font-black shadow-md">
                          {analyzeResult.risk_assessment.violations.length}{" "}
                          Issues Found
                        </span>
                      </div>

                      <div className="space-y-3">
                        {analyzeResult.risk_assessment.violations.map(
                          (violation: any, idx: number) => (
                            <div
                              key={idx}
                              className={`group relative overflow-hidden p-5 rounded-xl border-2 transition-all hover:shadow-lg hover:scale-[1.02] ${
                                violation.severity === "CRITICAL"
                                  ? "bg-gradient-to-r from-red-50 to-red-100 border-red-300"
                                  : violation.severity === "HIGH"
                                    ? "bg-gradient-to-r from-orange-50 to-orange-100 border-orange-300"
                                    : violation.severity === "MEDIUM"
                                      ? "bg-gradient-to-r from-yellow-50 to-yellow-100 border-yellow-300"
                                      : "bg-gradient-to-r from-blue-50 to-blue-100 border-blue-300"
                              }`}
                            >
                              <div className="absolute top-0 right-0 w-32 h-32 bg-white/20 rounded-full blur-3xl"></div>

                              <div className="relative">
                                <div className="flex items-start justify-between gap-3 mb-3">
                                  <div className="flex items-center gap-2">
                                    <span
                                      className={`text-xs font-black px-3 py-1.5 rounded-full shadow-sm ${
                                        violation.severity === "CRITICAL"
                                          ? "bg-red-600 text-white"
                                          : violation.severity === "HIGH"
                                            ? "bg-orange-600 text-white"
                                            : violation.severity === "MEDIUM"
                                              ? "bg-yellow-600 text-slate-900"
                                              : "bg-blue-600 text-white"
                                      }`}
                                    >
                                      {violation.severity}
                                    </span>
                                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                                      {violation.category}
                                    </span>
                                  </div>
                                </div>

                                <div className="flex items-start gap-3">
                                  <span className="text-2xl mt-1">
                                    {violation.severity === "CRITICAL"
                                      ? "🔴"
                                      : violation.severity === "HIGH"
                                        ? "🟠"
                                        : violation.severity === "MEDIUM"
                                          ? "🟡"
                                          : "🔵"}
                                  </span>
                                  <div className="flex-1">
                                    <div className="text-base font-bold text-slate-800 mb-1">
                                      {violation.message}
                                    </div>
                                    {violation.details && (
                                      <div className="text-sm text-slate-600 leading-relaxed">
                                        {violation.details}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ),
                        )}
                      </div>
                    </div>
                  )}
                {/* Key Insights Section with Enhanced Design */}
                {analyzeResult.risk_assessment.insights &&
                  analyzeResult.risk_assessment.insights.length > 0 && (
                    <div className="relative overflow-hidden bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-600 rounded-xl border-2 border-blue-700 p-8 shadow-2xl">
                      <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full blur-3xl"></div>
                      <div className="absolute bottom-0 left-0 w-48 h-48 bg-purple-500/10 rounded-full blur-3xl"></div>

                      <div className="relative">
                        <div className="flex items-center gap-3 mb-6">
                          <span className="text-4xl">💡</span>
                          <h3 className="text-2xl font-black text-white">
                            Key Insights
                          </h3>
                        </div>

                        <div className="space-y-3">
                          {analyzeResult.risk_assessment.insights.map(
                            (insight: string, idx: number) => (
                              <div
                                key={idx}
                                className="flex items-start gap-3 bg-white/10 backdrop-blur-sm border border-white/20 rounded-lg p-4 hover:bg-white/15 transition-all"
                              >
                                <span className="text-yellow-300 text-xl mt-0.5 flex-shrink-0">
                                  •
                                </span>
                                <span className="text-white text-sm leading-relaxed font-medium">
                                  {insight}
                                </span>
                              </div>
                            ),
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                {/* Compliance Status - Enhanced with GDPR Article Details */}
                {analyzeResult.risk_assessment.compliance_risks && (
                  <div className="bg-white rounded-xl border-2 border-slate-200 p-6 shadow-lg">
                    <div className="flex items-center gap-2 mb-6">
                      <span className="text-2xl">📋</span>
                      <h3 className="text-lg font-bold text-slate-800">
                        Regulatory Compliance Status
                      </h3>
                    </div>

                    <div className="space-y-4">
                      {Object.entries(
                        analyzeResult.risk_assessment.compliance_risks,
                      )
                        .filter(([key]) =>
                          ["gdpr", "ccpa", "hipaa", "ecoa"].includes(key),
                        )
                        .map(([regulation, data]: [string, any]) => {
                          if (!data || typeof data !== "object") return null;

                          const regulationInfo: Record<
                            string,
                            {
                              name: string;
                              description: string;
                              keyArticles: string[];
                            }
                          > = {
                            gdpr: {
                              name: "GDPR (General Data Protection Regulation)",
                              description:
                                "EU regulation protecting personal data and privacy",
                              keyArticles: [
                                "Article 5 - Principles (lawfulness, fairness, transparency, purpose limitation, data minimization)",
                                "Article 6 - Lawful basis for processing",
                                "Article 7 - Conditions for consent",
                                "Article 9 - Processing special categories of personal data",
                                "Article 15-22 - Data subject rights (access, rectification, erasure, portability)",
                                "Article 25 - Data protection by design and by default",
                                "Article 32 - Security of processing",
                                "Article 35 - Data protection impact assessment",
                              ],
                            },
                            ccpa: {
                              name: "CCPA (California Consumer Privacy Act)",
                              description:
                                "California law providing privacy rights to consumers",
                              keyArticles: [
                                "Right to Know what personal information is collected",
                                "Right to Delete personal information",
                                "Right to Opt-Out of sale of personal information",
                                "Right to Non-Discrimination for exercising CCPA rights",
                                "Notice at Collection requirements",
                              ],
                            },
                            hipaa: {
                              name: "HIPAA (Health Insurance Portability and Accountability Act)",
                              description:
                                "US regulation protecting health information",
                              keyArticles: [
                                "Privacy Rule - Protected Health Information (PHI) safeguards",
                                "Security Rule - Administrative, physical, technical safeguards",
                                "Breach Notification Rule - Incident reporting requirements",
                                "Minimum Necessary Standard - Access limitation",
                              ],
                            },
                            ecoa: {
                              name: "ECOA (Equal Credit Opportunity Act)",
                              description:
                                "US law prohibiting discrimination in credit decisions",
                              keyArticles: [
                                "Prohibition of discrimination based on protected characteristics",
                                "Adverse action notice requirements",
                                "Record retention requirements",
                                "Monitoring and reporting obligations",
                              ],
                            },
                          };

                          const info = regulationInfo[regulation] || {
                            name: regulation.toUpperCase(),
                            description: "",
                            keyArticles: [],
                          };

                          return (
                            <div
                              key={regulation}
                              className={`rounded-xl border-2 overflow-hidden ${
                                data.status === "COMPLIANT"
                                  ? "border-green-300 bg-gradient-to-br from-green-50 to-emerald-50"
                                  : data.status === "PARTIAL"
                                    ? "border-yellow-300 bg-gradient-to-br from-yellow-50 to-orange-50"
                                    : data.status === "NOT_APPLICABLE"
                                      ? "border-slate-300 bg-gradient-to-br from-slate-50 to-slate-100"
                                      : "border-red-300 bg-gradient-to-br from-red-50 to-rose-50"
                              }`}
                            >
                              {/* Header */}
                              <div
                                className={`p-4 border-b-2 ${
                                  data.status === "COMPLIANT"
                                    ? "bg-green-100 border-green-200"
                                    : data.status === "PARTIAL"
                                      ? "bg-yellow-100 border-yellow-200"
                                      : data.status === "NOT_APPLICABLE"
                                        ? "bg-slate-100 border-slate-200"
                                        : "bg-red-100 border-red-200"
                                }`}
                              >
                                <div className="flex items-center justify-between">
                                  <div>
                                    <div className="text-sm font-black text-slate-800 uppercase tracking-wide">
                                      {info.name}
                                    </div>
                                    {info.description && (
                                      <div className="text-xs text-slate-600 mt-1">
                                        {info.description}
                                      </div>
                                    )}
                                  </div>
                                  <span
                                    className={`px-4 py-2 rounded-full text-xs font-black shadow-sm ${
                                      data.status === "COMPLIANT"
                                        ? "bg-green-600 text-white"
                                        : data.status === "PARTIAL"
                                          ? "bg-yellow-600 text-white"
                                          : data.status === "NOT_APPLICABLE"
                                            ? "bg-slate-600 text-white"
                                            : "bg-red-600 text-white"
                                    }`}
                                  >
                                    {data.status === "NOT_APPLICABLE"
                                      ? "N/A"
                                      : data.status}
                                  </span>
                                </div>
                              </div>

                              {/* Content */}
                              <div className="p-4">
                                {data.applicable === false ? (
                                  <div className="text-sm text-slate-600 italic">
                                    This regulation does not appear to apply to
                                    your dataset based on detected data types.
                                  </div>
                                ) : (
                                  <div className="space-y-3">
                                    {/* Score */}
                                    {data.score !== undefined && (
                                      <div className="flex items-center gap-3">
                                        <div className="text-xs font-semibold text-slate-600">
                                          Compliance Score:
                                        </div>
                                        <div className="flex-1 h-3 bg-slate-200 rounded-full overflow-hidden">
                                          <div
                                            className={`h-full transition-all ${
                                              data.score > 0.7
                                                ? "bg-green-500"
                                                : data.score > 0.4
                                                  ? "bg-yellow-500"
                                                  : "bg-red-500"
                                            }`}
                                            style={{
                                              width: `${data.score * 100}%`,
                                            }}
                                          ></div>
                                        </div>
                                        <div className="text-sm font-bold text-slate-800">
                                          {(data.score * 100).toFixed(0)}%
                                        </div>
                                      </div>
                                    )}

                                    {/* Compliant Checks */}
                                    {data.compliant_checks &&
                                      data.compliant_checks.length > 0 && (
                                        <div>
                                          <div className="text-xs font-semibold text-green-700 mb-2">
                                            ✓ Compliant Areas:
                                          </div>
                                          <div className="flex flex-wrap gap-2">
                                            {data.compliant_checks.map(
                                              (check: string, idx: number) => (
                                                <span
                                                  key={idx}
                                                  className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded border border-green-200"
                                                >
                                                  {check.replace(/_/g, " ")}
                                                </span>
                                              ),
                                            )}
                                          </div>
                                        </div>
                                      )}

                                    {/* Non-Compliant Checks */}
                                    {data.non_compliant_checks &&
                                      data.non_compliant_checks.length > 0 && (
                                        <div>
                                          <div className="text-xs font-semibold text-red-700 mb-2">
                                            ⚠️ Non-Compliant Areas:
                                          </div>
                                          <div className="flex flex-wrap gap-2">
                                            {data.non_compliant_checks.map(
                                              (check: string, idx: number) => (
                                                <span
                                                  key={idx}
                                                  className="px-2 py-1 bg-red-100 text-red-800 text-xs rounded border border-red-200"
                                                >
                                                  {check.replace(/_/g, " ")}
                                                </span>
                                              ),
                                            )}
                                          </div>
                                        </div>
                                      )}

                                    {/* Key Articles/Requirements */}
                                    {info.keyArticles.length > 0 && (
                                      <details className="mt-3">
                                        <summary className="text-xs font-semibold text-blue-700 cursor-pointer hover:text-blue-900">
                                          📖 View Key Requirements & Articles
                                        </summary>
                                        <div className="mt-2 pl-4 space-y-2">
                                          {info.keyArticles.map(
                                            (article, idx) => (
                                              <div
                                                key={idx}
                                                className="flex items-start gap-2"
                                              >
                                                <span className="text-blue-600 text-xs mt-0.5">
                                                  •
                                                </span>
                                                <span className="text-xs text-slate-700">
                                                  {article}
                                                </span>
                                              </div>
                                            ),
                                          )}
                                        </div>
                                      </details>
                                    )}

                                    {/* Bias Score for ECOA */}
                                    {regulation === "ecoa" &&
                                      data.bias_score !== undefined && (
                                        <div className="mt-3 p-3 bg-white rounded border border-slate-200">
                                          <div className="text-xs font-semibold text-slate-600 mb-1">
                                            Bias Score (Discrimination Risk):
                                          </div>
                                          <div className="flex items-center gap-3">
                                            <div className="flex-1 h-3 bg-slate-200 rounded-full overflow-hidden">
                                              <div
                                                className={`h-full transition-all ${
                                                  data.bias_score < 0.3
                                                    ? "bg-green-500"
                                                    : data.bias_score < 0.5
                                                      ? "bg-yellow-500"
                                                      : "bg-red-500"
                                                }`}
                                                style={{
                                                  width: `${data.bias_score * 100}%`,
                                                }}
                                              ></div>
                                            </div>
                                            <div
                                              className={`text-sm font-bold ${
                                                data.bias_score < 0.3
                                                  ? "text-green-600"
                                                  : data.bias_score < 0.5
                                                    ? "text-yellow-600"
                                                    : "text-red-600"
                                              }`}
                                            >
                                              {(data.bias_score * 100).toFixed(
                                                1,
                                              )}
                                              %
                                            </div>
                                          </div>
                                          <div className="text-xs text-slate-600 mt-1">
                                            {data.bias_score < 0.3
                                              ? "Low discrimination risk"
                                              : data.bias_score < 0.5
                                                ? "Moderate discrimination risk - monitor closely"
                                                : "High discrimination risk - immediate remediation required"}
                                          </div>
                                        </div>
                                      )}
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                    </div>

                    {/* Compliance Recommendations */}
                    {analyzeResult.risk_assessment.compliance_risks
                      .recommendations &&
                      analyzeResult.risk_assessment.compliance_risks
                        .recommendations.length > 0 && (
                        <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
                          <div className="text-sm font-bold text-blue-900 mb-3">
                            📌 Compliance Recommendations
                          </div>
                          <div className="space-y-2">
                            {analyzeResult.risk_assessment.compliance_risks.recommendations.map(
                              (rec: any, idx: number) => (
                                <div
                                  key={idx}
                                  className="flex items-start gap-3 p-3 bg-white rounded border border-blue-200"
                                >
                                  <span
                                    className={`px-2 py-0.5 text-xs font-bold rounded ${
                                      rec.priority === "CRITICAL"
                                        ? "bg-red-600 text-white"
                                        : rec.priority === "HIGH"
                                          ? "bg-orange-600 text-white"
                                          : rec.priority === "MEDIUM"
                                            ? "bg-yellow-600 text-white"
                                            : "bg-blue-600 text-white"
                                    }`}
                                  >
                                    {rec.priority}
                                  </span>
                                  <div className="flex-1">
                                    <div className="text-sm font-semibold text-slate-800">
                                      {rec.recommendation}
                                    </div>
                                    {rec.rationale && (
                                      <div className="text-xs text-slate-600 mt-1">
                                        {rec.rationale}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ),
                            )}
                          </div>
                        </div>
                      )}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12 bg-slate-50 rounded-xl border-2 border-dashed border-slate-300">
                <span className="text-4xl mb-3 block">🔒</span>
                <p className="text-slate-600 mb-2">
                  No risk analysis results yet
                </p>
                <p className="text-sm text-slate-500">
                  Upload a dataset and click "Analyze" to see comprehensive risk
                  assessment
                </p>
              </div>
            )}
          </div>
        );
      case "bias-risk-mitigation":
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-2xl font-bold mb-2">
                PII Detection & Anonymization Strategy
              </h2>
              <p className="text-sm text-slate-600">
                Review detected risky features and choose how to anonymize them
              </p>
            </div>

            {piiDetectionResult ? (
              <div className="space-y-6">
                {/* File Info Banner */}
                <div className="p-3 bg-slate-100 border border-slate-300 rounded-lg text-sm">
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-slate-700">File:</span>
                    <code className="px-2 py-1 bg-white rounded border border-slate-200">
                      {piiDetectionResult.filename}
                    </code>
                    <span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs font-semibold rounded">
                      {piiDetectionResult.file_type.toUpperCase()}
                    </span>
                    <span className="text-slate-600">
                      {piiDetectionResult.dataset_info.rows} rows ×{" "}
                      {piiDetectionResult.dataset_info.columns} columns
                    </span>
                  </div>
                </div>

                {/* Summary Card */}
                <div className="p-6 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl border-2 border-blue-200">
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div>
                      <div className="text-xs font-semibold text-blue-700 mb-1">
                        TOTAL COLUMNS SCANNED
                      </div>
                      <div className="text-3xl font-bold text-blue-900">
                        {piiDetectionResult.summary.total_columns_scanned}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-red-700 mb-1">
                        HIGH RISK
                      </div>
                      <div className="text-3xl font-bold text-red-900">
                        {piiDetectionResult.summary.high_risk_count}
                      </div>
                      <div className="text-xs text-slate-600">Must remove</div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-orange-700 mb-1">
                        MEDIUM RISK
                      </div>
                      <div className="text-3xl font-bold text-orange-900">
                        {piiDetectionResult.summary.medium_risk_count}
                      </div>
                      <div className="text-xs text-slate-600">
                        Hash recommended
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-yellow-700 mb-1">
                        LOW RISK
                      </div>
                      <div className="text-3xl font-bold text-yellow-900">
                        {piiDetectionResult.summary.low_risk_count}
                      </div>
                      <div className="text-xs text-slate-600">
                        Mask/generalize
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 p-3 bg-white/70 rounded-lg text-sm text-slate-700">
                    {piiDetectionResult.message}
                  </div>
                </div>

                {/* Risky Features List */}
                <div className="space-y-3">
                  {piiDetectionResult.risky_features.map((feature, idx) => {
                    const riskColor =
                      feature.risk_level === "HIGH"
                        ? "red"
                        : feature.risk_level === "MEDIUM"
                          ? "orange"
                          : feature.risk_level === "LOW"
                            ? "yellow"
                            : "gray";

                    const bgColor =
                      feature.risk_level === "HIGH"
                        ? "bg-red-50 border-red-300"
                        : feature.risk_level === "MEDIUM"
                          ? "bg-orange-50 border-orange-300"
                          : feature.risk_level === "LOW"
                            ? "bg-yellow-50 border-yellow-300"
                            : "bg-gray-50 border-gray-300";

                    return (
                      <div
                        key={idx}
                        className={`p-5 rounded-xl border-2 ${bgColor}`}
                      >
                        {/* Header */}
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex-1">
                            <div className="flex items-center gap-3 mb-2">
                              <span
                                className={`px-3 py-1 bg-${riskColor}-600 text-white text-xs font-bold rounded-full`}
                              >
                                {feature.risk_level} RISK
                              </span>
                              <span className="font-mono font-bold text-lg text-slate-800">
                                {feature.column}
                              </span>
                            </div>
                            <div className="text-sm text-slate-700">
                              <span className="font-semibold">Detected:</span>{" "}
                              {feature.entity_type}
                              <span className="mx-2">•</span>
                              <span className="font-semibold">
                                Confidence:
                              </span>{" "}
                              {(feature.confidence * 100).toFixed(1)}%
                              <span className="mx-2">•</span>
                              <span className="font-semibold">
                                Occurrences:
                              </span>{" "}
                              {feature.detection_count}
                            </div>
                          </div>
                        </div>

                        {/* Explanation */}
                        <div className="p-4 bg-white rounded-lg mb-4">
                          <div className="text-xs font-semibold text-slate-600 mb-2">
                            WHY IS THIS RISKY?
                          </div>
                          <p className="text-sm text-slate-700 leading-relaxed">
                            {feature.explanation}
                          </p>
                          <div className="mt-3 text-xs text-slate-600">
                            <strong>GDPR Reference:</strong>{" "}
                            {feature.gdpr_article}
                          </div>
                        </div>

                        {/* Sample Values */}
                        {feature.sample_values.length > 0 && (
                          <div className="p-4 bg-white rounded-lg mb-4">
                            <div className="text-xs font-semibold text-slate-600 mb-2">
                              SAMPLE VALUES
                            </div>
                            <div className="flex gap-2 flex-wrap">
                              {feature.sample_values.map((val, i) => (
                                <code
                                  key={i}
                                  className="px-2 py-1 bg-slate-100 rounded text-xs text-slate-800 border border-slate-200"
                                >
                                  {val}
                                </code>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Recommended Strategy */}
                        <div className="p-4 bg-white rounded-lg border-2 border-green-300">
                          <div className="flex items-start gap-3">
                            <div className="flex-1">
                              <div className="text-xs font-semibold text-green-700 mb-1">
                                ✓ RECOMMENDED STRATEGY
                              </div>
                              <div className="font-bold text-lg text-slate-900">
                                {feature.recommended_strategy}
                              </div>
                              <div className="text-sm text-slate-700 mt-1">
                                {feature.strategy_description}
                              </div>
                              <div className="mt-2 flex gap-4 text-xs text-slate-600">
                                <div>
                                  <strong>Reversible:</strong>{" "}
                                  {feature.reversible ? "Yes" : "No"}
                                </div>
                                <div>
                                  <strong>Use Cases:</strong>{" "}
                                  {feature.use_cases.join(", ")}
                                </div>
                              </div>
                            </div>
                            <button
                              className="px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-500"
                              onClick={() =>
                                alert(
                                  `Apply ${feature.recommended_strategy} to ${feature.column}`,
                                )
                              }
                            >
                              Apply
                            </button>
                          </div>
                        </div>

                        {/* Alternative Strategies */}
                        <details className="mt-3">
                          <summary className="text-xs font-semibold text-slate-600 cursor-pointer hover:text-slate-800">
                            View Alternative Strategies
                          </summary>
                          <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                            {Object.entries(
                              piiDetectionResult.available_strategies,
                            )
                              .filter(
                                ([strategy]) =>
                                  strategy !== feature.recommended_strategy,
                              )
                              .map(([strategy, details]: [string, any]) => (
                                <div
                                  key={strategy}
                                  className="p-3 bg-white rounded border border-slate-200 hover:border-slate-400"
                                >
                                  <div className="font-semibold text-sm text-slate-800">
                                    {strategy}
                                  </div>
                                  <div className="text-xs text-slate-600 mt-1">
                                    {details.description}
                                  </div>
                                  <div className="mt-2 flex items-center justify-between">
                                    <span
                                      className={`px-2 py-0.5 text-xs rounded ${
                                        details.risk_level === "HIGH"
                                          ? "bg-red-100 text-red-800"
                                          : details.risk_level === "MEDIUM"
                                            ? "bg-orange-100 text-orange-800"
                                            : "bg-yellow-100 text-yellow-800"
                                      }`}
                                    >
                                      {details.risk_level} Risk
                                    </span>
                                    <button
                                      className="px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-500"
                                      onClick={() =>
                                        alert(
                                          `Apply ${strategy} to ${feature.column}`,
                                        )
                                      }
                                    >
                                      Use This
                                    </button>
                                  </div>
                                </div>
                              ))}
                          </div>
                        </details>
                      </div>
                    );
                  })}
                </div>

                {/* Apply All Button */}
                <div className="sticky bottom-0 p-4 bg-gradient-to-t from-white via-white to-transparent">
                  <button
                    className="w-full py-3 bg-green-600 text-white font-bold rounded-lg hover:bg-green-500 shadow-lg"
                    onClick={() =>
                      alert(
                        "Apply all recommended strategies and clean dataset",
                      )
                    }
                  >
                    ✓ Apply All Recommended Strategies & Clean Dataset
                  </button>
                </div>
              </div>
            ) : (
              <div className="text-center py-12">
                <div className="text-6xl mb-4">🔍</div>
                <p className="text-slate-600 mb-2">
                  No PII detection results yet
                </p>
                <p className="text-sm text-slate-500">
                  Upload a dataset and click "🔍 Detect PII" to scan for risky
                  features
                </p>
              </div>
            )}
          </div>
        );
      case "results":
        return (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Results Summary</h2>
            {analyzeResult || cleanResult ? (
              <div className="space-y-4">
                {analyzeResult && (
                  <div className="p-4 bg-white rounded-lg border">
                    <h3 className="font-semibold mb-2">Analysis Results</h3>
                    <div className="text-sm space-y-1">
                      <div>Dataset: {analyzeResult.filename}</div>
                      <div>Rows: {analyzeResult.dataset_info.rows}</div>
                      <div>Columns: {analyzeResult.dataset_info.columns}</div>
                      <div>
                        Bias Score:{" "}
                        {(
                          analyzeResult.bias_metrics.overall_bias_score * 100
                        ).toFixed(1)}
                        %
                      </div>
                      <div>
                        Risk Score:{" "}
                        {(
                          analyzeResult.risk_assessment.overall_risk_score * 100
                        ).toFixed(1)}
                        %
                      </div>
                    </div>
                    <a
                      href={getReportUrl(analyzeResult.report_file)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-3 inline-block text-sm text-brand-600 underline"
                    >
                      Download Full Report →
                    </a>
                  </div>
                )}

                {cleanResult && (
                  <div className="p-4 bg-white rounded-lg border">
                    <h3 className="font-semibold mb-2">Cleaning Results</h3>
                    <div className="text-sm space-y-1">
                      <div>
                        Original: {cleanResult.dataset_info.original_rows} rows
                        × {cleanResult.dataset_info.original_columns} cols
                      </div>
                      <div>
                        Cleaned: {cleanResult.dataset_info.cleaned_rows} rows ×{" "}
                        {cleanResult.dataset_info.cleaned_columns} cols
                      </div>
                      <div>
                        Cells Anonymized:{" "}
                        {cleanResult.summary.total_cells_affected}
                      </div>
                      <div>
                        Columns Removed:{" "}
                        {cleanResult.summary.columns_removed.length}
                      </div>
                      <div>
                        GDPR Compliant: {cleanResult.gdpr_compliance.length}{" "}
                        articles applied
                      </div>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <a
                        href={getReportUrl(cleanResult.files.cleaned_csv)}
                        download
                        className="text-sm text-brand-600 underline"
                      >
                        Download Cleaned CSV →
                      </a>
                      <a
                        href={getReportUrl(cleanResult.files.audit_report)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-brand-600 underline"
                      >
                        View Audit Report →
                      </a>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-slate-600">
                Process a dataset to see aggregated results.
              </p>
            )}
          </div>
        );
      default:
        return null;
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-white/60">
      {renderTabContent()}
    </div>
  );
}
