import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Maal",
  description:
    "Maal verifies every product attribute against its source, an adversarial audit, and a physics check before it reaches your catalog.",
};

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/enrich", label: "Enrich" },
  { href: "/catalog", label: "Catalog" },
  { href: "/compare", label: "Compare" },
  { href: "/about", label: "About" },
];

// Highlights the nav link matching the current path. Kept as a plain inline
// script (no React hook) so this file can stay a server component: a client
// component here would force components/ui.tsx into a "use client" module,
// which breaks the plain function exports (verdictTone, flagTone,
// physicsSummary) that catalog/row/job pages call directly during server
// rendering. Reacts to Next's client-side navigations via the History API.
const NAV_ACTIVE_SCRIPT = `(function(){function s(){var p=location.pathname;document.querySelectorAll("[data-nav-link]").forEach(function(a){var h=a.getAttribute("data-nav-link");var on=h==="/"?p==="/":p===h||p.indexOf(h+"/")===0;if(on){a.setAttribute("aria-current","page")}else{a.removeAttribute("aria-current")}})}var ps=history.pushState,rs=history.replaceState;history.pushState=function(){ps.apply(this,arguments);s()};history.replaceState=function(){rs.apply(this,arguments);s()};addEventListener("popstate",s);s()})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@400;600;800&family=JetBrains+Mono:wght@400;500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="flex min-h-screen flex-col antialiased">
        <header className="sticky top-0 z-50 h-[60px] border-b border-line bg-ink-2/80 backdrop-blur">
          <div className="mx-auto flex h-full max-w-6xl items-center justify-between gap-6 px-4">
            <Link
              href="/"
              className="flex shrink-0 items-center gap-2 focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
            >
              <span className="h-2.5 w-2.5 rounded-full bg-accent" aria-hidden="true" />
              <span className="font-display text-base font-extrabold tracking-tight text-fg">
                Maal
              </span>
            </Link>
            <nav className="flex min-w-0 items-center gap-5 overflow-x-auto">
              {NAV_LINKS.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  data-nav-link={l.href}
                  className="shrink-0 whitespace-nowrap py-1 text-sm text-fg-dim transition-colors duration-150 ease-out hover:text-fg focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
                >
                  {l.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-line px-4 py-4 text-xs text-fg-faint">
          Maal, provenance-first product intelligence.{" "}
          <Link
            href="/about"
            className="underline underline-offset-4 hover:text-fg-dim focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
          >
            About
          </Link>
        </footer>
        <script dangerouslySetInnerHTML={{ __html: NAV_ACTIVE_SCRIPT }} />
      </body>
    </html>
  );
}
