"use client";
import { useState } from "react";
import { Navbar } from "../../components/Navbar";
import { Sidebar, TryTab } from "../../components/try/Sidebar";
import { CenterPanel } from "../../components/try/CenterPanel";
import { ChatbotPanel } from "../../components/try/ChatbotPanel";

export default function TryPage() {
  const [tab, setTab] = useState<TryTab>("processing");

  return (
    <main className="min-h-screen flex flex-col">
      <Navbar />
      <div className="flex flex-1 min-h-0">
        <Sidebar value={tab} onChange={setTab} />
        <div className="flex-1 min-h-0 flex">
          <div className="flex-1 min-h-0 min-w-0"><CenterPanel tab={tab} onAnalyze={() => setTab("bias-analysis")} /></div>
          <div className="w-[360px] hidden xl:block"><ChatbotPanel /></div>
        </div>
      </div>
    </main>
  );
}
