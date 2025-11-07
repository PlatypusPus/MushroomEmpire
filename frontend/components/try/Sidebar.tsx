"use client";
import clsx from "clsx";

export type TryTab =
	| "processing"
	| "bias-analysis"
	| "risk-analysis"
	| "bias-risk-mitigation"
	| "results";

const tabs: { id: TryTab; label: string; description: string }[] = [
	{ id: "processing", label: "Processing", description: "Upload & parse" },
	{ id: "bias-analysis", label: "Bias Analysis", description: "Detect patterns" },
	{ id: "risk-analysis", label: "Risk Analysis", description: "Assess exposure" },
	{ id: "bias-risk-mitigation", label: "Bias & Risk Mitigation", description: "Recommend actions" },
	{ id: "results", label: "Results", description: "View summaries" },
];

interface SidebarProps {
	value: TryTab;
	onChange: (tab: TryTab) => void;
}

export function Sidebar({ value, onChange }: SidebarProps) {
	return (
		<aside className={clsx("flex-none w-64 h-full border-r border-slate-200 bg-white/80 flex flex-col")}>      
			<div className="flex items-center px-3 h-14 border-b border-slate-200">
				<span className="font-semibold text-sm text-brand-700">Workflow</span>
			</div>
			<nav className="flex-1 py-2 space-y-1 overflow-hidden">
				{tabs.map((t) => {
					const selected = t.id === value;
					return (
						<button
							key={t.id}
							onClick={() => onChange(t.id)}
							className={clsx(
								"group w-full text-left px-4 py-3 text-sm font-medium flex flex-col gap-0.5 transition-colors",
								selected ? "bg-brand-600/10 text-brand-800" : "hover:bg-brand-50 text-slate-700"
							)}
						>
							<span className={clsx("", selected && "font-semibold")}>{t.label}</span>
							<span className="text-xs text-slate-500 group-hover:text-slate-600 line-clamp-1">{t.description}</span>
						</button>
					);
				})}
			</nav>
		</aside>
	);
}
