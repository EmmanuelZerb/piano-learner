"use client";

import { useRef, useState, type DragEvent, type FormEvent } from "react";

import { importYoutube, uploadTrack, type TrackCreated } from "@/lib/api";

const ACCEPT = ".mp3,.wav,.flac,.m4a,audio/mpeg,audio/wav,audio/flac,audio/mp4";

type Status =
  | { kind: "idle" }
  | { kind: "busy"; label: string }
  | { kind: "error"; message: string }
  | { kind: "done"; message: string };

export function ImportPanel({ onImported }: { onImported: () => void }) {
  const [url, setUrl] = useState("");
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const fileInput = useRef<HTMLInputElement>(null);
  const busy = status.kind === "busy";

  async function run(label: string, action: () => Promise<TrackCreated>) {
    setStatus({ kind: "busy", label });
    try {
      const { track, duplicate } = await action();
      const message = duplicate
        ? `« ${track.title} » est déjà dans la bibliothèque.`
        : `« ${track.title} » importé.`;
      setStatus({ kind: "done", message });
      onImported();
    } catch (err) {
      setStatus({ kind: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }

  function handleFile(file: File | undefined) {
    if (!file || busy) return;
    void run(`Import de ${file.name}…`, () => uploadTrack(file));
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    handleFile(event.dataTransfer.files[0]);
  }

  function handleYoutube(event: FormEvent) {
    event.preventDefault();
    if (!url.trim() || busy) return;
    void run("Téléchargement depuis YouTube…", async () => {
      const result = await importYoutube(url.trim());
      setUrl("");
      return result;
    });
  }

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        aria-disabled={busy}
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
        } ${busy ? "pointer-events-none opacity-50" : ""}`}
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
          disabled={busy}
          className="flex-1 rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
        />
        <button
          type="submit"
          disabled={busy || !url.trim()}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          Importer
        </button>
      </form>

      {status.kind === "busy" && <p className="text-sm text-zinc-500">{status.label}</p>}
      {status.kind === "error" && <p className="text-sm text-red-500">{status.message}</p>}
      {status.kind === "done" && <p className="text-sm text-emerald-600">{status.message}</p>}
    </div>
  );
}
