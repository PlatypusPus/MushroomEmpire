"use client";
import { TryTab } from "./Sidebar";
import { useState, useRef, useCallback, useEffect } from "react";

interface CenterPanelProps {
	tab: TryTab;
}

interface UploadedFileMeta {
	name: string;
	size: number;
	type: string;
	contentPreview: string;
}

export function CenterPanel({ tab }: CenterPanelProps) {
			const [fileMeta, setFileMeta] = useState<UploadedFileMeta | null>(null);
		const [isDragging, setIsDragging] = useState(false);
		const [progress, setProgress] = useState<number>(0);
		const [progressLabel, setProgressLabel] = useState<string>("Processing");
		const inputRef = useRef<HTMLInputElement | null>(null);
			const [loadedFromCache, setLoadedFromCache] = useState(false);

		const reset = () => {
			setFileMeta(null);
			setProgress(0);
			setProgressLabel("Processing");
		};

		const processFile = useCallback(async (f: File) => {
		if (!f) return;
			setProgress(0);
			// For large files, show a progress bar while reading the file stream (no preview)
			if (f.size > 1024 * 1024) {
				setProgressLabel("Uploading");
				const metaObj: UploadedFileMeta = {
					name: f.name,
					size: f.size,
					type: f.type || "unknown",
					contentPreview: "File too large for preview (limit 1MB).",
				};
				setFileMeta(metaObj);
				// Save to IndexedDB immediately so it persists without needing full read
				(async () => {
					try { await saveLatestUpload(f, metaObj); } catch {}
				})();
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
					<div className="space-y-4">
						<h2 className="text-xl font-semibold">Upload & Process Data</h2>
						<p className="text-sm text-slate-600">Upload a CSV / JSON / text file. We will later parse, detect PII, and queue analyses.</p>
									<div className="flex flex-col gap-3">
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
									<pre className="max-h-64 overflow-auto text-xs bg-slate-50 p-3 rounded-md whitespace-pre-wrap leading-relaxed">
										{fileMeta.contentPreview || "(no preview)"}
									</pre>
												<div className="mt-3 flex justify-end">
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
