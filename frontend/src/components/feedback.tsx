export function LoadingState({
  label = "Loading page",
}: Readonly<{ label?: string }>) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-xl border border-[var(--border)] bg-white p-6 shadow-sm transition-all"
    >
      <div
        aria-hidden="true"
        className="h-2 w-24 animate-pulse rounded-full bg-teal-600"
      />
      <p className="mt-4 font-medium text-slate-800">{label}…</p>
    </div>
  );
}

export function ErrorState({
  title = "This view is unavailable",
  message = "The request could not be completed. No entry decision was changed.",
  retry,
}: Readonly<{
  title?: string;
  message?: string;
  retry?: () => void;
}>) {
  return (
    <section
      role="alert"
      className="rounded-xl border border-red-200 bg-red-50 p-6 shadow-sm transition-all"
    >
      <h2 className="text-lg font-semibold text-red-950">{title}</h2>
      <p className="mt-2 leading-6 text-red-800">{message}</p>
      {retry ? (
        <button
          type="button"
          onClick={retry}
          className="mt-5 min-h-11 rounded-md bg-red-800 px-4 py-2 font-semibold text-white shadow-sm transition-colors hover:bg-red-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-600 focus-visible:ring-offset-2"
        >
          Try again
        </button>
      ) : null}
    </section>
  );
}

export function EmptyState({
  title = "No records found",
  message = "There are no entries to display at this time.",
}: Readonly<{
  title?: string;
  message?: string;
}>) {
  return (
    <div
      role="status"
      className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center"
    >
      <h3 className="text-base font-semibold text-slate-800">{title}</h3>
      <p className="mt-1 text-sm text-slate-600">{message}</p>
    </div>
  );
}
