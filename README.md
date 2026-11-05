# Piano Learner

Application locale qui transforme un morceau (MP3/WAV ou URL YouTube) en tutoriel piano « notes qui tombent ». Le pipeline : séparation des pistes par IA, transcription MIDI, simplification par niveau, puis lecteur interactif avec clavier MIDI.

> Usage strictement personnel, sur des contenus dont vous avez le droit de disposer.

## Prérequis (Windows)

```powershell
winget install astral-sh.uv
winget install Gyan.FFmpeg
# Node.js >= 20 (testé avec 24)
```

Un GPU NVIDIA est recommandé (testé sur RTX 3060 Ti 8 Go, wheels torch CUDA 12.6). Sans GPU, tout fonctionne sur CPU, mais 5 à 10 fois plus lentement.

## Installation

```powershell
npm install
npm run setup      # venv Python 3.11 + torch CUDA + modèles ML, deps frontend
npm run doctor     # vérifie ffmpeg, Node, torch, GPU
npm run check:ml   # optionnel : télécharge les modèles (~250 Mo) et teste une inférence
```

## Utilisation

```powershell
npm run dev
```

- Interface : http://localhost:3000
- API : http://127.0.0.1:8000 (documentation interactive sur `/docs`)

## Développement

Voir [CLAUDE.md](CLAUDE.md) pour l'architecture, les commandes et les décisions techniques.

## Limites connues

- La transcription automatique n'est jamais parfaite, surtout sur des productions denses (synthés, reverb).
- La piste « piano » de Demucs est souvent incomplète : transcrire aussi « other ».
- yt-dlp doit être mis à jour régulièrement pour suivre les changements de YouTube.
