import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "Maal — Product Intelligence Console",
};

const downloads = [
  { label: "result.csv", href: "/api/download/result.csv" },
  { label: "result.xlsx", href: "/api/download/result.xlsx" },
  { label: "sidecar.jsonl", href: "/api/download/sidecar.jsonl" },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body className="min-h-screen bg-paper font-sans text-ink antialiased">
        <header className="border-b border-line bg-panel">
          <div className="flex items-center justify-between px-6 py-3">
            <Link href="/about" className="flex items-baseline gap-3" title="What is Maal?">
              <span className="font-sans text-lg font-bold tracking-[0.18em]">
                MAAL
              </span>
              <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-ink2">
                Product Intelligence Console
              </span>
            </Link>
            <nav className="flex items-center gap-5">
              <Link href="/enrich" className="rounded-[3px] bg-accent px-3 py-1.5 font-mono text-xs font-semibold text-white hover:bg-accent/90">
                Enrich
              </Link>
              <Link href="/" className="font-mono text-xs text-ink2 underline decoration-line underline-offset-4 hover:text-ink">
                Dashboard
              </Link>
              <Link href="/catalog" className="font-mono text-xs text-ink2 underline decoration-line underline-offset-4 hover:text-ink">
                Catalog
              </Link>
              <Link href="/compare" className="font-mono text-xs text-ink2 underline decoration-line underline-offset-4 hover:text-ink">
                Ground truth
              </Link>
              <Link href="/about" className="font-mono text-xs text-ink2 underline decoration-line underline-offset-4 hover:text-ink">
                About
              </Link>
            </nav>
          </div>
        </header>
        <main className="px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
