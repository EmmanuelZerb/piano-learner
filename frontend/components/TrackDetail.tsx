"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ArrangementPanel } from "@/components/ArrangementPanel";
import { JobProgress } from "@/components/JobProgress";
import { StemsPanel } from "@/components/StemsPanel";
import { TranscriptionPanel } from "@/components/TranscriptionPanel";
import {
  createTrackJob,
  deleteTrack,
  getTrack,
  listJobs,
  mediaUrl,
  type Job,
  type ProcessOptions,
  type Track,
} from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { isFinished } from "@/lib/jobs";

export function TrackDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [track, setTrack] = useState<Track | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Une tâche terminée a pu produire stems, MIDI et niveaux : on recharge ces panneaux.
  const [pipelineVersion, setPipelineVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getTrack(id, controller.signal),
      listJobs({ trackId: id, active: true }, controller.signal),
    ])
      .then(([loaded, active]) => {
        setTrack(loaded);
        setJob(active[0] ?? null);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [id]);

  const startJob = useCallback(
    async (options: ProcessOptions) => {
      setError(null);
      try {
        setJob(await createTrackJob(id, options));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [id],
  );

  const onJobFinished = useCallback((finished: Job) => {
    setJob(finished);
    setPipelineVersion((v) => v + 1);
  }, []);

  async function remove() {
    if (!track || !window.confirm(`Supprimer « ${track.title} » et tous ses fichiers ?`)) return;
    try {
      await deleteTrack(track.id);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (!track)
    return <p className={error ? "text-red-500" : "text-zinc-500"}>{error ?? "Chargement…"}</p>;

  const running = job !== null && !isFinished(job.status);

  return (
    <>
      <div className="flex items-center justify-between">
        <Link href="/" className="text-sm text-zinc-500 hover:underline">
          ← Bibliothèque
        </Link>
        <button
          onClick={remove}
          disabled={running}
          className="text-sm text-red-500 hover:underline disabled:opacity-40"
        >
          Supprimer
        </button>
      </div>
      <header className="flex gap-4">
        {track.thumbnail_url && (
          // Image servie par l'API locale : l'optimisation de next/image n'apporte rien ici.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={mediaUrl(track.thumbnail_url)}
            alt=""
            className="h-20 w-36 rounded object-cover"
          />
        )}
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold">{track.title}</h1>
          <p className="text-zinc-500">
            {[track.artist, formatDuration(track.duration_s)].filter(Boolean).join(" · ")}
          </p>
        </div>
      </header>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {job && <JobProgress key={job.id} job={job} onFinished={onJobFinished} />}

      <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
        <h2 className="mb-3 font-medium">Mixage original</h2>
        <audio controls preload="none" src={mediaUrl(track.audio_url)} className="w-full" />
      </section>

      <StemsPanel
        key={`s${pipelineVersion}`}
        track={track}
        onTrackChange={setTrack}
        busy={running}
        onSeparate={() => void startJob({ until: "separate" })}
      />
      <TranscriptionPanel
        key={`t${pipelineVersion}`}
        track={track}
        busy={running}
        onTranscribe={(transcribe) => void startJob({ until: "transcribe", transcribe })}
      />
      <ArrangementPanel key={`a${pipelineVersion}`} trackId={track.id} />
    </>
  );
}
