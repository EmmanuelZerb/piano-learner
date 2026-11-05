export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type ToolInfo = {
  available: boolean;
  path: string | null;
  version: string | null;
};

export type DeviceInfo = {
  torch_installed: boolean;
  torch_version: string | null;
  device: "cuda" | "mps" | "cpu";
  name: string | null;
  vram_gb: number | null;
};

export type Health = {
  status: "ok" | "degraded";
  ffmpeg: ToolInfo;
  ffprobe: ToolInfo;
  device: DeviceInfo;
};

export type Track = {
  id: string;
  title: string;
  artist: string | null;
  source: "upload" | "youtube";
  source_url: string | null;
  original_filename: string | null;
  duration_s: number;
  created_at: string;
  audio_url: string;
  thumbnail_url: string | null;
  transcribe_stems: string[];
};

export type Stems = {
  model: string;
  available: boolean;
  stems: { name: string; url: string }[];
  cached: boolean | null;
  elapsed_s: number | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
  ) {
    super(message);
  }
}

/** Les URLs renvoyées par l'API sont relatives (ex. /tracks/{id}/audio). */
export function mediaUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** Message lisible depuis une réponse d'erreur FastAPI ({detail: string | [{msg}], code?}). */
export function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  }
  return `Erreur HTTP ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const code = (body as { code?: string } | null)?.code ?? null;
    throw new ApiError(errorMessage(body, res.status), res.status, code);
  }
  return body as T;
}

export function fetchHealth(signal?: AbortSignal): Promise<Health> {
  return request<Health>("/health", { signal });
}

export function listTracks(signal?: AbortSignal): Promise<Track[]> {
  return request<Track[]>("/tracks", { signal });
}

export function getTrack(id: string, signal?: AbortSignal): Promise<Track> {
  return request<Track>(`/tracks/${id}`, { signal });
}

export function updateTranscribeStems(id: string, stems: string[]): Promise<Track> {
  return request<Track>(`/tracks/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcribe_stems: stems }),
  });
}

export function getStems(id: string, signal?: AbortSignal): Promise<Stems> {
  return request<Stems>(`/tracks/${id}/stems`, { signal });
}

export type TranscribeParams = {
  piano_engine: "bytedance" | "basic_pitch";
  piano: { onset_threshold: number; offset_threshold: number; frame_threshold: number };
  basic_pitch: { onset_threshold: number; frame_threshold: number; min_note_ms: number };
};

export type Transcription = {
  available: boolean;
  stems: {
    stem: string;
    engine: string;
    notes: number;
    pedals: number;
    cached: boolean;
    midi_url: string;
  }[];
  merged_url: string | null;
  params: TranscribeParams | null;
  elapsed_s: number | null;
};

export function getTranscriptionDefaults(signal?: AbortSignal): Promise<TranscribeParams> {
  return request<TranscribeParams>("/transcription/defaults", { signal });
}

export function getTranscription(id: string, signal?: AbortSignal): Promise<Transcription> {
  return request<Transcription>(`/tracks/${id}/transcription`, { signal });
}

export type Level = "beginner" | "intermediate" | "advanced";

export type PostprocessParams = {
  quantize: "none" | "eighth" | "sixteenth" | "triplet";
  quantize_strength: number;
  min_note_ms: number;
  min_velocity: number;
  merge_window_ms: number;
  split_point: number;
  dynamic_split: boolean;
  melody_from_vocals: boolean;
};

export type Arrangement = {
  available: boolean;
  tempo: number | null;
  key: string | null;
  chords: number | null;
  levels: {
    level: Level;
    right_notes: number;
    left_notes: number;
    max_polyphony_right: number;
    max_polyphony_left: number;
    edits: number;
    unmatched_edits: number;
    midi_url: string;
    notes_url: string;
    musicxml_url: string;
  }[];
  params: PostprocessParams | null;
};

export function getArrangementDefaults(signal?: AbortSignal): Promise<PostprocessParams> {
  return request<PostprocessParams>("/arrangement/defaults", { signal });
}

export function getArrangement(id: string, signal?: AbortSignal): Promise<Arrangement> {
  return request<Arrangement>(`/tracks/${id}/arrangement`, { signal });
}

export function arrangeTrack(id: string, params: PostprocessParams): Promise<Arrangement> {
  return request<Arrangement>(`/tracks/${id}/arrange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export type JobStatus = "queued" | "running" | "done" | "error" | "cancelled";

export type Job = {
  id: string;
  label: string;
  source: "upload" | "youtube" | "track";
  track_id: string | null;
  status: JobStatus;
  step: string;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
  timings: Record<string, number> | null; // secondes passées dans chaque étape
};

export type ProcessOptions = {
  until?: "ingest" | "separate" | "transcribe";
  stems?: string[];
  transcribe?: TranscribeParams;
  postprocess?: PostprocessParams;
};

const JSON_HEADERS = { "Content-Type": "application/json" };

export function createYoutubeJob(url: string, options: ProcessOptions = {}): Promise<Job> {
  return request<Job>("/jobs/youtube", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ url, options }),
  });
}

export function createUploadJob(file: File, options: ProcessOptions = {}): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  form.append("options", JSON.stringify(options));
  return request<Job>("/jobs/upload", { method: "POST", body: form });
}

export function createTrackJob(id: string, options: ProcessOptions): Promise<Job> {
  return request<Job>(`/tracks/${id}/jobs`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ options }),
  });
}

export function listJobs(
  filter: { trackId?: string; active?: boolean } = {},
  signal?: AbortSignal,
): Promise<Job[]> {
  const params = new URLSearchParams();
  if (filter.trackId) params.set("track_id", filter.trackId);
  if (filter.active) params.set("active", "true");
  return request<Job[]>(`/jobs?${params}`, { signal });
}

export function getJob(id: string): Promise<Job> {
  return request<Job>(`/jobs/${id}`);
}

export function cancelJob(id: string): Promise<Job> {
  return request<Job>(`/jobs/${id}/cancel`, { method: "POST" });
}

export function jobEventsUrl(id: string): string {
  return `${API_BASE}/jobs/${id}/events`;
}

export async function deleteTrack(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tracks/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    throw new ApiError(errorMessage(body, res.status), res.status, null);
  }
}

export type PracticeRecord = {
  level: Level;
  mode: "wait" | "free";
  hands: "R" | "L" | "LR";
  speed: number;
  hits: number;
  wrongs: number;
  misses: number;
  duration_s: number;
};

export type PracticeSessionRead = PracticeRecord & {
  id: string;
  accuracy: number;
  created_at: string;
};

export type PracticeHistory = {
  sessions: PracticeSessionRead[];
  best_accuracy: number | null;
  total_duration_s: number;
};

export function recordPractice(
  trackId: string,
  body: PracticeRecord,
): Promise<PracticeSessionRead> {
  return request<PracticeSessionRead>(`/tracks/${trackId}/practice`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function getPracticeHistory(
  trackId: string,
  signal?: AbortSignal,
): Promise<PracticeHistory> {
  return request<PracticeHistory>(`/tracks/${trackId}/practice`, { signal });
}

// --- Bibliothèque ---------------------------------------------------------------------------

export type LibraryItem = Track & {
  stage: "imported" | "separated" | "transcribed" | "arranged";
  levels: Level[];
  sessions: number;
  best_accuracy: number | null;
  practice_seconds: number;
  last_practiced_at: string | null;
  last_level: Level | null;
  active_job: Job | null;
};

export function getLibrary(signal?: AbortSignal): Promise<LibraryItem[]> {
  return request<LibraryItem[]>("/library", { signal });
}

// --- Éditeur --------------------------------------------------------------------------------

export type NoteEdit =
  | { op: "delete"; pitch: number; start: number }
  | { op: "pitch"; pitch: number; start: number; new_pitch: number }
  | { op: "hand"; pitch: number; start: number; hand: "L" | "R" }
  | { op: "split"; start: number; end: number; split: number };

const editsUrl = (trackId: string, level: Level) => `/tracks/${trackId}/arrangement/${level}/edits`;

export function addEdits(trackId: string, level: Level, edits: NoteEdit[]): Promise<Arrangement> {
  return request<Arrangement>(editsUrl(trackId, level), {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ edits }),
  });
}

/** `last` : annule seulement la dernière correction. */
export function removeEdits(trackId: string, level: Level, last: boolean): Promise<Arrangement> {
  return request<Arrangement>(`${editsUrl(trackId, level)}?last=${last}`, { method: "DELETE" });
}

export function describeDevice(device: DeviceInfo): string {
  if (!device.torch_installed) return "torch non installé (uv sync)";
  if (device.device === "cpu") return "CPU (aucun GPU détecté)";
  const vram = device.vram_gb ? ` · ${device.vram_gb} Go` : "";
  return `${device.device.toUpperCase()} · ${device.name ?? "?"}${vram}`;
}
