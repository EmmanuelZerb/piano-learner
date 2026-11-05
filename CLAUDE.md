# CLAUDE.md — Piano Learner

Application web locale et personnelle. Elle prend un audio (fichier ou URL YouTube), sépare les stems (Demucs), transcrit en MIDI (ByteDance pour le piano, Basic Pitch pour le reste), post-traite le résultat (quantification, mains, difficulté), puis l'affiche en « notes qui tombent » façon Synthesia.

## État d'avancement

| Phase | Statut |
|---|---|
| 0 — Initialisation (monorepo, `/health`, test de la stack ML) | ✅ |
| 1 — Ingestion audio (upload + YouTube → WAV 44,1 kHz) | ✅ |
| 2 — Séparation des sources (Demucs htdemucs_6s, cache par hash) | ✅ |
| 3 — Transcription (ByteDance + Basic Pitch, cache par paramètres) | ✅ |
| 4 — Post-traitement (tempo, quantification, mains, niveaux, tonalité, accords) | ✅ |
| 5 — API et tâches asynchrones (SSE, annulation, suppression) | ✅ |
| 6 — Lecteur « notes qui tombent » (Canvas, Tone.js, accompagnement) | ✅ |
| 7 — Mode entraînement (MIDI, attente, libre, score, historique) | ✅ |
| 8 — Bibliothèque, export MusicXML, éditeur de corrections | ✅ |
| 9 — Qualité et finitions | ⏳ à faire |

## Architecture

```
backend/                 Python 3.11, géré par uv (pyproject.toml + uv.lock)
  app/main.py            create_app(settings) : moteur DB, JobManager (lifespan), CORS, handler PipelineError, /health
  app/jobs.py            JobManager : file asyncio + 1 worker (thread), progression en mémoire → SSE, annulation, reprise au démarrage ; run_process
  app/config.py          Settings (pydantic-settings, préfixe d'env PIANO_, backend/.env)
  app/system.py          Détection ffmpeg/ffprobe et du device torch (cuda/mps/cpu)
  app/db.py              Moteur SQLite, migration minimale (add_missing_columns), get_session
  app/models/            Tables SQLModel (Track avec transcribe_stems, Job, PracticeSession)
  app/workflow.py        Enchaînement par morceau : separate → transcribe (→ arrange auto) ; arrange seul
  app/library.py         Dossiers de travail temporaires, enregistrement et déduplication (hash du WAV)
  app/api/deps.py        Dépendances communes (session, settings, get_track_or_404)
  app/api/tracks.py      Routes /tracks : upload, youtube, liste, détail, PATCH sélection, audio, miniature
  app/api/stems.py       Routes /tracks/{id}/separate, /stems, /stems/{name}
  app/api/transcription.py  /tracks/{id}/transcribe (sépare si besoin + régénère les niveaux), /transcription, /midi/{f}.mid, /transcription/defaults
  app/api/arrangement.py /tracks/{id}/arrange (post-traitement seul), /arrangement, /arrangement/{niveau}.mid|.json,
                         /arrangement/{niveau}/edits (GET/POST/DELETE ?last=), /export/{niveau}.musicxml, /arrangement/defaults
  app/api/library.py     GET /library : morceaux + étape (importé → prêt à jouer), niveaux, progression, tâche active
  app/api/practice.py    POST/GET /tracks/{id}/practice : séances d'entraînement, meilleur score, temps total
  app/api/jobs.py        /jobs/youtube, /jobs/upload, /tracks/{id}/jobs, /jobs, /jobs/{id}, /jobs/{id}/events (SSE), /jobs/{id}/cancel
  app/api/files.py       serve_track_file : fichiers générés, protégé contre la sortie du dossier
  app/pipeline/ingest.py Validation (octets d'en-tête + ffprobe), yt-dlp, normalisation ffmpeg
  app/pipeline/errors.py PipelineError(code, message, status) → {code, detail}
  app/pipeline/separate.py Demucs htdemucs_6s, cache par hash, verrou GPU, stems FLAC 24 bits
  app/pipeline/gpu.py    Verrou GPU partagé (Demucs, ByteDance)
  app/pipeline/notes.py  Format pivot Note/Pedal/StemTranscription (JSON) : entrée du post-traitement
  app/pipeline/transcribe.py  ByteDance (piano) / Basic Pitch (autres), paramètres, cache, manifest
  app/pipeline/midi_io.py  Export pretty_midi : un instrument (= un canal) par stem, CC64 pour la pédale
  app/pipeline/cleanup.py   Tessiture A0–C8, vélocité min, doublons entre stems, notes courtes
  app/pipeline/rhythm.py    BeatGrid (librosa + régularisation), position en temps, quantification
  app/pipeline/hands.py     Partage des mains par coût (heuristique isolée, remplaçable)
  app/pipeline/harmony.py   Tonalité (Krumhansl-Schmuckler), accords par temps (gabarits)
  app/pipeline/difficulty.py  Niveaux débutant / intermédiaire / avancé, cap_polyphony
  app/pipeline/postprocess.py PostprocessParams, arrange(), base + corrections → .json/.mid/manifest
  app/pipeline/edits.py     Corrections manuelles (delete, pitch, hand, split) rejouées sur la base
  app/pipeline/notation.py  Export MusicXML (music21) : 2 portées, armure, tempo, double croche
  scripts/doctor.py      Diagnostic des prérequis
  scripts/check_ml_stack.py  Test de cohabitation et d'inférence des 3 modèles ML
  tests/                 pytest ; tests/synth.py = audio de test (synthé additif, Salamander, F1 mir_eval)
  storage/               Généré, ignoré par git :
    app.db               SQLite
    tracks/{id}/         source.<ext>, audio.wav (stéréo 44,1 kHz s16), thumbnail.jpg
    cache/stems/{wav_sha256}/htdemucs_6s/  {stem}.flac + manifest.json (écrit en dernier = cache complet)
    cache/transcriptions/{wav_sha256}/{stem}-{moteur}-{hash params}.json  notes brutes
    tracks/{id}/midi/    {stem}.mid, merged.mid, manifest.json (dernière transcription)
    tracks/{id}/arrangement/  {niveau}.base.json (calculé), {niveau}.json/.mid (corrigé), edits.json,
                              {niveau}.musicxml (généré à la demande), manifest.json
    cache/analysis/{wav_sha256}/beats.json  grille des temps
    models/salamander-test/  échantillons de piano pour le test ByteDance
    tmp/                 dossiers de travail (vidés automatiquement)
    models/              checkpoints (ByteDance…)
frontend/                Next.js 16 (App Router), React 19, TS strict, Tailwind 4, vitest
  app/                   Pages (/, /tracks/[id], /tracks/[id]/play)
  components/            LibraryView (accueil), panneaux de la page morceau, JobProgress, Slider
  components/player/     PlayerView (chargement, boucle rAF, raccourcis, clavier à la souris), PlayerControls,
                         usePractice (arbitre, attente, séance), useMidi, PracticePanel (+ bilan), EditorPanel
  lib/player/            engine.ts (Tone), renderer.ts (Canvas), notes.ts, keyboard.ts, practice.ts
                         (PracticeJudge, waitSteps), midi.ts (Web MIDI),
                         shortcuts.ts, store.ts (Zustand), samples.mjs (liste Salamander)
  scripts/fetch-samples.mjs  Télécharge Salamander dans public/samples/ (ignoré par git)
  lib/                   Client API, audio, MIDI, stores
package.json (racine)    Orchestration uniquement (concurrently)
```

## Commandes (depuis la racine)

```
npm install && npm run setup   # deps racine, venv backend (groupe ml inclus, torch CUDA), deps frontend
npm run dev                    # API sur http://127.0.0.1:8000 + web sur http://localhost:3000
npm test                       # pytest (sans ml/network) + vitest
npm run test:full              # tous les tests, y compris modèles réels et réseau (environ 1 min)
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
- **Post-traitement** : relit les JSON de transcription et `beats.json`, sans aucun modèle. Relancer prend environ 1 s (8 s la première fois, à cause de la détection des temps). La transcription régénère automatiquement les niveaux avec les derniers `PostprocessParams`.
- **Ordre** : vélocité → tessiture → doublons → durée → quantification (en position de temps, donc elle suit le tempo) → mains → tonalité et accords → niveaux.
- **Niveaux** :
  - Débutant : mélodie en « skyline » (piste voix si transcrite, remontée en Do4–Mi6), fondamentale de chaque accord en Sol2–Sol3. Au plus 1 note par main, vérifié par un test sur 10 morceaux aléatoires.
  - Intermédiaire : quantification à la croche à 100 %, au plus 3 notes par main ; on garde les voix extérieures.
  - Avancé : tout le nettoyé.
- **Format JSON d'un niveau** (lu par le lecteur en phase 6) : `{level, tempo, beats[], key, chords[[s,e,nom]], pedals[[s,e]], notes[[pitch,start,end,vel,hand]]}`. Les temps sont en secondes réelles de l'audio.
- **MIDI d'arrangement** (mido) :
  - Une piste Tempo (tempo, armure, 4/4, accords en `marker`), puis Main droite (canal 0) et Main gauche (canal 1).
  - Carte de tempo construite sur les temps détectés (un seul tempo si la grille est régulière).
  - Des temps de levée sont ajoutés avant le premier temps détecté. Le MIDI est donc décalé de quelques fractions de seconde par rapport à l'audio, contrairement au JSON.
- **Limite connue** : librosa peut se caler sur les contretemps quand les charlestons dominent la grosse caisse (décalage d'un demi-temps, vu sur le morceau synthétique). L'impact sur la quantification à la croche est nul, mais les fenêtres d'accords sont décalées. Un réglage manuel de la phase sera à prévoir dans l'éditeur (phase 8).
- **Tâches de fond** :
  - Le frontend passe uniquement par `/jobs`. Les routes synchrones (`/tracks/upload`, `/tracks/youtube`, `/separate`, `/transcribe`, `/arrange`) restent disponibles pour les scripts et les tests ; elles utilisent les mêmes fonctions de `workflow.py`.
  - Un seul worker : les traitements passent les uns après les autres.
  - Une tâche « process » enchaîne import (YouTube ou fichier), séparation, transcription et niveaux, jusqu'à l'étape `options.until` (ingest, separate ou transcribe).
  - Progression globale : download 0–15 %, convert 10–15 %, separate 15–55 %, transcribe 55–95 %, arrange 95–100 %.
  - L'état courant vit en mémoire (`JobManager._live`) ; la base n'est écrite qu'aux changements d'étape ou de statut. SSE : un `data: <JobRead JSON>` par mise à jour, `: ping` toutes les 15 s.
  - Upload : la copie et la vérification du type se font pendant la requête (415/413 immédiats) ; ffprobe et la conversion se font dans la tâche. Les fichiers en attente sont dans `tmp/` et le worker les nettoie.
  - Au démarrage, les tâches non terminées passent en `error/interrupted` et `tmp/` est vidé.
- **Annulation** : coopérative, via `Cancelled` levée par les callbacks de progression.
  - yt-dlp : `DownloadCancelled` dans le hook de progression.
  - Demucs : callback par segment (réagit en moins d'une seconde).
  - Transcription : entre deux stems seulement. ByteDance traite une piste d'un bloc (environ 15–20 s pour 3 min), d'où ce délai avant l'arrêt.
  - Une tâche annulée ne laisse pas de manifest partiel. Les caches déjà écrits restent valides.
- **Suppression** (`DELETE /tracks/{id}`) : dossier du morceau, caches stems/notes/temps (par hash) et tâches associées. Elle est refusée (409) si une tâche est active sur le morceau.
- SQLite en WAL avec un timeout de 30 s : l'API lit pendant que le worker écrit.
- Mesure : YouTube « Me at the zoo » (19 s) traité de bout en bout en 29 s (téléchargement, séparation, transcription, niveaux).
- **Pas de `make`** (Windows) : `npm run …` à la racine remplace `make dev`.
- **torch / torchaudio < 2.9**, wheels **cu126** (index `pytorch-cu126` dans `pyproject.toml`) : demucs dépend des backends d'écriture torchaudio retirés en 2.9. Pour écrire les WAV, utiliser `soundfile`, pas `torchaudio.save`.
- **Basic Pitch sans TensorFlow** : sous Windows / Python 3.11, basic-pitch 0.4 exige TF 2.14, qui n'est pas installable. On l'exclut via `[tool.uv] override-dependencies`, et basic-pitch utilise automatiquement `nmp.onnx` avec `onnxruntime` (sur CPU). Les warnings « Coremltools/TFLite/Tensorflow is not installed » sont normaux.
- **`setuptools<81`** : `resampy` (une dépendance de basic-pitch) importe `pkg_resources`.
- **Checkpoint ByteDance** : la lib le télécharge avec `wget`, absent sous Windows. `transcribe.ensure_bytedance_checkpoint` le télécharge dans `storage/models/`. Les seuils se règlent par attributs de l'instance, et l'attribut `offset_threshod` est bien écrit ainsi dans la lib.
- **Précision mesurée** (gamme de do, F1 mir_eval, onset à ±50 ms) :
  - Basic Pitch : 100 % sur le synthé additif, 94 % sur les échantillons Salamander.
  - ByteDance : 100 % sur Salamander, mais seulement 82 % sur le synthé additif, parce qu'il est entraîné sur du vrai piano. Son test utilise donc `render_with_samples`.
  - Transposer un échantillon **vers le haut** fait apparaître des octaves fantômes chez ByteDance : le rendu de test ne transpose que vers le bas.
- **Cache de transcription** : la clé contient le stem, le moteur et les paramètres propres à ce moteur. Changer un seuil Basic Pitch ne relance donc pas ByteDance. `TranscribeParams` (Pydantic) sert à la fois au pipeline et à l'API.
- Basic Pitch fragmente beaucoup et produit des doublons à l'octave sur la basse : c'est attendu, et le nettoyage se fait en phase 4. Sur un mixage synthétique, Demucs range les accords dans `other`, et la piste piano peut alors rester vide.
- La piste `piano` de `htdemucs_6s` est de qualité médiocre : toujours permettre de transcrire `other`.
- **Next.js 16** : les API diffèrent des versions connues. Lire `frontend/AGENTS.md` et `frontend/node_modules/next/dist/docs/` avant d'écrire du code Next.
- **Lecteur — horloge** :
  - Tout est piloté par `Tone.Transport` avec PPQ = 960 et 60 BPM de base : 1 temps = 1 s du morceau, et `ticks / PPQ` donne la position.
  - Vitesse = `bpm × vitesse` : les notes programmées une fois dans un `Tone.Part` ne bougent pas.
  - L'image lit `transport.getTicksAtTime(currentTime - outputLatency)` à chaque `requestAnimationFrame`. Aucun `setInterval`, donc pas de dérive par construction.
  - `window.__playerStats` expose les images/s, la pire image et la dérive mesurée (instantanées et cumulées sur la session).
- **Lecteur — son** :
  - Tone.Sampler avec les échantillons Salamander (un toutes les 3 demi-tons), servis localement depuis `/samples/salamander/`.
  - Le sustain est appliqué en prolongeant la note jusqu'au relâchement de la pédale (`sustainedEnds`). Le niveau débutant n'a pas de pédale.
  - Main coupée : la note n'est pas jouée et elle est affichée à 25 % d'opacité.
  - Métronome : un clic par temps détecté, accent tous les 4 temps. Décompte : 4 clics avant `transport.start`.
- **Accompagnement** (stems ou mixage d'origine) :
  - Buffers chargés à la demande.
  - À 100 % de vitesse : `Tone.Player`. Sinon : `Tone.GrainPlayer`, qui change la vitesse sans changer la hauteur, avec un léger grain.
  - Il est relancé à la bonne position à chaque lecture, saut, changement de vitesse et tour de boucle (événement `loop` du Transport).
- **Rendu** :
  - Canvas 2D sans React dans la boucle d'image : la position n'est pas dans le store. La barre de progression et le temps sont mis à jour par des refs.
  - `notesInWindow` fait une recherche dichotomique, avec une marge égale à la durée de la plus longue note.
  - Couleurs : main droite en vert, main gauche en bleu, plus foncé sur les touches noires.
- `@tonejs/midi` n'est pas utilisé : le lecteur lit le JSON des niveaux, qui contient en plus les mains, les temps et les accords.
- **Entraînement** :
  - Entrées : clavier MIDI (Web MIDI, accès demandé au clic, branchement à chaud) ou clic/glissé sur le clavier à l'écran. Les deux passent par `usePractice.noteOn/noteOff`.
  - Main travaillée : elle n'est pas jouée par le lecteur ; l'autre main l'est.
- **Mode attente** :
  - Un `Tone.Part` place un point d'arrêt 1 tick avant chaque attaque (accord = notes à moins de 60 ms).
  - Le callback, appelé avec l'anticipation de Tone, fait `transport.pause(time)` sauf si l'accord est déjà tenu.
  - `resume()` repart au plus tôt juste après l'instant d'arrêt (sinon la pause programmée bloquerait la reprise). `resumedFrom` ignore l'arrêt d'où l'on repart.
- **Arbitrage** (`PracticeJudge`) :
  - Juste = même hauteur à ±150 ms en temps réel (× vitesse en temps du morceau), la note attendue la plus proche.
  - Fausse = toute autre touche. Manquée = note dépassée sans avoir été jouée (mode libre seulement).
  - Un retour en arrière (boucle, saut) rend le passage rejouable sans effacer le score.
  - Précision = justes / (justes + fausses + manquées).
- **Séance** : chronométrée pendant la lecture et l'attente. « Terminer la séance » (ou la fin du morceau) affiche le bilan, puis l'enregistre via POST /practice si au moins une note a été jugée.
- **Position à l'arrêt** : `songTime()` lit `transport.ticks` (à « maintenant ») quand le Transport n'avance pas. Avant ce correctif, un saut fait en pause n'était visible qu'après l'anticipation de Tone (≈ 100 ms), et A/B enregistraient une position périmée.
- **Corrections (éditeur)** :
  - Une note est désignée par sa hauteur et son attaque (±40 ms). Les opérations sont rejouées dans l'ordre sur `{niveau}.base.json`, donc elles survivent à un recalcul du post-traitement.
  - Une correction qui ne trouve plus sa note est ignorée et comptée (`unmatched_edits`, signalée sur la page du morceau).
  - « split » réassigne les mains sur [début, fin[ (boucle A-B) selon une hauteur de partage.
  - Dans le lecteur : touche E ou bouton « Éditer » (met en pause), clic sur une note (`noteAtPoint`, les notes sur touches noires sont prioritaires), ±½ ton, ±octave, main, Suppr. Puis rechargement du niveau via `levelReload`.
- **MusicXML** :
  - Positions en temps sur la grille détectée, avec les mêmes temps de levée que le MIDI, arrondies à la double croche.
  - `chordify(addTies=True)` par main transforme les chevauchements en accords liés.
  - Généré à la demande (environ 7 s pour le niveau avancé de 3 min), puis mis en cache jusqu'à la prochaine modification du niveau. 3 min à 100 BPM donnent bien 75 mesures.
  - Les triolets sont arrondis à la double croche.
- **Bibliothèque** : l'accueil utilise `/library`, avec recherche titre/artiste insensible aux accents (`lib/library.ts`), étape de traitement, progression d'entraînement et tâche en cours.
- **Diagnostic** : `window.__pianoEngine` (développement uniquement) et `window.__playerStats`.
- **Vérifié sans clavier MIDI**, par des clics simulés sur le clavier à l'écran : attente en boucle 0–5 s (29 étapes, arrêt à chacune, reprise et nouvelle attente après chaque tour), fausse note sans déblocage, mode libre (justes/fausses/manquées), séance enregistrée.
- **Mesures du lecteur** (morceau test, niveau avancé, 60 %, voix et batterie en accompagnement) :
  - Page visible : 72 images/s (la fréquence de l'écran), pire image de 15 ms. Dérive entre l'image et l'horloge audio : 3,2 ms au maximum.
  - Onglet masqué : le navigateur bride `requestAnimationFrame` (jusqu'à 1 image/s) et l'audio. Les mesures ne valent donc que page visible.
  - La touche F affiche ces indicateurs en direct sur le lecteur.
- Le chemin du projet contient un espace (`D:\Logiciel Piano`) : toujours mettre les chemins entre guillemets dans les scripts.

## Conventions

- Python : type hints partout, fonctions courtes, ruff (ligne 100), Pydantic v2 pour les schémas d'API. Chaque étape du pipeline doit pouvoir être appelée seule (fonction pure, entrée et sortie sous forme de fichiers dans `storage/`).
- TS : `strict`, appels API typés dans `lib/api.ts`, prettier (ligne 100, plugin tailwind).
- Commentaires seulement quand ils apportent quelque chose (le « pourquoi »). Code et UI en français ou en anglais : identifiants en anglais, textes d'interface en français.
- Rien de lourd dans git (audio, stems, modèles) : tout va dans `backend/storage/`.
- Un commit par phase, après tests et lint verts.
