"use client";

import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";

import { JobProgress } from "@/components/JobProgress";
import { createUploadJob, createYoutubeJob, listJobs, type Job } from "@/lib/api";

const ACCEPT = ".mp3,.wav,.flac,.m4a,audio/mpeg,audio/wav,audio/flac,audio/mp4";

export function ImportPanel({ onImported }: { onImported: () => void }) {
  const [url, setUrl] = useState("");
  const [dragging, setDragging] = useState(false);
  const [processAll, setProcessAll] = useState(true);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // Les tâches continuent côté serveur : on les retrouve après un rechargement de la page.
  useEffect(() => {
    const controller = new AbortController();
    listJobs({ active: true }, controller.signal)
      .then((active) => setJobs(active.filter((j) => j.source !== "track")))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  async function start(action: () => Promise<Job>) {
    setSending(true);
    setError(null);
    try {
      const job = await action();
      setJobs((current) => [job, ...current]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  }

  const options = { until: processAll ? ("transcribe" as const) : ("ingest" as const) };

  function handleFile(file: File | undefined) {
    if (!file || sending) return;
    void start(() => createUploadJob(file, options));
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    handleFile(event.dataTransfer.files[0]);
  }

  function handleYoutube(event: FormEvent) {
    event.preventDefault();
    if (!url.trim() || sending) return;
    void start(async () => {
      const job = await createYoutubeJob(url.trim(), options);
      setUrl("");
      return job;
    });
  }

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        aria-disabled={sending}
        onClick={() => fileInput.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
          dragging
            ? "border-emerald-500 bg-emerald-500/5"
            : "border-zinc-300 hover:border-zinc-400 dark:border-zinc-700"
        } ${sending ? "pointer-events-none opacity-50" : ""}`}
      >
        <p className="font-medium">Glisse un fichier audio ici ou clique pour choisir</p>
        <p className="mt-1 text-sm text-zinc-500">MP3, WAV, FLAC ou M4A</p>
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            handleFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>

      <form onSubmit={handleYoutube} className="flex gap-2">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=…"
          disabled={sending}
          className="flex-1 rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
        />
        <button
          type="submit"
          disabled={sending || !url.trim()}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Importer
        </button>
      </form>

      <label className="flex items-center gap-2 text-sm text-zinc-500">
        <input
          type="checkbox"
          checked={processAll}
          onChange={(e) => setProcessAll(e.target.checked)}
        />
        Traiter automatiquement : séparation, transcription et niveaux de difficulté
      </label>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {jobs.length > 0 && (
        <div className="space-y-2">
          {jobs.map((job) => (
            <JobProgress key={job.id} job={job} onFinished={onImported} showTrackLink />
          ))}
        </div>
      )}
    </div>
  );
}
