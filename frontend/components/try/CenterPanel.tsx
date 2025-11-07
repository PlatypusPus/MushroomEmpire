"use client";
import { TryTab } from "./Sidebar";
import { useState, useRef, useCallback, useEffect } from "react";
import { saveLatestUpload, getLatestUpload, deleteLatestUpload } from "../../lib/indexeddb";
import { analyzeDataset, cleanDataset, detectPII, getReportUrl, type AnalyzeResponse, type CleanResponse, type DetectPIIResponse } from "../../lib/api";

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
	origin: 'csv';
}

export function CenterPanel({ tab, onAnalyze }: CenterPanelProps) {
	const PREVIEW_BYTES = 64 * 1024; // read first 64KB slice for large-file preview
	const [fileMeta, setFileMeta] = useState<UploadedFileMeta | null>(null);
	const [uploadedFile, setUploadedFile] = useState<File | null>(null);
	const [isDragging, setIsDragging] = useState(false);
	const [progress, setProgress] = useState<number>(0);
	const [progressLabel, setProgressLabel] = useState<string>("Processing");
	const [tablePreview, setTablePreview] = useState<TablePreviewData | null>(null);
	const inputRef = useRef<HTMLInputElement | null>(null);
	const [loadedFromCache, setLoadedFromCache] = useState(false);
	const [isProcessing, setIsProcessing] = useState(false);
	const [error, setError] = useState<string | null>(null);
	
	// Analysis results
	const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResponse | null>(null);
	const [cleanResult, setCleanResult] = useState<CleanResponse | null>(null);
	const [piiDetectionResult, setPIIDetectionResult] = useState<DetectPIIResponse | null>(null);

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
	};		function tryParseCSV(text: string, maxRows = 50, maxCols = 40): TablePreviewData | null {
			const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
			if (lines.length < 2) return null;
			const commaDensity = lines.slice(0, 10).filter(l => l.includes(',')).length;
			if (commaDensity < 2) return null;
			const parseLine = (line: string) => {
				const out: string[] = [];
				let cur = '';
				let inQuotes = false;
				for (let i = 0; i < line.length; i++) {
					const ch = line[i];
					if (ch === '"') {
						if (inQuotes && line[i + 1] === '"') { cur += '"'; i++; } else { inQuotes = !inQuotes; }
					} else if (ch === ',' && !inQuotes) {
						out.push(cur);
						cur = '';
					} else { cur += ch; }
				}
				out.push(cur);
				return out.map(c => c.trim());
			};
			const raw = lines.slice(0, maxRows).map(parseLine);
			if (raw.length === 0) return null;
			const headers = raw[0];
			const colCount = Math.min(headers.length, maxCols);
			const rows = raw.slice(1).map(r => r.slice(0, colCount));
			return { headers: headers.slice(0, colCount), rows, origin: 'csv' };
		}

		// We no longer build table preview for JSON; revert JSON to raw text view.

	const processFile = useCallback(async (f: File) => {
		if (!f) return;
		const isCSV = /\.csv$/i.test(f.name);
		setProgress(0);
		setUploadedFile(f); // Save the file for API calls
		
		// For large files, show a progress bar while reading the file stream (no preview)
		if (f.size > 1024 * 1024) {
				setProgressLabel("Uploading");
				const metaObj: UploadedFileMeta = {
					name: f.name,
					size: f.size,
					type: f.type || "unknown",
					contentPreview: `Loading partial preview (first ${Math.round(PREVIEW_BYTES/1024)}KB)...`,
				};
				setFileMeta(metaObj);
				setTablePreview(null);
				// Save to IndexedDB immediately so it persists without needing full read
				(async () => {
					try { await saveLatestUpload(f, metaObj); } catch {}
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
							setFileMeta(prev => prev ? { ...prev, contentPreview: text.slice(0, 4000) } : prev);
							if (isCSV) {
								const parsed = tryParseCSV(text);
								setTablePreview(parsed);
							} else {
								setTablePreview(null);
							}
							try { await saveLatestUpload(f, { ...metaObj, contentPreview: text.slice(0, 4000) }); } catch {}
						} catch { /* ignore */ }
					};
					headReader.readAsArrayBuffer(headBlob);
				} catch { /* ignore */ }
				// Use streaming read for progress without buffering entire file in memory
				try {
					const stream: ReadableStream<Uint8Array> | undefined = (typeof (f as any).stream === "function" ? (f as any).stream() : undefined);
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
								const pct = Math.min(100, Math.round((evt.loaded / evt.total) * 100));
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
	}, [tab]);	function renderTabContent() {
			switch (tab) {
			case "processing":
					return (
						<div className="space-y-4 max-w-[1100px] xl:max-w-[1200px] w-full mx-auto">
						<h2 className="text-xl font-semibold">Upload & Process Data</h2>
						<p className="text-sm text-slate-600">Upload a CSV / JSON / text file. We will later parse, detect PII, and queue analyses.</p>
									<div className="flex flex-col gap-3 min-w-0">
										<div
											onDragOver={onDragOver}
											onDragLeave={onDragLeave}
											onDrop={onDrop}
											className={
												"rounded-lg border-2 border-dashed p-6 text-center transition-colors " +
												(isDragging ? "border-brand-600 bg-brand-50" : "border-slate-300 hover:border-brand-300")
											}
										>
											<p className="text-sm text-slate-600">Drag & drop a CSV / JSON / TXT here, or click to browse.</p>
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
												<div className="mt-1 text-xs text-slate-500">{progressLabel} {progress}%</div>
											</div>
										)}
											{fileMeta && (
								<div className="rounded-md border border-slate-200 p-4 bg-white shadow-sm">
									<div className="flex items-center justify-between mb-2">
										<div className="text-sm font-medium">{fileMeta.name}</div>
										<div className="text-xs text-slate-500">{Math.round(fileMeta.size / 1024)} KB</div>
									</div>
													{loadedFromCache && (
														<div className="mb-2 text-[11px] text-brand-700">Loaded from browser cache</div>
													)}
												<div className="mb-3 text-xs text-slate-500">{fileMeta.type || "Unknown type"}</div>
												{/* Table preview when structured data detected; otherwise show text */}
												{tablePreview && tablePreview.origin === 'csv' ? (
													<div className="max-h-64 w-full min-w-0 overflow-x-auto overflow-y-auto rounded-md bg-slate-50">
														<table className="min-w-full text-xs">
															<thead className="sticky top-0 bg-slate-100">
																<tr>
																	{tablePreview.headers.map((h, idx) => (
																		<th key={idx} className="text-left font-semibold px-3 py-2 border-b border-slate-200 whitespace-nowrap">{h}</th>
																	))}
																</tr>
															</thead>
															<tbody>
																{tablePreview.rows.map((r, i) => (
																	<tr key={i} className={i % 2 === 0 ? "" : "bg-slate-100/50"}>
																		{r.map((c, j) => (
																			<td key={j} className="px-3 py-1.5 border-b border-slate-100 whitespace-nowrap max-w-[24ch] overflow-hidden text-ellipsis">{c}</td>
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
														🔍 PII Detection complete! Found {piiDetectionResult.summary.risky_columns_found} risky columns in {piiDetectionResult.file_type.toUpperCase()} file.
														<div className="mt-1 text-xs">
															<span className="font-semibold text-red-700">{piiDetectionResult.summary.high_risk_count} HIGH</span> • 
															<span className="font-semibold text-orange-600 ml-1">{piiDetectionResult.summary.medium_risk_count} MEDIUM</span> • 
															<span className="font-semibold text-yellow-600 ml-1">{piiDetectionResult.summary.low_risk_count} LOW</span>
														</div>
														<p className="mt-2 text-xs">Review detected risks in the "Bias & Risk Mitigation" tab to choose anonymization strategies.</p>
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
														✅ Cleaning complete! {cleanResult.summary.total_cells_affected} cells anonymized.
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
																try { await deleteLatestUpload(); } catch {}
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
							<h2 className="text-2xl font-bold mb-2">Bias & Fairness Analysis</h2>
							<p className="text-sm text-slate-600">Comprehensive evaluation of algorithmic fairness across demographic groups</p>
						</div>
						
						{analyzeResult ? (
							<div className="space-y-6">
								{/* Overall Bias Score Card */}
								<div className="p-6 bg-gradient-to-br from-purple-50 to-indigo-50 rounded-xl border-2 border-purple-200">
									<div className="flex items-start justify-between">
										<div>
											<div className="text-sm font-medium text-purple-700 mb-1">Overall Bias Score</div>
											<div className="text-5xl font-bold text-purple-900">
												{(analyzeResult.bias_metrics.overall_bias_score * 100).toFixed(1)}%
											</div>
											<div className="mt-3 flex items-center gap-2">
												{analyzeResult.bias_metrics.overall_bias_score < 0.3 ? (
													<>
														<span className="px-3 py-1 bg-green-100 text-green-800 text-xs font-semibold rounded-full">
															✓ Low Bias
														</span>
														<span className="text-sm text-slate-600">Excellent fairness</span>
													</>
												) : analyzeResult.bias_metrics.overall_bias_score < 0.5 ? (
													<>
														<span className="px-3 py-1 bg-yellow-100 text-yellow-800 text-xs font-semibold rounded-full">
															⚠ Moderate Bias
														</span>
														<span className="text-sm text-slate-600">Monitor recommended</span>
													</>
												) : (
													<>
														<span className="px-3 py-1 bg-red-100 text-red-800 text-xs font-semibold rounded-full">
															✗ High Bias
														</span>
														<span className="text-sm text-slate-600">Action required</span>
													</>
												)}
											</div>
										</div>
										<div className="text-right">
											<div className="text-sm text-slate-600 mb-1">Violations</div>
											<div className={`text-3xl font-bold ${analyzeResult.bias_metrics.violations_detected.length > 0 ? 'text-red-600' : 'text-green-600'}`}>
												{analyzeResult.bias_metrics.violations_detected.length}
											</div>
										</div>
									</div>
									
									{/* Interpretation */}
									<div className="mt-4 p-4 bg-white/70 rounded-lg">
										<div className="text-xs font-semibold text-purple-800 mb-1">INTERPRETATION</div>
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
											<div className="text-xs text-blue-700 font-semibold mb-1">ACCURACY</div>
											<div className="text-2xl font-bold text-blue-900">{(analyzeResult.model_performance.accuracy * 100).toFixed(1)}%</div>
											<div className="text-xs text-slate-600 mt-1">Overall correctness</div>
										</div>
										<div className="p-4 bg-green-50 rounded-lg">
											<div className="text-xs text-green-700 font-semibold mb-1">PRECISION</div>
											<div className="text-2xl font-bold text-green-900">{(analyzeResult.model_performance.precision * 100).toFixed(1)}%</div>
											<div className="text-xs text-slate-600 mt-1">Positive prediction accuracy</div>
										</div>
										<div className="p-4 bg-purple-50 rounded-lg">
											<div className="text-xs text-purple-700 font-semibold mb-1">RECALL</div>
											<div className="text-2xl font-bold text-purple-900">{(analyzeResult.model_performance.recall * 100).toFixed(1)}%</div>
											<div className="text-xs text-slate-600 mt-1">True positive detection rate</div>
										</div>
										<div className="p-4 bg-orange-50 rounded-lg">
											<div className="text-xs text-orange-700 font-semibold mb-1">F1 SCORE</div>
											<div className="text-2xl font-bold text-orange-900">{(analyzeResult.model_performance.f1_score * 100).toFixed(1)}%</div>
											<div className="text-xs text-slate-600 mt-1">Balanced metric</div>
										</div>
									</div>
								</div>

								{/* Fairness Metrics */}
								{Object.keys(analyzeResult.bias_metrics.disparate_impact).length > 0 && (
									<div className="p-6 bg-white rounded-xl border border-slate-200 shadow-sm">
										<h3 className="font-bold text-lg mb-4 flex items-center gap-2">
											<span className="text-purple-600">⚖️</span>
											Fairness Metrics by Protected Attribute
										</h3>
										
										{Object.entries(analyzeResult.bias_metrics.disparate_impact).map(([attr, metrics]: [string, any]) => (
											<div key={attr} className="mb-6 last:mb-0 p-4 bg-slate-50 rounded-lg">
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
																<div className="text-xs font-semibold text-slate-600">DISPARATE IMPACT RATIO</div>
																<div className="text-2xl font-bold text-slate-900">{metrics.disparate_impact.value.toFixed(3)}</div>
															</div>
															<div className={`px-3 py-1 rounded-full text-xs font-semibold ${
																metrics.disparate_impact.fair ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
															}`}>
																{metrics.disparate_impact.fair ? '✓ FAIR' : '✗ UNFAIR'}
															</div>
														</div>
														<div className="text-xs text-slate-600 mb-2">{metrics.disparate_impact.interpretation || 'Ratio of positive rates between groups'}</div>
														<div className="text-xs text-slate-500 bg-blue-50 p-2 rounded">
															<strong>Fair Range:</strong> {metrics.disparate_impact.threshold || 0.8} - {(1/(metrics.disparate_impact.threshold || 0.8)).toFixed(2)} 
															{metrics.disparate_impact.fair 
																? " • This ratio indicates balanced treatment across groups." 
																: " • Ratio outside fair range suggests one group receives significantly different outcomes."}
														</div>
													</div>
												)}
												
												{/* Statistical Parity */}
												{metrics?.statistical_parity_difference?.value !== undefined && (
													<div className="mb-3 p-3 bg-white rounded border border-slate-200">
														<div className="flex items-center justify-between mb-2">
															<div>
																<div className="text-xs font-semibold text-slate-600">STATISTICAL PARITY DIFFERENCE</div>
																<div className="text-2xl font-bold text-slate-900">
																	{metrics.statistical_parity_difference.value.toFixed(3)}
																</div>
															</div>
															<div className={`px-3 py-1 rounded-full text-xs font-semibold ${
																metrics.statistical_parity_difference.fair ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
															}`}>
																{metrics.statistical_parity_difference.fair ? '✓ FAIR' : '✗ UNFAIR'}
															</div>
														</div>
														<div className="text-xs text-slate-600 mb-2">{metrics.statistical_parity_difference.interpretation || 'Difference in positive rates'}</div>
														<div className="text-xs text-slate-500 bg-blue-50 p-2 rounded">
															<strong>Fair Threshold:</strong> ±{metrics.statistical_parity_difference.threshold || 0.1} 
															{metrics.statistical_parity_difference.fair 
																? " • Difference within acceptable range for equal treatment." 
																: " • Significant difference in positive outcome rates between groups."}
														</div>
													</div>
												)}
												
												{/* Group Metrics */}
												{metrics.group_metrics && (
													<div className="p-3 bg-white rounded border border-slate-200">
														<div className="text-xs font-semibold text-slate-600 mb-2">GROUP PERFORMANCE</div>
														<div className="grid grid-cols-1 md:grid-cols-2 gap-2">
															{Object.entries(metrics.group_metrics).map(([group, groupMetrics]: [string, any]) => (
																<div key={group} className="p-2 bg-slate-50 rounded">
																	<div className="font-medium text-sm text-slate-800">{group}</div>
																	<div className="text-xs text-slate-600 mt-1">
																		<div>Positive Rate: <strong>{groupMetrics.positive_rate !== undefined ? (groupMetrics.positive_rate * 100).toFixed(1) : 'N/A'}%</strong></div>
																		<div>Sample Size: <strong>{groupMetrics.sample_size ?? 'N/A'}</strong></div>
																		{groupMetrics.tpr !== undefined && <div>True Positive Rate: <strong>{(groupMetrics.tpr * 100).toFixed(1)}%</strong></div>}
																	</div>
																</div>
															))}
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
										<div className="space-y-3">
											{analyzeResult.bias_metrics.violations_detected.map((violation: any, i: number) => (
												<div key={i} className="p-4 bg-white rounded-lg border border-red-200">
													<div className="flex items-start gap-3">
														<span className={`px-2 py-1 rounded text-xs font-bold ${
															violation.severity === 'HIGH' ? 'bg-red-600 text-white' :
															violation.severity === 'MEDIUM' ? 'bg-orange-500 text-white' :
															'bg-yellow-500 text-white'
														}`}>
															{violation.severity}
														</span>
														<div className="flex-1">
															<div className="font-semibold text-slate-900">{violation.attribute}: {violation.metric}</div>
															<div className="text-sm text-slate-700 mt-1">{violation.message}</div>
															{violation.details && (
																<div className="text-xs text-slate-500 mt-2 p-2 bg-slate-50 rounded">
																	{violation.details}
																</div>
															)}
														</div>
													</div>
												</div>
											))}
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
											<span><strong>Bias Score {(analyzeResult.bias_metrics.overall_bias_score * 100).toFixed(1)}%</strong> indicates 
											{analyzeResult.bias_metrics.overall_bias_score < 0.3 ? ' strong fairness with minimal disparities across groups.' 
												: analyzeResult.bias_metrics.overall_bias_score < 0.5 ? ' moderate disparities that should be monitored and addressed.'
												: ' significant unfairness requiring immediate remediation before deployment.'}</span>
										</li>
										<li className="flex items-start gap-2">
											<span className="text-blue-600 mt-0.5">•</span>
											<span><strong>Model achieves {(analyzeResult.model_performance.accuracy * 100).toFixed(1)}% accuracy</strong>, 
											but fairness metrics reveal how performance varies across demographic groups.</span>
										</li>
										{analyzeResult.bias_metrics.violations_detected.length > 0 ? (
											<li className="flex items-start gap-2">
												<span className="text-red-600 mt-0.5">•</span>
												<span className="text-red-700"><strong>{analyzeResult.bias_metrics.violations_detected.length} violation(s)</strong> detected. 
												Review mitigation tab for recommended actions to improve fairness.</span>
											</li>
										) : (
											<li className="flex items-start gap-2">
												<span className="text-green-600 mt-0.5">•</span>
												<span className="text-green-700"><strong>No violations detected.</strong> Model meets fairness thresholds across all protected attributes.</span>
											</li>
										)}
									</ul>
								</div>
							</div>
						) : (
							<div className="text-center py-12">
								<div className="text-6xl mb-4">📊</div>
								<p className="text-slate-600 mb-2">No analysis results yet</p>
								<p className="text-sm text-slate-500">Upload a dataset and click "Analyze" to see bias and fairness metrics</p>
							</div>
						)}
					</div>
				);
			case "risk-analysis":
				return (
					<div className="space-y-4">
						<h2 className="text-xl font-semibold">Risk Analysis</h2>
						{analyzeResult ? (
							<div className="space-y-4">
								<div className="p-4 bg-white rounded-lg border">
									<div className="text-sm text-slate-600">Overall Risk Score</div>
									<div className="text-2xl font-bold">{(analyzeResult.risk_assessment.overall_risk_score * 100).toFixed(1)}%</div>
								</div>
								
								{cleanResult && (
									<div className="p-4 bg-white rounded-lg border">
										<h3 className="font-semibold mb-2">PII Detection Results</h3>
										<div className="text-sm space-y-1">
											<div>Cells Anonymized: <span className="font-medium">{cleanResult.summary.total_cells_affected}</span></div>
											<div>Columns Removed: <span className="font-medium">{cleanResult.summary.columns_removed.length}</span></div>
											<div>Columns Anonymized: <span className="font-medium">{cleanResult.summary.columns_anonymized.length}</span></div>
										</div>
									</div>
								)}
							</div>
						) : (
							<p className="text-sm text-slate-600">Upload and analyze a dataset to see risk assessment.</p>
						)}
					</div>
				);
			case "bias-risk-mitigation":
				return (
					<div className="space-y-6">
						<div>
							<h2 className="text-2xl font-bold mb-2">PII Detection & Anonymization Strategy</h2>
							<p className="text-sm text-slate-600">Review detected risky features and choose how to anonymize them</p>
						</div>
						
						{piiDetectionResult ? (
							<div className="space-y-6">
								{/* File Info Banner */}
								<div className="p-3 bg-slate-100 border border-slate-300 rounded-lg text-sm">
									<div className="flex items-center gap-3">
										<span className="font-semibold text-slate-700">File:</span>
										<code className="px-2 py-1 bg-white rounded border border-slate-200">{piiDetectionResult.filename}</code>
										<span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs font-semibold rounded">
											{piiDetectionResult.file_type.toUpperCase()}
										</span>
										<span className="text-slate-600">
											{piiDetectionResult.dataset_info.rows} rows × {piiDetectionResult.dataset_info.columns} columns
										</span>
									</div>
								</div>

								{/* Summary Card */}
								<div className="p-6 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl border-2 border-blue-200">
									<div className="grid grid-cols-1 md:grid-cols-4 gap-4">
										<div>
											<div className="text-xs font-semibold text-blue-700 mb-1">TOTAL COLUMNS SCANNED</div>
											<div className="text-3xl font-bold text-blue-900">{piiDetectionResult.summary.total_columns_scanned}</div>
										</div>
										<div>
											<div className="text-xs font-semibold text-red-700 mb-1">HIGH RISK</div>
											<div className="text-3xl font-bold text-red-900">{piiDetectionResult.summary.high_risk_count}</div>
											<div className="text-xs text-slate-600">Must remove</div>
										</div>
										<div>
											<div className="text-xs font-semibold text-orange-700 mb-1">MEDIUM RISK</div>
											<div className="text-3xl font-bold text-orange-900">{piiDetectionResult.summary.medium_risk_count}</div>
											<div className="text-xs text-slate-600">Hash recommended</div>
										</div>
										<div>
											<div className="text-xs font-semibold text-yellow-700 mb-1">LOW RISK</div>
											<div className="text-3xl font-bold text-yellow-900">{piiDetectionResult.summary.low_risk_count}</div>
											<div className="text-xs text-slate-600">Mask/generalize</div>
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
											feature.risk_level === 'HIGH' ? 'red' :
											feature.risk_level === 'MEDIUM' ? 'orange' :
											feature.risk_level === 'LOW' ? 'yellow' : 'gray';
										
										const bgColor = 
											feature.risk_level === 'HIGH' ? 'bg-red-50 border-red-300' :
											feature.risk_level === 'MEDIUM' ? 'bg-orange-50 border-orange-300' :
											feature.risk_level === 'LOW' ? 'bg-yellow-50 border-yellow-300' : 'bg-gray-50 border-gray-300';
										
										return (
											<div key={idx} className={`p-5 rounded-xl border-2 ${bgColor}`}>
												{/* Header */}
												<div className="flex items-start justify-between mb-3">
													<div className="flex-1">
														<div className="flex items-center gap-3 mb-2">
															<span className={`px-3 py-1 bg-${riskColor}-600 text-white text-xs font-bold rounded-full`}>
																{feature.risk_level} RISK
															</span>
															<span className="font-mono font-bold text-lg text-slate-800">{feature.column}</span>
														</div>
														<div className="text-sm text-slate-700">
															<span className="font-semibold">Detected:</span> {feature.entity_type}
															<span className="mx-2">•</span>
															<span className="font-semibold">Confidence:</span> {(feature.confidence * 100).toFixed(1)}%
															<span className="mx-2">•</span>
															<span className="font-semibold">Occurrences:</span> {feature.detection_count}
														</div>
													</div>
												</div>

												{/* Explanation */}
												<div className="p-4 bg-white rounded-lg mb-4">
													<div className="text-xs font-semibold text-slate-600 mb-2">WHY IS THIS RISKY?</div>
													<p className="text-sm text-slate-700 leading-relaxed">{feature.explanation}</p>
													<div className="mt-3 text-xs text-slate-600">
														<strong>GDPR Reference:</strong> {feature.gdpr_article}
													</div>
												</div>

												{/* Sample Values */}
												{feature.sample_values.length > 0 && (
													<div className="p-4 bg-white rounded-lg mb-4">
														<div className="text-xs font-semibold text-slate-600 mb-2">SAMPLE VALUES</div>
														<div className="flex gap-2 flex-wrap">
															{feature.sample_values.map((val, i) => (
																<code key={i} className="px-2 py-1 bg-slate-100 rounded text-xs text-slate-800 border border-slate-200">
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
															<div className="text-xs font-semibold text-green-700 mb-1">✓ RECOMMENDED STRATEGY</div>
															<div className="font-bold text-lg text-slate-900">{feature.recommended_strategy}</div>
															<div className="text-sm text-slate-700 mt-1">{feature.strategy_description}</div>
															<div className="mt-2 flex gap-4 text-xs text-slate-600">
																<div>
																	<strong>Reversible:</strong> {feature.reversible ? 'Yes' : 'No'}
																</div>
																<div>
																	<strong>Use Cases:</strong> {feature.use_cases.join(', ')}
																</div>
															</div>
														</div>
														<button
															className="px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-500"
															onClick={() => alert(`Apply ${feature.recommended_strategy} to ${feature.column}`)}
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
														{Object.entries(piiDetectionResult.available_strategies)
															.filter(([strategy]) => strategy !== feature.recommended_strategy)
															.map(([strategy, details]: [string, any]) => (
																<div key={strategy} className="p-3 bg-white rounded border border-slate-200 hover:border-slate-400">
																	<div className="font-semibold text-sm text-slate-800">{strategy}</div>
																	<div className="text-xs text-slate-600 mt-1">{details.description}</div>
																	<div className="mt-2 flex items-center justify-between">
																		<span className={`px-2 py-0.5 text-xs rounded ${
																			details.risk_level === 'HIGH' ? 'bg-red-100 text-red-800' :
																			details.risk_level === 'MEDIUM' ? 'bg-orange-100 text-orange-800' :
																			'bg-yellow-100 text-yellow-800'
																		}`}>
																			{details.risk_level} Risk
																		</span>
																		<button
																			className="px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-500"
																			onClick={() => alert(`Apply ${strategy} to ${feature.column}`)}
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
										onClick={() => alert('Apply all recommended strategies and clean dataset')}
									>
										✓ Apply All Recommended Strategies & Clean Dataset
									</button>
								</div>
							</div>
						) : (
							<div className="text-center py-12">
								<div className="text-6xl mb-4">🔍</div>
								<p className="text-slate-600 mb-2">No PII detection results yet</p>
								<p className="text-sm text-slate-500">Upload a dataset and click "🔍 Detect PII" to scan for risky features</p>
							</div>
						)}
					</div>
				);
			case "results":
				return (
					<div className="space-y-4">
						<h2 className="text-xl font-semibold">Results Summary</h2>
						{(analyzeResult || cleanResult) ? (
							<div className="space-y-4">
								{analyzeResult && (
									<div className="p-4 bg-white rounded-lg border">
										<h3 className="font-semibold mb-2">Analysis Results</h3>
										<div className="text-sm space-y-1">
											<div>Dataset: {analyzeResult.filename}</div>
											<div>Rows: {analyzeResult.dataset_info.rows}</div>
											<div>Columns: {analyzeResult.dataset_info.columns}</div>
											<div>Bias Score: {(analyzeResult.bias_metrics.overall_bias_score * 100).toFixed(1)}%</div>
											<div>Risk Score: {(analyzeResult.risk_assessment.overall_risk_score * 100).toFixed(1)}%</div>
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
											<div>Original: {cleanResult.dataset_info.original_rows} rows × {cleanResult.dataset_info.original_columns} cols</div>
											<div>Cleaned: {cleanResult.dataset_info.cleaned_rows} rows × {cleanResult.dataset_info.cleaned_columns} cols</div>
											<div>Cells Anonymized: {cleanResult.summary.total_cells_affected}</div>
											<div>Columns Removed: {cleanResult.summary.columns_removed.length}</div>
											<div>GDPR Compliant: {cleanResult.gdpr_compliance.length} articles applied</div>
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