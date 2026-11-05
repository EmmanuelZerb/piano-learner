"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { getLibrary, mediaUrl, type LibraryItem } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/format";
import { percent, STEP_LABELS } from "@/lib/jobs";
import { matchesQuery } from "@/lib/library";
import { LEVEL_LABELS } from "@/lib/music";

const STAGE_LABELS: Record<LibraryItem["stage"], { label: string; className: string }> = {
  imported: {
    label: "Importé",
    className: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  },
  separated: {
    label: "Pistes séparées",
    className: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  },
  transcribed: {
    label: "Transcrit",
    className: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300",
  },
  arranged: {
    label: "Prêt à jouer",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
};

function Card({ item }: { item: LibraryItem }) {
  const stage = STAGE_LABELS[item.stage];
  const job = item.active_job;
  return (
    <li className="flex gap-4 rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
      <Link href={`/tracks/${item.id}`} className="shrink-0">
        {item.thumbnail_url ? (
          // Image servie par l'API locale : l'optimisation de next/image n'apporte rien ici.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={mediaUrl(item.thumbnail_url)}
            alt=""
            className="h-20 w-32 rounded object-cover"
          />
        ) : (
          <div className="flex h-20 w-32 items-center justify-center rounded bg-zinc-100 text-3xl dark:bg-zinc-900">
            ♪
          </div>
        )}
      </Link>
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <Link
              href={`/tracks/${item.id}`}
              className="block truncate font-medium hover:underline"
            >
              {item.title}
            </Link>
            <p className="truncate text-xs text-zinc-500">
              {[item.artist, formatDuration(item.duration_s), formatDate(item.created_at)]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
          <span className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${stage.className}`}>
            {job ? `${STEP_LABELS[job.step] ?? "En cours"} ${percent(job.progress)}` : stage.label}
          </span>
        </div>

        {item.sessions > 0 ? (
          <div className="space-y-1">
            <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
              <div
                className="h-full rounded-full bg-yellow-400"
                style={{ width: `${(item.best_accuracy ?? 0) * 100}%` }}
              />
            </div>
            <p className="text-xs text-zinc-500">
              Meilleur score {percent(item.best_accuracy ?? 0)} · {item.sessions} séance(s) ·{" "}
              {Math.round(item.practice_seconds / 60)} min
              {item.last_level && ` · dernier niveau : ${LEVEL_LABELS[item.last_level]}`}
            </p>
          </div>
        ) : (
          <p className="text-xs text-zinc-500">
            {item.levels.length > 0 ? "Pas encore travaillé" : "Niveaux pas encore calculés"}
          </p>
        )}

        {item.stage === "arranged" && (
          <Link
            href={`/tracks/${item.id}/play`}
            className="inline-block rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white"
          >
            ▶ Jouer
          </Link>
        )}
      </div>
    </li>
  );
}

export function LibraryView({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getLibrary(controller.signal)
      .then((data) => {
        setItems(data);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [refreshKey]);

  const visible = useMemo(
    () => (items ?? []).filter((item) => matchesQuery(item, query)),
    [items, query],
  );

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (items === null) return <p className="text-sm text-zinc-500">Chargement…</p>;
  if (items.length === 0)
    return <p className="text-sm text-zinc-500">Aucun morceau pour l&apos;instant.</p>;

  return (
    <div className="space-y-3">
      {items.length > 3 && (
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Rechercher un titre ou un artiste…"
          className="w-full rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
        />
      )}
      <ul className="space-y-3">
        {visible.map((item) => (
          <Card key={item.id} item={item} />
        ))}
      </ul>
      {visible.length === 0 && <p className="text-sm text-zinc-500">Aucun résultat.</p>}
    </div>
  );
}
