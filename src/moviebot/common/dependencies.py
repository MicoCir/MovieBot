# src/moviebot/common/dependencies.py
"""Runtime wiring: resolución de índice activo y creación de componentes."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from moviebot.agents.netflix.intent_extractor import LlmIntentExtractor
from moviebot.repositories.netflix_meilisearch import MeilisearchNetflixRepository

if TYPE_CHECKING:
    from moviebot.common.config import Settings

logger = logging.getLogger(__name__)


def resolve_active_index(settings: Settings) -> str:
    """Resuelve el nombre del índice Meilisearch activo.

    Precedencia:
    1. Si settings.meilisearch_index está seteado (no None) → usar como override.
    2. Si no → leer active_index desde index_registry.json.
    3. Si el registry no existe o es inválido → raise error explícito.

    Returns:
        Nombre del índice Meilisearch activo.

    Raises:
        FileNotFoundError: si meilisearch_index es None y el registry no existe.
        ValueError: si el registry JSON es inválido o no contiene active_index.
    """
    if settings.meilisearch_index is not None:
        return settings.meilisearch_index

    registry_path = settings.meilisearch_registry_path

    if not registry_path.exists():
        raise FileNotFoundError(
            f"No se puede resolver el índice activo: "
            f"meilisearch_index no está configurado y el registry "
            f"no existe en {registry_path}"
        )

    try:
        content = registry_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(
            f"El registry en {registry_path} no es un JSON válido: {exc}"
        ) from exc

    active_index = data.get("active_index")
    if not active_index:
        raise ValueError(f"El registry en {registry_path} no contiene 'active_index'")

    return active_index


def create_netflix_repository(settings: Settings) -> MeilisearchNetflixRepository:
    """Crea una instancia de MeilisearchNetflixRepository con el índice activo.

    Args:
        settings: Configuración del proyecto.

    Returns:
        Instancia configurada del repository.
    """
    index_name = resolve_active_index(settings)
    api_key = (
        settings.meilisearch_api_key.get_secret_value()
        if settings.meilisearch_api_key
        else None
    )

    return MeilisearchNetflixRepository(
        meilisearch_url=settings.meilisearch_url,
        meilisearch_api_key=api_key,
        index_name=index_name,
    )


def create_intent_extractor(settings: Settings) -> LlmIntentExtractor:
    """Crea una instancia de LlmIntentExtractor con el modelo configurado.

    Args:
        settings: Configuración del proyecto.

    Returns:
        Instancia configurada del intent extractor.
    """
    client = AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
    )

    return LlmIntentExtractor(
        openai_client=client,
        model=settings.openai_model,
    )
