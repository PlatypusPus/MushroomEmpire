import './globals.css';
import type { ReactNode } from 'react';
import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'ShroomShield',
  description: 'AI-powered GDPR compliance platform',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full bg-gradient-to-br from-brand-50 via-white to-brand-100 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
