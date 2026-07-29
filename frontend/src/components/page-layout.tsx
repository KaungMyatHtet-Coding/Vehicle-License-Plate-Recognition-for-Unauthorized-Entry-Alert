export function PageHeader({
  eyebrow,
  title,
  description,
}: Readonly<{
  eyebrow: string;
  title: string;
  description: string;
}>) {
  return (
    <header className="max-w-3xl">
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--brand)]">
        {eyebrow}
      </p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
        {title}
      </h1>
      <p className="mt-3 text-base leading-7 text-slate-600">{description}</p>
    </header>
  );
}

export function FoundationPanel({
  title,
  description,
  children,
}: Readonly<{
  title: string;
  description: string;
  children?: React.ReactNode;
}>) {
  return (
    <section className="rounded-xl border border-[var(--border)] bg-white p-5 shadow-sm sm:p-6">
      <h2 className="text-lg font-semibold text-slate-950">{title}</h2>
      <p className="mt-2 leading-6 text-slate-600">{description}</p>
      {children}
    </section>
  );
}
