"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { cancelJob, type Job } from "@/lib/api";
import { describeJob, describeTimings, isFinished, percent } from "@/lib/jobs";
import { useJob } from "@/lib/useJob";

type Props = {
  job: Job;
  onFinished?: (job: Job) => void;
  showTrackLink?: boolean;
};

export function JobProgress({ job: initial, onFinished, showTrackLink = false }: Props) {
  const job = useJob(initial);
  const [cancelling, setCancelling] = useState(false);
  const notified = useRef(isFinished(initial.status));

  useEffect(() => {
    if (isFinished(job.status) && !notified.current) {
      notified.current = true;
      onFinished?.(job);
    }
  }, [job, onFinished]);

  const finished = isFinished(job.status);
  const barColor =
    job.status === "error"
      ? "bg-red-500"
      : job.status === "cancelled"
        ? "bg-zinc-400"
        : job.status === "done"
          ? "bg-emerald-500"
          : "bg-zinc-900 dark:bg-zinc-100";

  return (
    <div className="space-y-1.5 rounded-lg border border-zinc-200 p-3 text-sm dark:border-zinc-800">
      <div className="flex items-center justify-between gap-3">
        <span className="truncate font-medium">{job.label}</span>
        {!finished && (
          <button
            onClick={() => {
              setCancelling(true);
              void cancelJob(job.id).catch(() => setCancelling(false));
            }}
            disabled={cancelling}
            className="shrink-0 text-xs text-zinc-500 underline disabled:opacity-40"
          >
            {cancelling ? "Annulation…" : "Annuler"}
          </button>
        )}
        {finished && showTrackLink && job.status === "done" && job.track_id && (
          <Link href={`/tracks/${job.track_id}`} className="shrink-0 text-xs underline">
            Ouvrir
          </Link>
        )}
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div
          className={`h-full transition-[width] duration-300 ${barColor}`}
          style={{ width: `${(job.status === "done" ? 1 : job.progress) * 100}%` }}
        />
      </div>
      <div
        className={`flex justify-between text-xs ${job.status === "error" ? "text-red-500" : "text-zinc-500"}`}
      >
        <span>{describeJob(job)}</span>
        {!finished && <span className="font-mono">{percent(job.progress)}</span>}
      </div>
      {finished && describeTimings(job.timings) && (
        <p className="text-xs text-zinc-400">{describeTimings(job.timings)}</p>
      )}
    </div>
  );
}
