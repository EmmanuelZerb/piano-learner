"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { listenInput, listInputs, requestMidi, type MidiDevice } from "@/lib/player/midi";
import { usePlayerStore } from "@/lib/player/store";

/** Accès MIDI (demandé au clic, l'autorisation passe par le navigateur), liste des claviers
 * branchés (mise à jour à chaud) et écoute du clavier choisi. */
export function useMidi(
  onNoteOn: (pitch: number, velocity: number) => void,
  onNoteOff: (pitch: number) => void,
) {
  const [access, setAccess] = useState<MIDIAccess | null>(null);
  const [devices, setDevices] = useState<MidiDevice[]>([]);
  // Le support du MIDI n'est testé qu'au clic : `navigator` n'existe pas au rendu serveur.
  const [error, setError] = useState<string | null>(null);
  const inputId = usePlayerStore((s) => s.midiInputId);
  const handlers = useRef({ onNoteOn, onNoteOff });
  useEffect(() => {
    handlers.current = { onNoteOn, onNoteOff };
  }, [onNoteOn, onNoteOff]);

  const connect = useCallback(async () => {
    try {
      const midi = await requestMidi();
      setAccess(midi);
      setError(null);
      const refresh = () => {
        const inputs = listInputs(midi);
        setDevices(inputs);
        const { midiInputId, set } = usePlayerStore.getState();
        if (!inputs.some((d) => d.id === midiInputId)) set({ midiInputId: inputs[0]?.id ?? null });
      };
      midi.onstatechange = refresh;
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Accès MIDI refusé.");
    }
  }, []);

  useEffect(() => {
    if (!access || !inputId) return;
    return listenInput(access, inputId, (message) => {
      if (message.type === "on") handlers.current.onNoteOn(message.pitch, message.velocity);
      else handlers.current.onNoteOff(message.pitch);
    });
  }, [access, inputId]);

  return { connected: access !== null, devices, error, connect };
}
