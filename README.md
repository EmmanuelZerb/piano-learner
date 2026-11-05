# Piano Learner

Application **locale et personnelle** pour apprendre des morceaux au piano. On importe un fichier audio (MP3, WAV, FLAC, M4A) ou une vidéo YouTube. L'application isole la « prod » par IA, la transcrit en MIDI, en tire trois arrangements (débutant, intermédiaire, avancé), puis l'affiche en **notes qui tombent** sur un clavier de 88 touches, avec un vrai son de piano, un mode entraînement au clavier MIDI et un suivi de progression.

> Outil destiné à un usage strictement personnel, sur des contenus dont vous avez le droit de disposer (morceaux achetés, libres de droits ou dont vous détenez les droits).

## Ce que fait l'application

| Étape | Outil | Résultat |
|---|---|---|
| Import | ffmpeg, yt-dlp | WAV stéréo 44,1 kHz, titre, artiste, miniature |
| Séparation | Demucs `htdemucs_6s` (GPU) | voix, batterie, basse, piano, guitare, autres |
| Transcription | ByteDance (piano : notes, vélocité, pédale), Basic Pitch (autres pistes) | un MIDI par piste et un MIDI fusionné |
| Post-traitement | librosa et règles maison | tempo, quantification, nettoyage, mains gauche/droite, tonalité, accords, 3 niveaux |
| Lecteur | Canvas, Tone.js, piano Salamander | notes qui tombent, vitesse de 25 à 150 %, boucle A-B, métronome, accompagnement par les pistes d'origine |
| Entraînement | Web MIDI | mode attente, mode libre, score, historique |
| Export | MIDI, MusicXML (music21) | partition à ouvrir dans MuseScore, corrections manuelles |

Tout tourne en local : aucun service cloud et aucune clé API.

## Prérequis

- **Windows 10/11**, macOS ou Linux. Le développement et les tests ont été faits sous Windows 11.
- **Node.js ≥ 20** (testé avec 24).
- **uv**, qui installe lui-même Python 3.11.
- **ffmpeg** (avec ffprobe) dans le PATH.
- **Navigateur Chrome ou Edge** pour le MIDI (Firefox ne gère pas la Web MIDI API sans extension).
- **GPU NVIDIA recommandé**. Testé sur une RTX 3060 Ti (8 Go) avec un pilote 610.
  - Les paquets torch utilisés embarquent CUDA 12.6 : il suffit d'un pilote NVIDIA compatible CUDA 12 (≥ 528 sous Windows), sans installer le CUDA Toolkit.
  - Sans GPU, tout fonctionne sur CPU, mais 5 à 10 fois plus lentement.
- **Espace disque** : environ 6 Go pour l'environnement Python (torch avec CUDA), environ 1 Go pour Node, plus environ 110 Mo de pistes séparées par morceau de 3 minutes.

Sous Windows :

```powershell
winget install astral-sh.uv
winget install Gyan.FFmpeg
winget install OpenJS.NodeJS.LTS
```

Ouvrir ensuite un **nouveau** terminal pour que le PATH soit à jour.

## Installation

```powershell
cd "D:\Logiciel Piano"
npm install
npm run setup      # venv Python + torch CUDA + modèles ML, dépendances web, échantillons de piano
npm run doctor     # vérifie Python, ffmpeg, Node, torch et le GPU
npm run check:ml   # optionnel : télécharge les modèles (~250 Mo) et fait une inférence de test
```

Les modèles (Demucs, ByteDance, Hugging Face) sont téléchargés dans `backend/storage/models/` au premier usage. Le cache des paquets Python est dans `backend/.uv-cache/`. Rien de lourd n'est écrit dans le profil Windows.

## Utilisation

```powershell
npm start          # usage normal : http://localhost:3000
npm run dev        # développement (rechargement automatique)
```

`npm start` nécessite une première compilation de l'interface : `npm run build`.

1. **Importer** : glisser un fichier ou coller une URL YouTube. Avec « Traiter automatiquement », la séparation, la transcription et les niveaux s'enchaînent. La progression s'affiche en direct, puis la durée de chaque étape. Le bouton « Annuler » arrête le traitement.
2. **Page du morceau** :
   - écouter chaque piste séparée et choisir celles à transcrire (par défaut piano, autres et basse ; ajouter la voix pour avoir la mélodie) ;
   - régler la transcription et le nettoyage, puis relancer seulement le post-traitement (environ 1 s) ;
   - télécharger le MIDI ou le MusicXML de chaque niveau.
3. **▶ Jouer** : le lecteur.

| Touche | Action |
|---|---|
| Espace | lecture / pause |
| ← → (Maj : pas de 1 s) | reculer / avancer de 5 s |
| ↑ ↓ | vitesse ± 5 % |
| A, B, Échap | début de boucle, fin de boucle, supprimer la boucle |
| G, D | couper la main gauche, la main droite |
| 1, 2, 3 | niveau débutant, intermédiaire, avancé |
| M, C, N | métronome, décompte, nom des notes |
| + / - | zoom vertical |
| E, Suppr | mode édition, supprimer la note sélectionnée |
| F | fluidité et dérive (diagnostic) |

4. **Entraînement** (panneau sous le lecteur) :
   - Brancher le clavier MIDI, puis cliquer sur « Connecter un clavier MIDI » (le navigateur demande l'autorisation). Sans clavier, on peut cliquer sur les touches à l'écran.
   - **Attente** : la lecture s'arrête avant chaque note ou accord jusqu'à ce qu'il soit joué.
   - **Libre** : la lecture continue et chaque note est jugée juste, fausse ou manquée (±150 ms).
   - On peut travailler une main pendant que l'autre est jouée automatiquement.
   - « Terminer la séance » affiche le bilan et l'enregistre dans l'historique, visible dans la bibliothèque.
5. **Éditeur** (bouton « Éditer » ou touche E) :
   - Cliquer une note pour la corriger : demi-ton, octave, main, suppression.
   - On peut aussi redéfinir le partage des mains sur un passage délimité par une boucle A-B.
   - Les corrections sont conservées si on recalcule les niveaux.

## Commandes

| Commande | Rôle |
|---|---|
| `npm run setup` | installe tout (Python, Node, échantillons) |
| `npm start` / `npm run dev` | lance l'API (port 8000) et l'interface (port 3000) |
| `npm run build` | compile l'interface pour `npm start` |
| `npm test` | tests rapides, sans modèles ni réseau |
| `npm run test:full` | tous les tests, dont les vrais modèles et un pipeline complet (environ 2 min) |
| `npm run lint` / `npm run format` | ruff, eslint, prettier, tsc |
| `npm run doctor` / `npm run check:ml` | diagnostic de l'installation |

## Configuration

Variables d'environnement, ou fichier `backend/.env` :

| Variable | Défaut | Rôle |
|---|---|---|
| `PIANO_STORAGE_DIR` | `backend/storage` | base de données, médias, caches, modèles |
| `PIANO_MODELS_PATH` | `<storage>/models` | modèles téléchargés |
| `PIANO_MAX_UPLOAD_MB` | 200 | taille maximale d'un fichier importé |
| `PIANO_MAX_DURATION_MIN` | 20 | durée maximale d'un morceau |
| `PIANO_LOG_FORMAT` | `json` | `json` (une ligne par événement) ou `text` |
| `PIANO_LOG_LEVEL` | `INFO` | niveau de log |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | adresse de l'API vue par l'interface |

Les logs JSON de l'API décrivent chaque étape. Par exemple, `step_done` contient `step`, `duration_s` et `track_id`, et `job_finished` contient `timings` et `total_s`. Ils permettent de suivre les temps d'exécution.

## Performances mesurées

Morceau de 3 min, RTX 3060 Ti, i7-8700 :

| Étape | Durée |
|---|---|
| Séparation Demucs (6 pistes) | 19,5 s |
| Transcription de 3 pistes (modèles déjà chargés) | 10 à 50 s |
| Post-traitement (3 niveaux) | 8 s la première fois, 1 s ensuite |
| Export MusicXML (niveau avancé) | 7 s |
| Lecteur | 72 images/s, dérive image/son ≤ 3,2 ms |

Un pipeline complet sur une vidéo YouTube de 19 s prend 29 s.

## Limites connues

- **La transcription automatique n'est jamais parfaite**, surtout sur des productions denses (synthés, reverb, effets). C'est pourquoi le post-traitement se relance seul en environ 1 s, avec d'autres réglages, et pourquoi l'éditeur existe.
- **La piste « piano » de Demucs est souvent incomplète** : une partie du piano se retrouve dans « autres ». Garder « autres » dans les pistes transcrites.
- **ByteDance n'est fiable que sur un vrai son de piano.** Pour les autres instruments, Basic Pitch est utilisé. Basic Pitch produit des doublons à l'octave, surtout sur la basse ; le nettoyage en retire une partie.
- **Détection des temps** : librosa peut se caler sur le contretemps quand les charlestons dominent la grosse caisse. La quantification à la croche n'en souffre pas, mais les accords détectés sont décalés.
- **Partition MusicXML** : elle est arrondie à la double croche, donc les triolets sont approximés. Une transcription dense donne une partition « avancé » chargée.
- **Accompagnement hors 100 %** : l'étirement temporel de l'audio d'origine ajoute un léger grain.
- **Annulation d'une tâche** : elle est immédiate pendant le téléchargement et la séparation. Pendant la transcription du piano, elle prend effet à la fin de la piste en cours (environ 20 s pour 3 min).
- **Une tâche à la fois** : le GPU n'est pas partagé.
- **YouTube** change souvent : en cas d'erreur de téléchargement, mettre à jour yt-dlp (voir Dépannage).

## Dépannage

| Symptôme | Solution |
|---|---|
| « ffmpeg absent » dans l'état du système | installer ffmpeg et rouvrir le terminal |
| Échec de téléchargement YouTube, « anti-robot » | `cd backend; uv lock --upgrade-package yt-dlp; uv sync`, puis réessayer plus tard |
| « Échantillons de piano introuvables » | `npm --prefix frontend run fetch:samples` |
| Le clavier MIDI n'apparaît pas | Chrome ou Edge ; autoriser l'accès au MIDI ; brancher le clavier avant de cliquer sur « Connecter » (la liste se met aussi à jour à chaud) |
| « Calcul : CPU » alors qu'on a un GPU NVIDIA | mettre à jour le pilote NVIDIA, puis `npm run doctor` |
| Port 8000 ou 3000 déjà utilisé | arrêter l'instance précédente (Ctrl+C dans son terminal) |
| Disque système plein | les caches sont dans le projet : `backend/.uv-cache` peut être supprimé sans risque, et `backend/storage/cache` aussi (les pistes et transcriptions seront recalculées) |

## Licences des composants

Demucs (MIT), Basic Pitch (Apache 2.0), piano_transcription_inference de ByteDance (Apache 2.0), music21 (BSD), Tone.js (MIT), échantillons **Salamander Grand Piano** par Alexander Holm (CC-BY 3.0).

## Développement

Voir [CLAUDE.md](CLAUDE.md) pour l'architecture, les conventions et les décisions techniques.
