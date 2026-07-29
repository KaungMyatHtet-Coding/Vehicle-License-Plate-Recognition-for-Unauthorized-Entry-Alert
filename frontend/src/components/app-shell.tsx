"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigation = [
  { href: "/dashboard", label: "Dashboard", shortLabel: "Home" },
  { href: "/recognition", label: "Recognition", shortLabel: "Recognize" },
  { href: "/history", label: "Detection history", shortLabel: "History" },
  { href: "/alerts", label: "Alerts", shortLabel: "Alerts" },
  {
    href: "/authorized-vehicles",
    label: "Authorized vehicles",
    shortLabel: "Vehicles",
  },
] as const;

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen md:grid md:grid-cols-[17rem_minmax(0,1fr)]">
      <a
        href="#main-content"
        className="fixed left-3 top-3 z-50 -translate-y-24 rounded-md bg-white px-4 py-3 font-semibold text-slate-950 shadow-lg transition-transform focus:translate-y-0"
      >
        Skip to main content
      </a>

      <aside className="border-b border-slate-700 bg-slate-950 text-white md:min-h-screen md:border-b-0 md:border-r">
        <div className="flex items-center justify-between gap-4 px-4 py-4 md:block md:px-6 md:py-7">
          <div>
            <p className="text-xs font-bold tracking-[0.2em] text-teal-300">
              CVPX
            </p>
            <p className="mt-1 text-sm font-semibold text-slate-100">
              Entry operations
            </p>
          </div>
          <span className="rounded-full border border-teal-700 bg-teal-950 px-2.5 py-1 text-xs font-medium text-teal-100">
            Local-first
          </span>
        </div>

        <nav
          aria-label="Primary navigation"
          className="overflow-x-auto px-3 pb-3 md:overflow-visible md:px-4 md:pb-6"
        >
          <ul className="flex min-w-max gap-1 md:min-w-0 md:flex-col">
            {navigation.map((item) => {
              const active = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`block rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                      active
                        ? "bg-teal-700 text-white"
                        : "text-slate-300 hover:bg-slate-800 hover:text-white"
                    }`}
                  >
                    <span className="md:hidden">{item.shortLabel}</span>
                    <span className="hidden md:inline">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>

      <div className="min-w-0">
        <header className="border-b border-[var(--border)] bg-white/90 px-4 py-3 backdrop-blur sm:px-6 lg:px-10">
          <p className="text-sm text-slate-600">
            Vehicle License Plate Recognition for Unauthorized Entry Alert
          </p>
        </header>
        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto w-full max-w-7xl px-4 py-7 sm:px-6 lg:px-10 lg:py-10"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
