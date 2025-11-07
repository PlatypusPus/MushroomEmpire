"use client";
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

export function Navbar() {
  const pathname = usePathname();
  const onTry = pathname?.startsWith('/try');
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <nav className={`w-full sticky top-0 z-50 bg-white border-b border-slate-200 shadow-md`}>
      <div className="container-max flex items-center justify-between h-16">
        <Link href="/" className="font-semibold text-brand-700 text-lg tracking-tight">Nordic Privacy AI</Link>
        {/* Desktop nav */}
        {onTry ? (
          <div className="hidden md:flex items-center gap-6 text-sm">
            <Link href="/" className="hover:text-brand-600 transition-colors">Home</Link>
          </div>
        ) : (
          <div className="hidden md:flex items-center gap-6 text-sm">
            <Link href="#features" className="hover:text-brand-600 transition-colors">Features</Link>
            <Link href="#agents" className="hover:text-brand-600 transition-colors">Agents</Link>
            <Link href="#contact" className="hover:text-brand-600 transition-colors">Contact</Link>
            <Link href="/try" className="inline-flex items-center rounded-md bg-brand-600 px-4 py-2 text-white font-medium shadow hover:bg-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:ring-offset-2">Try me</Link>
          </div>
        )}
        {/* Mobile menu button */}
        <button
          aria-label="Toggle menu"
          className="md:hidden inline-flex items-center justify-center w-10 h-10 rounded-md border border-slate-300 text-slate-700"
          onClick={() => setMenuOpen(v => !v)}
        >
          <span className="sr-only">Menu</span>
          {menuOpen ? '✕' : '☰'}
        </button>
      </div>
      {/* Mobile menu panel */}
      <div className={`md:hidden border-t border-slate-200 transition-[max-height,opacity] duration-200 overflow-hidden ${menuOpen ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'}`}>
        <div className="container-max py-3 flex flex-col gap-3 text-sm">
          {onTry ? (
            <Link href="/" onClick={() => setMenuOpen(false)} className="py-2">Home</Link>
          ) : (
            <>
              <a href="#features" onClick={() => setMenuOpen(false)} className="py-2">Features</a>
              <a href="#agents" onClick={() => setMenuOpen(false)} className="py-2">Agents</a>
              <a href="#contact" onClick={() => setMenuOpen(false)} className="py-2">Contact</a>
              <Link href="/try" onClick={() => setMenuOpen(false)} className="inline-flex items-center justify-center rounded-md bg-brand-600 px-4 py-2 text-white font-medium shadow hover:bg-brand-500">Try me</Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
