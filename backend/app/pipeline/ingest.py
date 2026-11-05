"""Ingestion : fichier uploadé ou URL YouTube → WAV stéréo 44,1 kHz normalisé.

Indépendant de FastAPI et de la base : chaque fonction prend des chemins et des limites
explicites, ce qui permet de relancer ou tester une étape isolément.
"""

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO
from urllib.parse import parse_qs, urlparse

WAV_NAME = "audio.wav"
THUMBNAIL_NAME = "thumbnail.jpg"
SAMPLE_RATE = 44100
CHANNELS = 2

ALLOWED_FORMATS = {"mp3", "wav", "flac", "m4a"}
_CHUNK = 1024 * 1024


class IngestError(Exception):
    """Erreur présentable à l'utilisateur. `code` est stable, `message` est en français."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class AudioProbe:
    duration_s: float
    codec: str
    sample_rate: int
    channels: int
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestedAudio:
    title: str
    artist: str | None
    duration_s: float
    source_url: str | None = None
    original_filename: str | None = None
    has_thumbnail: bool = False


# --- Validation des fichiers -------------------------------------------------------------


def sniff_audio_format(header: bytes) -> str | None:
    """Type réel d'après les octets d'en-tête (les 12 premiers suffisent)."""
    if header.startswith(b"ID3"):
        return "mp3"
    if len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0:
        return "mp3"  # synchro de trame MPEG sans tag ID3
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"fLaC"):
        return "flac"
    if header[4:8] == b"ftyp":
        return "m4a"  # conteneur MP4/ISO ; ffprobe confirme ensuite la présence d'audio
    return None


def save_stream(src: BinaryIO, dest: Path, max_bytes: int) -> int:
    """Copie par blocs en refusant au-delà de `max_bytes` (le fichier partiel est supprimé)."""
    written = 0
    with dest.open("wb") as out:
        while chunk := src.read(_CHUNK):
            written += len(chunk)
            if written > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise IngestError(
                    "too_large",
                    f"Fichier trop volumineux (limite : {max_bytes // (1024 * 1024)} Mo).",
                    413,
                )
            out.write(chunk)
    if written == 0:
        raise IngestError("empty_file", "Le fichier est vide.", 400)
    return written


def probe_audio(path: Path) -> AudioProbe:
    """Lit la première piste audio avec ffprobe. Échoue si aucun flux audio décodable."""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", "-select_streams", "a:0", str(path),
    ]  # fmt: skip
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    data = json.loads(result.stdout or "{}") if result.returncode == 0 else {}
    streams = data.get("streams") or []
    duration = float(data.get("format", {}).get("duration") or 0)
    if not streams or duration <= 0:
        raise IngestError("no_audio", "Aucune piste audio lisible dans ce fichier.", 415)
    stream = streams[0]
    raw_tags = {**data["format"].get("tags", {}), **stream.get("tags", {})}
    return AudioProbe(
        duration_s=duration,
        codec=stream.get("codec_name", "?"),
        sample_rate=int(stream.get("sample_rate") or 0),
        channels=int(stream.get("channels") or 0),
        tags={k.lower(): str(v) for k, v in raw_tags.items()},
    )


def check_duration(duration_s: float, max_duration_s: float) -> None:
    if duration_s > max_duration_s:
        minutes, limit = duration_s / 60, max_duration_s / 60
        raise IngestError(
            "too_long", f"Morceau trop long ({minutes:.0f} min, limite : {limit:.0f} min)."
        )


def normalize_to_wav(src: Path, dest: Path) -> None:
    """Convertit n'importe quelle source audio en WAV PCM 16 bits stéréo 44,1 kHz."""
    cmd = [
        "ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src),
        "-vn", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(dest),
    ]  # fmt: skip
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
    if result.returncode != 0:
        raise IngestError("conversion_failed", f"Échec de la conversion ffmpeg : {result.stderr}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_upload(
    src: BinaryIO, filename: str, work_dir: Path, max_bytes: int, max_duration_s: float
) -> IngestedAudio:
    suffix = Path(filename).suffix.lower()[:8] or ".bin"
    source = work_dir / f"source{suffix}"
    save_stream(src, source, max_bytes)

    with source.open("rb") as f:
        fmt = sniff_audio_format(f.read(16))
    if fmt not in ALLOWED_FORMATS:
        raise IngestError(
            "unsupported_format",
            "Format non reconnu : seuls les vrais fichiers MP3, WAV, FLAC et M4A sont acceptés.",
            415,
        )

    probe = probe_audio(source)
    check_duration(probe.duration_s, max_duration_s)
    normalize_to_wav(source, work_dir / WAV_NAME)
    return IngestedAudio(
        title=probe.tags.get("title") or Path(filename).stem or "Sans titre",
        artist=probe.tags.get("artist"),
        duration_s=probe.duration_s,
        original_filename=filename,
    )


# --- YouTube ------------------------------------------------------------------------------

_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_PATH_PREFIXES = ("/shorts/", "/embed/", "/live/", "/v/")


def validate_youtube_url(url: str) -> str:
    """Renvoie l'ID de la vidéo. Refuse les playlists et tout ce qui n'est pas YouTube."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or (host not in _YT_HOSTS and host != "youtu.be"):
        raise IngestError("invalid_url", "Ce n'est pas une URL YouTube valide.")

    video_id: str | None = None
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        video_id = (parse_qs(parsed.query).get("v") or [""])[0]
    elif parsed.path.startswith(_YT_PATH_PREFIXES):
        video_id = parsed.path.split("/")[2]
    elif parsed.path == "/playlist":
        raise IngestError("playlist", "Les playlists ne sont pas acceptées : choisis une vidéo.")

    if not video_id or not _YT_ID.match(video_id):
        raise IngestError("invalid_url", "Impossible de trouver l'identifiant de la vidéo.")
    return video_id


def canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


_YT_ERRORS: list[tuple[tuple[str, ...], str, str]] = [
    (("private video",), "private", "Cette vidéo est privée."),
    (
        ("confirm your age", "age-restricted", "inappropriate for some users"),
        "age_restricted",
        "Vidéo soumise à une restriction d'âge (connexion requise).",
    ),
    (
        ("available in your country", "blocked it in your country", "geo restrict"),
        "geo_blocked",
        "Vidéo indisponible dans ton pays.",
    ),
    (
        ("not a bot",),
        "bot_check",
        "YouTube demande une vérification anti-robot. Mets yt-dlp à jour et réessaie plus tard.",
    ),
    (
        ("video unavailable", "this video is unavailable", "has been removed", "does not exist"),
        "unavailable",
        "Vidéo indisponible ou supprimée.",
    ),
    (("unsupported url", "incomplete youtube id"), "invalid_url", "URL YouTube non reconnue."),
]


def classify_youtube_error(message: str) -> IngestError:
    lowered = message.lower()
    for needles, code, text in _YT_ERRORS:
        if any(n in lowered for n in needles):
            return IngestError(code, text)
    return IngestError("download_failed", f"Échec du téléchargement YouTube : {message}", 502)


def _artist_from_info(info: dict) -> str | None:
    artists = info.get("artists") or []
    artist = info.get("artist") or (artists[0] if artists else None)
    if artist:
        return str(artist)
    uploader = info.get("uploader") or info.get("channel")
    return str(uploader).removesuffix(" - Topic") if uploader else None


def download_youtube(video_id: str, work_dir: Path, max_duration_s: float) -> tuple[Path, dict]:
    """Télécharge la meilleure piste audio + la miniature (jpg). Renvoie (fichier, infos)."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "writethumbnail": True,
        # YouTube exige un runtime JS pour certains formats : Node est déjà requis par le frontend.
        "js_runtimes": {"node": {}, "deno": {}},
        "postprocessors": [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}
        ],
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(canonical_youtube_url(video_id), download=False)
            if info.get("is_live"):
                raise IngestError("live", "Les directs ne sont pas acceptés.")
            check_duration(float(info.get("duration") or 0), max_duration_s)
            info = ydl.process_ie_result(info, download=True)
    except DownloadError as exc:
        raise classify_youtube_error(str(exc)) from exc

    downloads = info.get("requested_downloads") or []
    if not downloads or not Path(downloads[0]["filepath"]).exists():
        raise IngestError("download_failed", "yt-dlp n'a produit aucun fichier audio.", 502)
    return Path(downloads[0]["filepath"]), info


def ingest_youtube(url: str, work_dir: Path, max_duration_s: float) -> IngestedAudio:
    video_id = validate_youtube_url(url)
    source, info = download_youtube(video_id, work_dir, max_duration_s)

    thumb = work_dir / "source.jpg"
    if thumb.exists():
        shutil.move(thumb, work_dir / THUMBNAIL_NAME)

    probe = probe_audio(source)
    normalize_to_wav(source, work_dir / WAV_NAME)
    return IngestedAudio(
        title=str(info.get("track") or info.get("title") or video_id),
        artist=_artist_from_info(info),
        duration_s=probe.duration_s,
        source_url=canonical_youtube_url(video_id),
        has_thumbnail=(work_dir / THUMBNAIL_NAME).exists(),
    )
