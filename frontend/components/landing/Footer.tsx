import Link from 'next/link';

export function Footer() {
  return (
    <footer className="mt-24 border-t border-slate-200 bg-white/80">
      <div className="container-max py-10 flex flex-col sm:flex-row items-center justify-between gap-6">
        <div className="text-sm text-slate-600">© {new Date().getFullYear()} ShroomShield. Hackathon prototype.</div>
        <nav className="flex gap-6 text-sm">
          <Link href="#features" className="hover:text-brand-600">Features</Link>
          <Link href="#agents" className="hover:text-brand-600">Agents</Link>
          <Link href="#contact" className="hover:text-brand-600">Contact</Link>
          <Link href="/try" className="hover:text-brand-600">Try</Link>
        </nav>
      </div>
    </footer>
  );
}
