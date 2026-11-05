"""Export MIDI (pretty_midi) : un instrument par stem, donc un canal par stem."""

from pathlib import Path

import pretty_midi

from app.pipeline.notes import StemTranscription

# Programmes General MIDI, pour que chaque piste soit reconnaissable dans MuseScore.
STEM_PROGRAMS = {
    "piano": 0,  # Acoustic Grand Piano
    "other": 4,  # Electric Piano 1
    "bass": 32,  # Acoustic Bass
    "guitar": 25,  # Acoustic Guitar (steel)
    "vocals": 53,  # Voice Oohs
}
SUSTAIN_CC = 64


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
