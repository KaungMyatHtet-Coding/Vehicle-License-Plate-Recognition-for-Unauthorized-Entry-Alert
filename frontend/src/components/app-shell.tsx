"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavigationItem = {
  href: "/dashboard" | "/recognition" | "/history" | "/alerts" | "/authorized-vehicles";
  label: string;
  shortLabel: string;
  group: "WORKFLOW" | "OPERATIONS";
  icon: "dashboard" | "recognition" | "history" | "alerts" | "vehicles";
};

const navigation: readonly NavigationItem[] = [
  { href: "/dashboard", label: "Dashboard", shortLabel: "Home", group: "WORKFLOW", icon: "dashboard" },
  { href: "/recognition", label: "Recognition", shortLabel: "Recognize", group: "WORKFLOW", icon: "recognition" },
  { href: "/history", label: "Detection history", shortLabel: "History", group: "OPERATIONS", icon: "history" },
  { href: "/alerts", label: "Alerts", shortLabel: "Alerts", group: "OPERATIONS", icon: "alerts" },
  { href: "/authorized-vehicles", label: "Authorized vehicles", shortLabel: "Vehicles", group: "OPERATIONS", icon: "vehicles" },
];

function NavIcon({ name }: { name: NavigationItem["icon"] }) {
  const common = { "aria-hidden": true, className: "h-4 w-4 shrink-0", fill: "none", stroke: "currentColor", strokeWidth: 1.8, viewBox: "0 0 24 24" };
  if (name === "dashboard") return <svg {...common}><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></svg>;
  if (name === "recognition") return <svg {...common}><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" /><path d="m8 12 2.5 2.5L16 9" /></svg>;
  if (name === "history") return <svg {...common}><path d="M4 7h16M4 12h16M4 17h10" /><circle cx="18" cy="17" r="2.5" /></svg>;
  if (name === "alerts") return <svg {...common}><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" /></svg>;
  return <svg {...common}><path d="M4 6h16v12H4zM8 6V4h8v2M8 18v2h8v-2" /><circle cx="9" cy="12" r="1.5" /><path d="M13 10h4M13 14h3" /></svg>;
}

function BrandMark() {
  return <span aria-hidden="true" className="flex h-9 w-11 items-center justify-center rounded-md border border-teal-400/70 bg-teal-950 text-teal-200">
    <svg className="h-6 w-8" fill="none" viewBox="0 0 32 24" stroke="currentColor" strokeWidth="1.6">
      <rect x="2" y="5" width="28" height="14" rx="2" /><path d="M7 10h18M7 14h6M18 14h7" />
    </svg>
  </span>;
}

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();

  return <div className="min-h-screen md:grid md:grid-cols-[15rem_minmax(0,1fr)]">
    <a href="#main-content" className="fixed left-3 top-3 z-50 -translate-y-24 rounded-md bg-white px-4 py-3 font-semibold text-slate-950 shadow-lg transition-transform focus:translate-y-0">Skip to main content</a>
    <aside className="border-b border-slate-700 bg-slate-950 text-white md:min-h-screen md:border-b-0 md:border-r">
      <div className="flex items-center gap-3 px-4 py-4 md:px-5 md:py-5">
        <BrandMark />
        <div>
          <p className="text-base font-bold tracking-[0.18em] text-white">CVPX</p>
          <p className="text-xs font-medium text-slate-300">Vehicle security</p>
        </div>
      </div>
      <nav aria-label="Primary navigation" className="overflow-x-auto px-3 pb-3 md:overflow-visible md:px-3 md:pb-5">
        {(["WORKFLOW", "OPERATIONS"] as const).map((group) => <div key={group} className="md:mb-4">
          <h2 className="mb-1 px-3 text-[0.68rem] font-semibold tracking-[0.16em] text-slate-400">{group}</h2>
          <ul className="flex min-w-max gap-1 md:min-w-0 md:flex-col">
            {navigation.filter((item) => item.group === group).map((item) => {
              const active = pathname === item.href;
              return <li key={item.href}><Link href={item.href} aria-current={active ? "page" : undefined} className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ${active ? "bg-teal-700 text-white" : "text-slate-200 hover:bg-slate-800 hover:text-white"}`}>
                <NavIcon name={item.icon} /><span className="md:hidden">{item.shortLabel}</span><span className="hidden md:inline">{item.label}</span>
              </Link></li>;
            })}
          </ul>
        </div>)}
      </nav>
    </aside>
    <div className="min-w-0">
      <header className="border-b border-[var(--border)] bg-white/90 px-4 py-4 backdrop-blur sm:px-6 lg:px-10">
        <h1 className="max-w-5xl text-base font-semibold leading-6 text-slate-950 sm:text-lg sm:leading-7">Vehicle License Plate Recognition for Unauthorized Entry Alert</h1>
      </header>
      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-10 lg:py-8">{children}</main>
    </div>
  </div>;
}
