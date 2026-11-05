import io
from pathlib import Path

import pytest

from app.pipeline.ingest import (
    IngestError,
    classify_youtube_error,
    ingest_upload,
    normalize_to_wav,
    probe_audio,
    save_stream,
    sniff_audio_format,
    validate_youtube_url,
)
from tests.conftest import AudioFactory, requires_ffmpeg

# --- Détection du type réel ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"ID3\x04\x00\x00\x00\x00\x00\x00\x00\x00", "mp3"),
        (b"\xff\xfb\x90\x64\x00\x00\x00\x00\x00\x00\x00\x00", "mp3"),
        (b"RIFF\x24\x08\x00\x00WAVEfmt ", "wav"),
        (b"fLaC\x00\x00\x00\x22\x10\x00\x10\x00", "flac"),
        (b"\x00\x00\x00\x20ftypM4A \x00\x00", "m4a"),
        (b"Hello, I am text", None),
        (b"%PDF-1.7\n%\xe2\xe3\xcf\xd3", None),
        (b"RIFF\x24\x08\x00\x00AVI LIST", None),
        (b"", None),
    ],
)
def test_sniff_audio_format(header: bytes, expected: str | None) -> None:
    assert sniff_audio_format(header) == expected


def test_save_stream_rejects_oversized(tmp_path: Path) -> None:
    dest = tmp_path / "f.bin"
    with pytest.raises(IngestError) as err:
        save_stream(io.BytesIO(b"x" * 2048), dest, max_bytes=1024)
    assert err.value.code == "too_large"
    assert err.value.status_code == 413
    assert not dest.exists()


def test_save_stream_rejects_empty(tmp_path: Path) -> None:
    with pytest.raises(IngestError) as err:
        save_stream(io.BytesIO(b""), tmp_path / "f.bin", max_bytes=1024)
    assert err.value.code == "empty_file"


def test_fake_mp3_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(IngestError) as err:
        ingest_upload(io.BytesIO(b"not really audio" * 10), "song.mp3", tmp_path, 10**6, 600)
    assert err.value.code == "unsupported_format"


@requires_ffmpeg
def test_truncated_file_with_valid_header_is_rejected(tmp_path: Path) -> None:
    fake = b"RIFF\x24\x08\x00\x00WAVE" + b"\x00" * 64
    with pytest.raises(IngestError) as err:
        ingest_upload(io.BytesIO(fake), "x.wav", tmp_path, 10**6, 600)
    assert err.value.code == "no_audio"


# --- ffmpeg -------------------------------------------------------------------------------


@requires_ffmpeg
@pytest.mark.parametrize("name", ["a.mp3", "a.wav", "a.flac", "a.m4a"])
def test_normalize_produces_stereo_44k_wav(make_audio: AudioFactory, tmp_path: Path, name: str):
    src = make_audio(name, seconds=1.5)
    dest = tmp_path / "out.wav"
    normalize_to_wav(src, dest)
    probe = probe_audio(dest)
    assert (probe.codec, probe.sample_rate, probe.channels) == ("pcm_s16le", 44100, 2)
    assert probe.duration_s == pytest.approx(1.5, abs=0.1)


@requires_ffmpeg
def test_ingest_upload_reads_tags_and_checks_duration(make_audio: AudioFactory, tmp_path: Path):
    src = make_audio("tagged.mp3", seconds=2, title="Ma chanson", artist="Moi")
    work = tmp_path / "work"
    work.mkdir()
    with src.open("rb") as f:
        audio = ingest_upload(f, "fichier.mp3", work, 10**7, 600)
    assert (audio.title, audio.artist) == ("Ma chanson", "Moi")
    assert (work / "audio.wav").exists()

    with src.open("rb") as f, pytest.raises(IngestError) as err:
        ingest_upload(f, "fichier.mp3", tmp_path / "work", 10**7, max_duration_s=1)
    assert err.value.code == "too_long"


# --- YouTube ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=BaW_jenozKc",
        "https://youtube.com/watch?v=BaW_jenozKc&t=42s",
        "http://m.youtube.com/watch?v=BaW_jenozKc",
        "https://music.youtube.com/watch?v=BaW_jenozKc&feature=share",
        "https://youtu.be/BaW_jenozKc?si=abc",
        "https://www.youtube.com/shorts/BaW_jenozKc",
        "https://www.youtube.com/embed/BaW_jenozKc",
        "https://www.youtube.com/watch?v=BaW_jenozKc&list=PL123456",
        "  https://www.youtube.com/watch?v=BaW_jenozKc  ",
    ],
)
def test_validate_youtube_url_accepts_videos(url: str) -> None:
    assert validate_youtube_url(url) == "BaW_jenozKc"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("https://www.youtube.com/playlist?list=PL123456", "playlist"),
        ("https://vimeo.com/123456", "invalid_url"),
        ("https://youtube.com.evil.example/watch?v=BaW_jenozKc", "invalid_url"),
        ("ftp://youtube.com/watch?v=BaW_jenozKc", "invalid_url"),
        ("https://www.youtube.com/watch?v=short", "invalid_url"),
        ("https://www.youtube.com/watch", "invalid_url"),
        ("https://www.youtube.com/@channel", "invalid_url"),
        ("not a url", "invalid_url"),
        ("", "invalid_url"),
    ],
)
def test_validate_youtube_url_rejects(url: str, code: str) -> None:
    with pytest.raises(IngestError) as err:
        validate_youtube_url(url)
    assert err.value.code == code


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "private"),
        ("ERROR: [youtube] abc: Video unavailable", "unavailable"),
        ("ERROR: [youtube] abc: Sign in to confirm your age.", "age_restricted"),
        ("ERROR: The uploader has not made this video available in your country", "geo_blocked"),
        ("ERROR: Sign in to confirm you're not a bot", "bot_check"),
        ("ERROR: something exploded", "download_failed"),
    ],
)
def test_classify_youtube_error(message: str, code: str) -> None:
    assert classify_youtube_error(message).code == code
