from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.config import Settings
from app.db import get_session
from app.models import Track

SessionDep = Annotated[Session, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_track_or_404(session: Session, track_id: str) -> Track:
    track = session.get(Track, track_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Morceau introuvable.")
    return track
