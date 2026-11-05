# CLAUDE.md — Piano Learner

Application web locale et personnelle. Elle prend un audio (fichier ou URL YouTube), sépare les stems (Demucs), transcrit en MIDI (ByteDance pour le piano, Basic Pitch pour le reste), post-traite le résultat (quantification, mains, difficulté), puis l'affiche en « notes qui tombent » façon Synthesia.

## État d'avancement

| Phase | Statut |
|---|---|
| 0 — Initialisation (monorepo, `/health`, test de la stack ML) | ✅ |
| 1 — Ingestion audio (upload + YouTube → WAV 44,1 kHz) | ✅ |
| 2 — Séparation des sources (Demucs htdemucs_6s, cache par hash) | ✅ |
| 3 — Transcription (ByteDance + Basic Pitch) | ⏳ à faire |
| 4–9 | voir le cahier des charges (post-traitement, API async, lecteur, entraînement, bibliothèque, finitions) |

## Architecture

```
backend/                 Python 3.11, géré par uv (pyproject.toml + uv.lock)
  app/main.py            create_app(settings) : moteur DB, CORS, handler PipelineError, /health
  app/config.py          Settings (pydantic-settings, préfixe d'env PIANO_, backend/.env)
  app/system.py          Détection ffmpeg/ffprobe et du device torch (cuda/mps/cpu)
  app/db.py              Moteur SQLite, migration minimale (add_missing_columns), get_session
  app/models/            Tables SQLModel (Track, avec transcribe_stems)
  app/library.py         Dossiers de travail temporaires, enregistrement et déduplication (hash du WAV)
  app/api/deps.py        Dépendances communes (session, settings, get_track_or_404)
  app/api/tracks.py      Routes /tracks : upload, youtube, liste, détail, PATCH sélection, audio, miniature
  app/api/stems.py       Routes /tracks/{id}/separate, /stems, /stems/{name}
  app/pipeline/ingest.py Validation (octets d'en-tête + ffprobe), yt-dlp, normalisation ffmpeg
  app/pipeline/errors.py PipelineError(code, message, status) → {code, detail}
  app/pipeline/separate.py Demucs htdemucs_6s, cache par hash, verrou GPU, stems FLAC 24 bits
  app/pipeline/          (phases 3+) transcribe, postprocess, jobs
  scripts/doctor.py      Diagnostic des prérequis
  scripts/check_ml_stack.py  Test de cohabitation et d'inférence des 3 modèles ML
  tests/                 pytest
  storage/               Généré, ignoré par git :
    app.db               SQLite
    tracks/{id}/         source.<ext>, audio.wav (stéréo 44,1 kHz s16), thumbnail.jpg
    cache/stems/{wav_sha256}/htdemucs_6s/  {stem}.flac + manifest.json (écrit en dernier = cache complet)
    tmp/                 dossiers de travail (vidés automatiquement)
    models/              checkpoints (ByteDance…)
frontend/                Next.js 16 (App Router), React 19, TS strict, Tailwind 4, vitest
  app/                   Pages (/, /tracks/[id])
  components/            Composants (player/ arrivera en phase 6)
  lib/                   Client API, audio, MIDI, stores
package.json (racine)    Orchestration uniquement (concurrently)
```

## Commandes (depuis la racine)

```
npm install && npm run setup   # deps racine, venv backend (groupe ml inclus, torch CUDA), deps frontend
npm run dev                    # API sur http://127.0.0.1:8000 + web sur http://localhost:3000
npm test                       # pytest + vitest
npm run lint                   # ruff check/format + eslint + prettier + tsc
npm run format                 # ruff format + prettier --write
npm run doctor                 # diagnostic ffmpeg / Node / torch / GPU
npm run check:ml               # inférence réelle demucs + basic-pitch + ByteDance (télécharge les modèles)
```

Backend seul : `cd backend; uv run pytest`, `uv run uvicorn app.main:app --reload`.
Les tests `network` et `ml` sont exclus par défaut. Pour les lancer : `uv run pytest -m network` (ou `-m ml`).

## Décisions et pièges connus

- **Ingestion** : le type réel est détecté par les octets d'en-tête puis confirmé par ffprobe (l'extension est ignorée). Limites : `PIANO_MAX_UPLOAD_MB` (200) et `PIANO_MAX_DURATION_MIN` (20). Les erreurs utilisateur sont des `PipelineError(code, message, status)`, sérialisées en `{code, detail}`.
- **YouTube** : l'URL est réduite à l'ID de la vidéo puis reconstruite sous forme canonique (jamais de playlist, jamais l'URL brute passée à yt-dlp). yt-dlp utilise Node comme runtime JS (`js_runtimes`). Quand YouTube change, faire `cd backend; uv lock --upgrade-package yt-dlp`. Le test réseau utilise « Me at the zoo » (jNQXAC9IVRw), car la vidéo de test de youtube-dl a été supprimée.
- **Séparation** : `apply_model(split=True)` découpe en segments d'environ 8 s, donc la VRAM reste bornée quelle que soit la durée. Un verrou empêche deux séparations simultanées sur le GPU. Mesure : 19,5 s pour 3 min sur une RTX 3060 Ti, et 108 Mo de stems FLAC par morceau. La normalisation (centrage-réduction sur le mono) est identique à celle de la CLI demucs. Le cache est indexé par le hash du WAV, pas par l'id du morceau.
- **Pistes à transcrire** : `Track.transcribe_stems` (None = piano + other + bass). La batterie est exclue. Elles se modifient via `PATCH /tracks/{id}`.
- **Migrations** : `add_missing_columns` ajoute seulement des colonnes nullables. Il faudra passer à Alembic pour renommer ou transformer des colonnes.
- **Dépendances ML** : groupe uv `ml` dans `default-groups`. `uv run` installe donc toujours torch et les autres paquets (sans ce réglage, `uv run` supprimait les paquets d'un extra). Pour une machine sans ML : `uv sync --no-group ml`.
- Les routes d'import et de séparation sont synchrones (pool de threads) jusqu'à la phase 5, où elles deviendront des tâches de fond avec SSE.
- **Pas de `make`** (Windows) : `npm run …` à la racine remplace `make dev`.
- **torch / torchaudio < 2.9**, wheels **cu126** (index `pytorch-cu126` dans `pyproject.toml`) : demucs dépend des backends d'écriture torchaudio retirés en 2.9. Pour écrire les WAV, utiliser `soundfile`, pas `torchaudio.save`.
- **Basic Pitch sans TensorFlow** : sous Windows / Python 3.11, basic-pitch 0.4 exige TF 2.14, qui n'est pas installable. On l'exclut via `[tool.uv] override-dependencies`, et basic-pitch utilise automatiquement `nmp.onnx` avec `onnxruntime` (sur CPU). Les warnings « Coremltools/TFLite/Tensorflow is not installed » sont normaux.
- **`setuptools<81`** : `resampy` (une dépendance de basic-pitch) importe `pkg_resources`.
- **Checkpoint ByteDance** : la lib le télécharge avec `wget`, absent sous Windows. On le télécharge nous-mêmes dans `storage/models/` et on passe `checkpoint_path=` (voir `check_ml_stack.bytedance_checkpoint`, à déplacer dans `app/pipeline` en phase 3).
- ByteDance transcrit mal les sinusoïdes (il est entraîné sur du piano réel) : les tests de précision de la phase 3 doivent utiliser un vrai timbre de piano.
- La piste `piano` de `htdemucs_6s` est de qualité médiocre : toujours permettre de transcrire `other`.
- **Next.js 16** : les API diffèrent des versions connues. Lire `frontend/AGENTS.md` et `frontend/node_modules/next/dist/docs/` avant d'écrire du code Next.
- Le chemin du projet contient un espace (`D:\Logiciel Piano`) : toujours mettre les chemins entre guillemets dans les scripts.

## Conventions

- Python : type hints partout, fonctions courtes, ruff (ligne 100), Pydantic v2 pour les schémas d'API. Chaque étape du pipeline doit pouvoir être appelée seule (fonction pure, entrée et sortie sous forme de fichiers dans `storage/`).
- TS : `strict`, appels API typés dans `lib/api.ts`, prettier (ligne 100, plugin tailwind).
- Commentaires seulement quand ils apportent quelque chose (le « pourquoi »). Code et UI en français ou en anglais : identifiants en anglais, textes d'interface en français.
- Rien de lourd dans git (audio, stems, modèles) : tout va dans `backend/storage/`.
- Un commit par phase, après tests et lint verts.
