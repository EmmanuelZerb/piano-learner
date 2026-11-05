"""Export MIDI.

- Transcriptions brutes (pretty_midi) : un instrument par stem, donc un canal par stem.
- Arrangements (mido) : deux pistes « Main droite » / « Main gauche » et une carte de tempo
  construite sur les temps détectés, pour que les mesures tombent juste dans MuseScore.
"""

import math
from pathlib import Path
from typing import TYPE_CHECKING

import mido
import pretty_midi

from app.pipeline.notes import StemTranscription
from app.pipeline.rhythm import BeatGrid, beat_position

if TYPE_CHECKING:
    from app.pipeline.postprocess import Arrangement

# Programmes General MIDI, pour que chaque piste soit reconnaissable dans MuseScore.
STEM_PROGRAMS = {
    "piano": 0,  # Acoustic Grand Piano
    "other": 4,  # Electric Piano 1
    "bass": 32,  # Acoustic Bass
    "guitar": 25,  # Acoustic Guitar (steel)
    "vocals": 53,  # Voice Oohs
}
SUSTAIN_CC = 64
PPQ = 480
HAND_TRACKS = (("R", "Main droite", 0), ("L", "Main gauche", 1))


def to_instrument(transcription: StemTranscription) -> pretty_midi.Instrument:
    program = STEM_PROGRAMS.get(transcription.stem, 0)
    instrument = pretty_midi.Instrument(program=program, name=transcription.stem)
    for n in transcription.notes:
        instrument.notes.append(
            pretty_midi.Note(velocity=n.velocity, pitch=n.pitch, start=n.start, end=n.end)
        )
    for p in transcription.pedals:
        instrument.control_changes += [
            pretty_midi.ControlChange(SUSTAIN_CC, 127, p.start),
            pretty_midi.ControlChange(SUSTAIN_CC, 0, p.end),
        ]
    return instrument


def write_midi(transcriptions: list[StemTranscription], path: Path) -> None:
    """pretty_midi attribue les canaux dans l'ordre des instruments (en sautant le 10, batterie)."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    midi.instruments = [to_instrument(t) for t in transcriptions]
    tmp = path.with_suffix(".part")
    midi.write(str(tmp))
    tmp.replace(path)


# --- Arrangements ---------------------------------------------------------------------------


def lead_beats(grid: BeatGrid) -> int:
    """Temps ajoutés avant le premier temps détecté pour que t = 0 ait un tick positif."""
    return max(0, math.ceil(-beat_position(grid, 0.0)))


def time_to_tick(grid: BeatGrid, t: float, lead: int) -> int:
    return max(0, round((beat_position(grid, t) + lead) * PPQ))


def tempo_events(grid: BeatGrid, lead: int) -> list[tuple[int, mido.MetaMessage]]:
    """Un changement de tempo par temps (un seul si la grille est régulière)."""
    b = grid.beats
    periods = [b[i + 1] - b[i] for i in range(len(b) - 1)]
    events = [(0, mido.MetaMessage("set_tempo", tempo=round(periods[0] * 1e6)))]
    for i, period in enumerate(periods[1:], start=1):
        tempo = round(period * 1e6)
        if abs(tempo - events[-1][1].tempo) > 500:  # < 0,05 % d'écart : inutile
            events.append(((i + lead) * PPQ, mido.MetaMessage("set_tempo", tempo=tempo)))
    return events


def _to_track(name: str, events: list[tuple[int, int, mido.Message]]) -> mido.MidiTrack:
    """events = (tick absolu, ordre à tick égal, message) → piste en temps relatifs."""
    track = mido.MidiTrack([mido.MetaMessage("track_name", name=name)])
    last = 0
    for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
        track.append(msg.copy(time=tick - last))
        last = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    return track


def write_arrangement_midi(arrangement: "Arrangement", path: Path) -> None:
    grid = arrangement.grid
    lead = lead_beats(grid)

    meta: list[tuple[int, int, mido.Message]] = [
        (0, 0, mido.MetaMessage("time_signature", numerator=4, denominator=4))
    ]
    if arrangement.key:
        meta.append((0, 0, mido.MetaMessage("key_signature", key=arrangement.key.name)))
    meta += [(tick, 0, msg) for tick, msg in tempo_events(grid, lead)]
    meta += [
        (time_to_tick(grid, c.start, lead), 1, mido.MetaMessage("marker", text=c.name))
        for c in arrangement.chords
        if c.root is not None
    ]

    midi = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    midi.tracks.append(_to_track("Tempo", meta))
    for hand, name, channel in HAND_TRACKS:
        events: list[tuple[int, int, mido.Message]] = [
            (0, 0, mido.Message("program_change", channel=channel, program=0))
        ]
        for n in arrangement.notes:
            if n.hand != hand:
                continue
            start = time_to_tick(grid, n.start, lead)
            end = max(start + 1, time_to_tick(grid, n.end, lead))
            # À tick égal : note_off (ordre 1) avant note_on (ordre 2) pour les notes répétées.
            events.append(
                (
                    start,
                    2,
                    mido.Message("note_on", channel=channel, note=n.pitch, velocity=n.velocity),
                )
            )
            events.append(
                (end, 1, mido.Message("note_off", channel=channel, note=n.pitch, velocity=0))
            )
        for p in arrangement.pedals:
            events.append(
                (
                    time_to_tick(grid, p.start, lead),
                    3,
                    mido.Message("control_change", channel=channel, control=SUSTAIN_CC, value=127),
                )
            )
            events.append(
                (
                    time_to_tick(grid, p.end, lead),
                    0,
                    mido.Message("control_change", channel=channel, control=SUSTAIN_CC, value=0),
                )
            )
        midi.tracks.append(_to_track(name, events))

    tmp = path.with_suffix(".part")
    midi.save(str(tmp))
    tmp.replace(path)
