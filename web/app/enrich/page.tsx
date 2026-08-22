"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Mode = "single" | "file";

export default function EnrichPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("single");
  const [mpn, setMpn] = useState("");
  const [description, setDescription] = useState("");
  const [brand, setBrand] = useState("");
  const [supplier, setSupplier] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canSubmit =
    mode === "single" ? mpn.trim() && description.trim() : !!file;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      let res: Response;
      if (mode === "single") {
        res = await fetch("/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mpn, description, brand, supplier }),
        });
      } else {
        const form = new FormData();
        if (file) form.append("file", file);
        res = await fetch("/api/jobs", { method: "POST", body: form });
      }
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.id) {
        setError(body.error ?? `Something went wrong (${res.status}).`);
        return;
      }
      router.push(`/jobs/${body.id}`);
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto max-w-2xl">
      <h1 className="font-sans text-lg font-bold">Enrich products</h1>
      <p className="mt-1 text-sm text-ink2">
        Send one product or a whole spreadsheet. Every value comes back with its
        source, an audit verdict, and a physics check.
      </p>

      <div className="mt-5 flex gap-2">
        {(["single", "file"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded-[3px] border px-3 py-1.5 font-mono text-xs ${
              mode === m
                ? "border-accent/50 bg-accent/10 text-accent"
                : "border-line bg-panel text-ink2 hover:border-ink2 hover:text-ink"
            }`}
          >
            {m === "single" ? "Single product" : "Upload file"}
          </button>
        ))}
      </div>

      <form
        className="mt-4 flex flex-col gap-4 rounded-[3px] border border-line bg-panel p-5"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        {mode === "single" ? (
          <>
            <Field label="Part number *">
              <input
                value={mpn}
                onChange={(e) => setMpn(e.target.value)}
                placeholder="e.g. PDSH4816AF"
                className="w-full rounded-[3px] border border-line bg-paper px-3 py-2 font-mono text-sm focus:border-accent focus:outline-none"
              />
            </Field>
            <Field label="Raw description *">
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder='e.g. PDSH4816AF Dishwasher SS - Display Only'
                className="w-full rounded-[3px] border border-line bg-paper px-3 py-2 font-mono text-sm focus:border-accent focus:outline-none"
              />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Brand (optional)">
                <input
                  value={brand}
                  onChange={(e) => setBrand(e.target.value)}
                  placeholder="e.g. Frigidaire"
                  className="w-full rounded-[3px] border border-line bg-paper px-3 py-2 text-sm focus:border-accent focus:outline-none"
                />
              </Field>
              <Field label="Supplier (optional)">
                <input
                  value={supplier}
                  onChange={(e) => setSupplier(e.target.value)}
                  placeholder="e.g. Acme Supply Co (ACME)"
                  className="w-full rounded-[3px] border border-line bg-paper px-3 py-2 text-sm focus:border-accent focus:outline-none"
                />
              </Field>
            </div>
          </>
        ) : (
          <>
            <label
              className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-[3px] border border-dashed border-line bg-paper px-6 py-10 text-center hover:border-accent/60"
            >
              <span className="font-mono text-sm">
                {file ? file.name : "Drop or choose a .csv / .xlsx / .tsv"}
              </span>
              <span className="text-xs text-ink2">
                Needs a part-number column and a description column — other
                columns are optional and auto-detected.
              </span>
              <input
                type="file"
                accept=".csv,.xlsx,.xls,.tsv,.txt"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <span className="rounded-[3px] border border-line px-3 py-1 font-mono text-xs text-ink2">
                Browse files
              </span>
            </label>
          </>
        )}

        {error && <p className="text-sm text-bad">{error}</p>}
        <button
          type="submit"
          disabled={!canSubmit || busy}
          className="self-start rounded-[3px] bg-accent px-4 py-2 font-mono text-xs font-semibold text-white hover:bg-accent/90 disabled:opacity-40"
        >
          {busy ? "Starting enrichment…" : "Enrich now"}
        </button>
      </form>
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-mono text-[10px] uppercase tracking-wider text-ink2">
        {label}
      </span>
      {children}
    </label>
  );
}
