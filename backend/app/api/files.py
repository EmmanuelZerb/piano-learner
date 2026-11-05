from pathlib import Path

from fastapi import HTTPException, status
from fastapi.responses import FileResponse

MEDIA_TYPES = {".mid": "audio/midi", ".json": "application/json"}


def serve_track_file(directory: Path, filename: str, title: str) -> FileResponse:
    """Sert un fichier généré. Le nom vient de l'URL : on refuse tout ce qui sort du dossier."""
    directory = directory.resolve()
    path = (directory / filename).resolve()
    media_type = MEDIA_TYPES.get(path.suffix)
    if media_type is None or path.parent != directory or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier introuvable.")
    if path.suffix == ".mid":  # téléchargement nommé d'après le morceau
        return FileResponse(path, media_type=media_type, filename=f"{title} - {path.name}")
    return FileResponse(path, media_type=media_type)
