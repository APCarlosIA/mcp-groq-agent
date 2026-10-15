"""Cliente MCP: lanza el servidor, descubre sus herramientas y las ejecuta.

Es la capa que usará el agente. Oculta los detalles del SDK y devuelve siempre
resultados acotados (en tamaño y en tiempo) en lugar de lanzar excepciones, para
que el fallo de una herramienta no tumbe la conversación.
"""

import argparse
import json
import logging
import os
import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
from mcp import Client, MCPError, StdioServerParameters
from mcp.server.mcpserver import MCPServer
from mcp.types import ContentBlock, TextContent, Tool

logger = logging.getLogger(__name__)

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]  # <raíz>/agente_mcp/cliente.py
TIMEOUT_LLAMADA = 30.0  # segundos máximos por llamada a una herramienta
MAX_RESULTADO = 4_000  # caracteres máximos que se devuelven al LLM
_MARCA_TRUNCADO = "… [resultado truncado]"
# Variables del entorno que se reenvían al servidor. El resto (incluida la API key
# de Groq) no se comparte con el subproceso.
VARIABLES_PARA_EL_SERVIDOR = ("NOTAS_DIR",)


@dataclass(frozen=True, slots=True)
class ResultadoHerramienta:
    """Resultado de ejecutar una herramienta, listo para entregárselo al LLM."""

    texto: str
    es_error: bool = False


def parametros_servidor_local() -> StdioServerParameters:
    """Parámetros para lanzar nuestro servidor como subproceso (transporte stdio)."""
    # El subproceso no hereda nuestro entorno (ni secretos): solo recibe esto
    entorno = {"PYTHONPATH": str(RAIZ_PROYECTO)}
    for variable in VARIABLES_PARA_EL_SERVIDOR:
        if variable in os.environ:
            entorno[variable] = os.environ[variable]
    return StdioServerParameters(
        # sys.executable es el Python que ejecuta este programa (el del .venv)
        command=sys.executable,
        args=["-m", "agente_mcp.servidor"],
        env=entorno,
    )


def _extraer_texto(bloques: Sequence[ContentBlock]) -> str:
    """Une el texto de los bloques de contenido y acota el tamaño."""
    partes = [
        bloque.text if isinstance(bloque, TextContent) else f"[contenido {bloque.type} omitido]"
        for bloque in bloques
    ]
    texto = "\n".join(partes) or "(sin contenido)"
    if len(texto) > MAX_RESULTADO:
        texto = texto[:MAX_RESULTADO] + _MARCA_TRUNCADO
    return texto


class SesionMCP:
    """Envoltorio sobre un `Client` ya conectado. Se obtiene con `conectar()`."""

    def __init__(self, cliente: Client) -> None:
        self._cliente = cliente

    @property
    def descripcion_servidor(self) -> str:
        """Nombre y versión que el servidor dijo tener al conectar."""
        info = self._cliente.server_info
        if info is None:
            return "servidor desconocido"
        return f"{info.name} v{info.version}" if info.version else info.name

    async def listar_herramientas(self) -> list[Tool]:
        """Devuelve todas las herramientas del servidor, recorriendo las páginas."""
        herramientas: list[Tool] = []
        cursor: str | None = None
        while True:
            pagina = await self._cliente.list_tools(cursor=cursor)
            herramientas.extend(pagina.tools)
            if pagina.next_cursor is None:
                return herramientas
            cursor = pagina.next_cursor

    async def ejecutar(
        self, nombre: str, argumentos: dict[str, Any] | None = None
    ) -> ResultadoHerramienta:
        """Ejecuta una herramienta. Nunca lanza excepciones: los fallos se devuelven
        como resultado con `es_error=True` para que el LLM pueda reaccionar."""
        try:
            with anyio.fail_after(TIMEOUT_LLAMADA):
                resultado = await self._cliente.call_tool(nombre, argumentos or {})
        except TimeoutError:
            logger.warning("La herramienta %s superó el tiempo límite", nombre)
            return ResultadoHerramienta("La herramienta tardó demasiado en responder.", True)
        except MCPError:
            # El detalle va al log; el LLM solo recibe un mensaje genérico
            logger.exception("Error de protocolo al llamar a %s", nombre)
            return ResultadoHerramienta("Error de comunicación con la herramienta.", True)
        return ResultadoHerramienta(_extraer_texto(resultado.content), resultado.is_error)


@asynccontextmanager
async def conectar(
    destino: StdioServerParameters | MCPServer | None = None,
) -> AsyncIterator[SesionMCP]:
    """Conecta con un servidor MCP y cierra la conexión al salir del bloque.

    Args:
        destino: parámetros stdio o un servidor en memoria (para tests).
            Por defecto, lanza nuestro servidor como subproceso.
    """
    async with Client(destino or parametros_servidor_local()) as cliente:
        yield SesionMCP(cliente)


# --- Línea de comandos: para probar el servidor sin LLM ---


def _json_objeto(texto: str) -> dict[str, Any]:
    """Convierte el texto en un objeto JSON, o falla con un mensaje claro."""
    try:
        valor = json.loads(texto)
    except json.JSONDecodeError as e:
        raise argparse.ArgumentTypeError(f"JSON no válido: {e.msg}") from None
    if not isinstance(valor, dict):
        raise argparse.ArgumentTypeError('deben ser un objeto JSON, p. ej. \'{"clave": "valor"}\'')
    return valor


def _primera_linea(texto: str | None) -> str:
    lineas = (texto or "").strip().splitlines()
    return lineas[0] if lineas else "(sin descripción)"


def _firma(herramienta: Tool) -> str:
    """Resume una herramienta como `nombre(param: tipo, opcional?: tipo)`."""
    esquema = herramienta.input_schema
    obligatorios = set(esquema.get("required", []))
    parametros = [
        f"{nombre}{'' if nombre in obligatorios else '?'}: {datos.get('type', 'any')}"
        for nombre, datos in esquema.get("properties", {}).items()
    ]
    return f"{herramienta.name}({', '.join(parametros)})"


async def _ejecutar_cli(herramienta: str | None, argumentos: dict[str, Any]) -> int:
    async with conectar() as sesion:
        if herramienta is None:
            herramientas = await sesion.listar_herramientas()
            print(f"Conectado a {sesion.descripcion_servidor}")
            print(f"{len(herramientas)} herramientas disponibles:\n")
            for h in herramientas:
                print(f"  {_firma(h)}\n      {_primera_linea(h.description)}\n")
            return 0
        resultado = await sesion.ejecutar(herramienta, argumentos)
        print(resultado.texto)
        return 1 if resultado.es_error else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cliente MCP de prueba. Sin argumentos, lista las herramientas."
    )
    parser.add_argument("herramienta", nargs="?", help="nombre de la herramienta a ejecutar")
    parser.add_argument(
        "argumentos", nargs="?", type=_json_objeto, default="{}", help="argumentos en JSON"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return anyio.run(_ejecutar_cli, args.herramienta, args.argumentos)
    except Exception:
        logger.exception("No se pudo completar la operación")
        print("Error: no se pudo comunicar con el servidor MCP (detalles arriba).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
