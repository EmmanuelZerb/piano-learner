import type { Job, JobStatus } from "@/lib/api";

export const STEP_LABELS: Record<string, string> = {
  queued: "En attente",
  starting: "Démarrage",
  download: "Téléchargement",
  convert: "Conversion",
  separate: "Séparation des pistes",
  transcribe: "Transcription",
  arrange: "Niveaux de difficulté",
  done: "Terminé",
};

export function isFinished(status: JobStatus): boolean {
  return status === "done" || status === "error" || status === "cancelled";
}

export function describeJob(job: Job): string {
  if (job.status === "cancelled") return "Annulé";
  if (job.status === "error") return job.error_message ?? "Erreur";
  if (job.status === "queued") return STEP_LABELS.queued;
  return STEP_LABELS[job.step] ?? job.step;
}

export function percent(progress: number): string {
  return `${Math.round(Math.min(1, Math.max(0, progress)) * 100)} %`;
}

/** { separate: 19.4, transcribe: 47.6 } → « Séparation des pistes 19 s · Transcription 48 s ». */
export function describeTimings(timings: Record<string, number> | null): string | null {
  if (!timings) return null;
  const parts = Object.entries(timings)
    .filter(([, seconds]) => seconds >= 0.5)
    .map(([step, seconds]) => `${STEP_LABELS[step] ?? step} ${Math.round(seconds)} s`);
  return parts.length ? parts.join(" · ") : null;
}
