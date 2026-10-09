import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import Dashboard from "./pages/Dashboard";
import Chat from "./pages/Chat";
import Landing from "./pages/Landing";
import Account from "./pages/Account";
import Validation from "./pages/Validation";
import Alerts from "./pages/Alerts";
import Priority from "./pages/Priority";
import LiveHazards from "./pages/LiveHazards";
import Tutorials from "./pages/Tutorials";
import ApiDocs from "./pages/ApiDocs";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <QueryClientProvider client={new QueryClient()}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/dashboard" element={<div className="animate-[page-in_700ms_ease-out]"><Dashboard /></div>} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/account" element={<Account />} />
            <Route path="/validation" element={<Validation />} />
            <Route path="/honesty" element={<Navigate to="/validation" replace />} />
            <Route path="/priority" element={<Priority />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/live" element={<LiveHazards />} />
            <Route path="/tutorials" element={<Tutorials />} />
            <Route path="/developers" element={<ApiDocs />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
