"use client";
import { TryTab } from "./Sidebar";
import { useState, useRef, useCallback, useEffect } from "react";
import { saveLatestUpload, getLatestUpload, deleteLatestUpload } from "../../lib/idb";

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
		const [isDragging, setIsDragging] = useState(false);
		const [progress, setProgress] = useState<number>(0);
		const [progressLabel, setProgressLabel] = useState<string>("Processing");
		const [tablePreview, setTablePreview] = useState<TablePreviewData | null>(null);
		const inputRef = useRef<HTMLInputElement | null>(null);
			const [loadedFromCache, setLoadedFromCache] = useState(false);

		const reset = () => {
			setFileMeta(null);
			setProgress(0);
			setProgressLabel("Processing");
			setTablePreview(null);
		};

		function tryParseCSV(text: string, maxRows = 50, maxCols = 40): TablePreviewData | null {
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
						const { meta } = await getLatestUpload();
						if (!ignore && meta) {
							setFileMeta(meta as UploadedFileMeta);
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
												<div className="mt-3 flex justify-end gap-2">
													<button
														type="button"
															onClick={async () => {
																reset();
																try { await deleteLatestUpload(); } catch {}
																setLoadedFromCache(false);
															}}
														className="text-xs rounded-md border px-3 py-1.5 hover:bg-slate-50"
													>
														Clear
													</button>
													<button
														type="button"
														onClick={() => onAnalyze?.()}
														className="text-xs rounded-md bg-brand-600 text-white px-3 py-1.5 hover:bg-brand-500"
													>
														Analyze
													</button>
												</div>
								</div>
							)}
						</div>
					</div>
				);
			case "bias-analysis":
				return (
					<div className="space-y-4">
						<h2 className="text-xl font-semibold">Bias Analysis (Placeholder)</h2>
						<p className="text-sm text-slate-600">Once processing completes, bias metrics will appear here (distribution, representation, fairness indicators).</p>
					</div>
				);
			case "risk-analysis":
				return (
					<div className="space-y-4">
						<h2 className="text-xl font-semibold">Risk Analysis (Placeholder)</h2>
						<p className="text-sm text-slate-600">Potential privacy exposure, sensitive attribute concentration, consent gaps will be displayed.</p>
					</div>
				);
			case "bias-risk-mitigation":
				return (
					<div className="space-y-4">
						<h2 className="text-xl font-semibold">Mitigation Suggestions (Placeholder)</h2>
						<p className="text-sm text-slate-600">Recommended transformations, anonymization strategies, sampling adjustments, consent workflows.</p>
					</div>
				);
			case "results":
				return (
					<div className="space-y-4">
						<h2 className="text-xl font-semibold">Results Summary (Placeholder)</h2>
						<p className="text-sm text-slate-600">Aggregated findings and downloadable compliance report will appear here.</p>
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
