"""Lectura de una guía de redacción aprobada en Google Docs."""

import os
import re

import google.auth
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from requests import RequestException


DOCS_SCOPE = "https://www.googleapis.com/auth/documents.readonly"
RECURSO_ID = re.compile(r"[A-Za-z0-9_-]+")
MAX_CARACTERES_GUIA = 12_000


def recurso_configurado(clave: str, secretos) -> str:
    valor = os.environ.get(clave, "")
    if not valor:
        try:
            valor = secretos.get(clave, "")
        except OSError:
            return ""
    valor = valor.strip() if isinstance(valor, str) else ""
    return valor if RECURSO_ID.fullmatch(valor) else ""


def validar_guia(texto: str) -> str:
    texto = texto.strip()
    if not texto:
        raise ValueError("La guía de redacción está vacía.")
    if len(texto) > MAX_CARACTERES_GUIA:
        raise ValueError(f"La guía admite hasta {MAX_CARACTERES_GUIA:,} caracteres.")
    return texto


def leer_guia(documento_id: str) -> tuple[str, str]:
    """Lee el título y los párrafos de la primera pestaña de un único documento."""
    if not RECURSO_ID.fullmatch(documento_id):
        raise ValueError("Configurá el ID del Google Doc con la guía aprobada.")
    try:
        credenciales, _ = google.auth.default(scopes=[DOCS_SCOPE])
        with AuthorizedSession(credenciales, refresh_timeout=10) as sesion:
            respuesta = sesion.get(
                f"https://docs.googleapis.com/v1/documents/{documento_id}",
                params={
                    "fields": "title,body(content(paragraph(elements(textRun(content)))))",
                    "suggestionsViewMode": "PREVIEW_WITHOUT_SUGGESTIONS",
                },
                timeout=10,
            )
            respuesta.raise_for_status()
            documento = respuesta.json()
    except (GoogleAuthError, RequestException, ValueError) as error:
        raise RuntimeError(
            "No se pudo leer la guía. Verificá las credenciales, el permiso de lectura y la API de Google Docs."
        ) from error

    parrafos = documento.get("body", {}).get("content", [])
    texto = "".join(
        elemento.get("textRun", {}).get("content", "")
        for bloque in parrafos
        for elemento in bloque.get("paragraph", {}).get("elements", [])
    )
    return documento.get("title") or "Guía de redacción", validar_guia(texto)
