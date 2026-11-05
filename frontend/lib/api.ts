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

export type TrackCreated = { track: Track; duplicate: boolean };

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

export function uploadTrack(file: File): Promise<TrackCreated> {
  const form = new FormData();
  form.append("file", file);
  return request<TrackCreated>("/tracks/upload", { method: "POST", body: form });
}

export function importYoutube(url: string): Promise<TrackCreated> {
  return request<TrackCreated>("/tracks/youtube", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
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

export function separateTrack(id: string): Promise<Stems> {
  return request<Stems>(`/tracks/${id}/separate`, { method: "POST" });
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

export function transcribeTrack(id: string, params: TranscribeParams): Promise<Transcription> {
  return request<Transcription>(`/tracks/${id}/transcribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params }),
  });
}

export function describeDevice(device: DeviceInfo): string {
  if (!device.torch_installed) return "torch non installé (uv sync)";
  if (device.device === "cpu") return "CPU (aucun GPU détecté)";
  const vram = device.vram_gb ? ` · ${device.vram_gb} Go` : "";
  return `${device.device.toUpperCase()} · ${device.name ?? "?"}${vram}`;
}
