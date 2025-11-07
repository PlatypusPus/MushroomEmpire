"use client";
import { useState, useRef, useEffect } from "react";
import { chatWithCopilot } from "../../lib/api";

const CHAT_ENDPOINT = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://f52c8f4e7dfc.ngrok-free.app';

export function ChatbotPanel() {
	const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string; pending?: boolean; error?: boolean }[]>([
		{ role: "assistant", content: "Hi! I'm your Privacy Copilot. Ask me about compliance, GDPR articles, or dataset risks." },
	]);
	const [input, setInput] = useState("");
	const [isLoading, setIsLoading] = useState(false);
	const [delayedError, setDelayedError] = useState<string | null>(null);
	const scrollRef = useRef<HTMLDivElement | null>(null);

	useEffect(() => {
		if (scrollRef.current) {
			scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
		}
	}, [messages]);

	async function handleSubmit(e: React.FormEvent) {
		e.preventDefault();
		const prompt = input.trim();
		if (!prompt || isLoading) return;
		setInput("");
		setDelayedError(null);
		setMessages(prev => [...prev, { role: "user", content: prompt }, { role: "assistant", content: "Thinking…", pending: true }]);
		setIsLoading(true);

		// Delay window for showing errors (avoid instant flashing if slow model)
		const errorDisplayDelayMs = 4_000;
		let canShowError = false;
		const delayTimer = setTimeout(() => { canShowError = true; if (delayedError) showErrorBubble(delayedError); }, errorDisplayDelayMs);

		function showErrorBubble(msg: string) {
			setMessages(prev => prev.map(m => m.pending ? { ...m, content: msg, pending: false, error: true } : m));
		}

		try {
				let responseText: string | null = null;
				// Primary attempt via shared client
				try {
					responseText = await chatWithCopilot(prompt);
				} catch (primaryErr: any) {
					// Fallback: replicate working curl (query param, empty body)
					try {
						const res = await fetch(`${CHAT_ENDPOINT}/chat?prompt=${encodeURIComponent(prompt)}` , {
							method: 'POST',
							headers: { 'accept': 'application/json' },
							body: ''
						});
						if (res.ok) {
							const j = await res.json();
							responseText = j.response || JSON.stringify(j);
						} else {
							throw primaryErr;
						}
					} catch { throw primaryErr; }
				}
				clearTimeout(delayTimer);
				setMessages(prev => prev.map(m => m.pending ? { ...m, content: responseText || 'No response text', pending: false } : m));
			} catch (err: any) {
				clearTimeout(delayTimer);
				const errMsg = err?.message || 'Unexpected error';
				if (canShowError) {
					showErrorBubble(errMsg);
				} else {
					setDelayedError(errMsg);
				}
			} finally {
				setIsLoading(false);
			}
	}

	return (
		<div className="flex flex-col h-full border-l border-slate-200 bg-white/80">
			<div className="h-14 flex items-center px-4 border-b border-slate-200">
				<h2 className="font-semibold text-sm text-brand-700">Privacy Copilot</h2>
			</div>
			<div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
				{messages.map((m, i) => (
					<div
						key={i}
						className={"rounded-md px-3 py-2 text-sm max-w-[80%] whitespace-pre-wrap " +
							(m.role === "assistant"
								? m.error
									? "bg-red-50 text-red-700 border border-red-200"
									: m.pending
										? "bg-brand-600/10 text-brand-700 animate-pulse"
										: "bg-brand-600/10 text-brand-800"
								: "bg-brand-600 text-white ml-auto")}
					>
						{m.content}
					</div>
				))}
			</div>
			<div className="p-3 border-t border-slate-200">
				<form className="flex gap-2" onSubmit={handleSubmit}>
					<input
						value={input}
						onChange={e => setInput(e.target.value)}
						placeholder="Ask about GDPR, compliance, privacy risks..."
						className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 disabled:opacity-60"
						disabled={isLoading}
					/>
					<button
						type="submit"
						disabled={!input.trim() || isLoading}
						className="rounded-md bg-brand-600 text-white px-4 py-2 text-sm font-medium disabled:opacity-50"
					>
						{isLoading ? 'Sending…' : 'Send'}
					</button>
				</form>
				<p className="mt-2 text-[11px] text-slate-500">Responses may take up to 1–2 minutes while the local model generates output.</p>
			</div>
		</div>
	);
}
