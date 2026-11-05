"use client";

import { useEffect, useState } from "react";

import { jobEventsUrl, type Job } from "@/lib/api";
import { isFinished } from "@/lib/jobs";

/** Suit une tâche en direct (Server-Sent Events) à partir de son état initial. */
export function useJob(initial: Job): Job {
  const [job, setJob] = useState(initial);

  useEffect(() => {
    if (isFinished(initial.status)) return;
    const source = new EventSource(jobEventsUrl(initial.id));
    source.onmessage = (event: MessageEvent<string>) => {
      const next = JSON.parse(event.data) as Job;
      setJob(next);
      if (isFinished(next.status)) source.close();
    };
    // En cas de coupure, EventSource se reconnecte seul et le serveur renvoie l'état courant.
    return () => source.close();
  }, [initial.id, initial.status]);

  return job;
}
