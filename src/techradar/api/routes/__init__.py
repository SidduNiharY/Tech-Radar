"""The `/v1` routes. main.create_app mounts every router here behind require_caller."""

from __future__ import annotations

from fastapi import APIRouter

from techradar.api.routes import ask, models, practice, quiz, settings, today

ROUTERS: tuple[APIRouter, ...] = (
    today.router,
    ask.router,
    practice.router,
    quiz.router,
    settings.router,
    models.router,
)
