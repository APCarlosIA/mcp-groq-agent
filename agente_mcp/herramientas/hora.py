"""Herramienta `hora_actual`: fecha y hora actuales en una zona horaria IANA.

Solo se aceptan nombres que existan en la base de datos de zonas horarias, de modo
que ninguna entrada del usuario o del LLM llega nunca al sistema de archivos.
"""

import logging
from datetime import UTC, datetime
from functools import cache
from zoneinfo import ZoneInfo, available_timezones

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

logger = logging.getLogger(__name__)

LONGITUD_MAXIMA = 64  # los nombres IANA reales son bastante más cortos


class ErrorHora(ValueError):
    """Error controlado: su mensaje es seguro de mostrar al LLM."""


@cache
def _zonas_por_minuscula() -> dict[str, str]:
    """Mapa 'europe/madrid' -> 'Europe/Madrid' (lista blanca de zonas válidas).

    Se calcula una sola vez porque available_timezones() recorre el disco.
    """
    return {zona.lower(): zona for zona in available_timezones()}


def hora_en(zona: str, instante: datetime | None = None) -> str:
    """Devuelve el instante dado en la zona indicada, en formato ISO 8601.

    Args:
        zona: nombre IANA ('Europe/Madrid'). No distingue mayúsculas.
        instante: momento a convertir, con zona horaria. Por defecto, ahora mismo.
            Existe para poder testear sin depender del reloj.

    Raises:
        ErrorHora: si la zona está vacía, es demasiado larga o no existe.
    """
    zona = zona.strip()
    if not zona:
        raise ErrorHora("La zona horaria está vacía.")
    if len(zona) > LONGITUD_MAXIMA:
        raise ErrorHora(f"La zona horaria supera los {LONGITUD_MAXIMA} caracteres.")

    nombre = _zonas_por_minuscula().get(zona.lower())
    if nombre is None:
        raise ErrorHora(
            "Zona horaria desconocida. Usa un nombre IANA como 'Europe/Madrid' "
            "o 'America/New_York'."
        )

    instante = instante or datetime.now(UTC)
    local = instante.astimezone(ZoneInfo(nombre))
    return f"{local.isoformat(timespec='seconds')} ({nombre})"


def registrar(mcp: MCPServer) -> None:
    """Registra la herramienta `hora_actual` en el servidor MCP."""

    @mcp.tool()
    def hora_actual(zona_horaria: str = "UTC") -> str:
        """Devuelve la fecha y hora actuales en una zona horaria.

        Usa nombres IANA como 'Europe/Madrid', 'America/New_York' o 'Asia/Tokyo'.
        Si no se indica zona, devuelve la hora en UTC.
        Ejemplo de resultado: '2026-10-15T20:50:12+02:00 (Europe/Madrid)'.
        """
        logger.debug("hora_actual invocada")
        try:
            return hora_en(zona_horaria)
        except ErrorHora as e:
            raise ToolError(str(e)) from e