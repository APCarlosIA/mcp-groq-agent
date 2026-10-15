"""Herramientas de notas: guardar y consultar notas de texto en una carpeta local.

Medidas de seguridad:
- El título solo admite [a-z0-9_-]: no puede contener rutas, puntos ni barras.
- Las notas nunca se sobrescriben (creación exclusiva).
- Límites de tamaño y de cantidad para no llenar el disco.
- Los detalles técnicos de los fallos van al log, nunca al LLM.
"""

import logging
import os
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

logger = logging.getLogger(__name__)

MAX_TITULO = 50
MAX_CONTENIDO = 2_000
MAX_NOTAS = 100
EXTENSION = ".txt"

# Debe empezar por letra o número; después, letras minúsculas, números, - o _
_PATRON_TITULO = re.compile(r"[a-z0-9][a-z0-9_-]*")


class ErrorNotas(ValueError):
    """Error controlado: su mensaje es seguro de mostrar al LLM."""


def directorio_por_defecto() -> Path:
    """Devuelve la variable NOTAS_DIR si existe o `notas/` en la raíz del proyecto."""
    configurado = os.environ.get("NOTAS_DIR")
    if configurado:
        return Path(configurado)
    # este archivo está en <raíz>/agente_mcp/herramientas/notas.py
    return Path(__file__).resolve().parents[2] / "notas"


def _normalizar_titulo(titulo: str) -> str:
    """Valida el título (lista blanca) y lo devuelve en minúsculas y sin espacios."""
    titulo = titulo.strip().lower()
    # fullmatch exige que coincida TODO el texto. Con `$` en lugar de fullmatch,
    # un salto de línea final ("nota\n") se colaría.
    if len(titulo) > MAX_TITULO or not _PATRON_TITULO.fullmatch(titulo):
        raise ErrorNotas(
            f"Título no válido. Usa de 1 a {MAX_TITULO} caracteres: letras "
            "minúsculas sin tildes, números, guiones y guiones bajos "
            "(ejemplo: 'lista-compra')."
        )
    return titulo


def _ruta(directorio: Path, titulo: str) -> Path:
    """Ruta del archivo de una nota. El título ya debe estar validado."""
    return directorio / f"{titulo}{EXTENSION}"


def _titulos(directorio: Path) -> list[str]:
    """Títulos de las notas existentes, ordenados. Ignora enlaces y archivos ajenos."""
    if not directorio.is_dir():
        return []
    return sorted(
        ruta.stem
        for ruta in directorio.glob(f"*{EXTENSION}")
        if ruta.is_file() and not ruta.is_symlink()
    )


def _crear_nueva(ruta: Path, contenido: str) -> None:
    """Crea el archivo solo si no existe. Permisos 600: solo lo lee su dueño."""
    try:
        # O_EXCL: falla si la ruta existe (incluso si es un enlace simbólico).
        # Comprobar y crear en un solo paso evita condiciones de carrera.
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ErrorNotas("Ya existe una nota con ese título.") from None
    with os.fdopen(fd, "w", encoding="utf-8") as archivo:
        archivo.write(contenido)


def guardar(directorio: Path, titulo: str, contenido: str) -> str:
    """Guarda una nota nueva y devuelve el título normalizado con el que se guardó.

    Raises:
        ErrorNotas: si el título o el contenido no son válidos, la nota ya existe,
            se alcanzó el límite de notas o falla la escritura.
    """
    # Se valida todo ANTES de tocar el disco
    titulo = _normalizar_titulo(titulo)
    if not contenido.strip():
        raise ErrorNotas("El contenido está vacío.")
    if len(contenido) > MAX_CONTENIDO:
        raise ErrorNotas(f"El contenido supera los {MAX_CONTENIDO} caracteres.")

    try:
        directorio.mkdir(parents=True, exist_ok=True, mode=0o700)
        if len(_titulos(directorio)) >= MAX_NOTAS:
            raise ErrorNotas(f"Se alcanzó el máximo de {MAX_NOTAS} notas.")
        _crear_nueva(_ruta(directorio, titulo), contenido)
    except ErrorNotas:
        raise
    except OSError:
        # El detalle (con rutas) queda en el log; el LLM solo ve un mensaje genérico
        logger.exception("No se pudo guardar la nota")
        raise ErrorNotas("No se pudo guardar la nota.") from None
    return titulo


def leer(directorio: Path, titulo: str) -> str:
    """Devuelve el contenido de una nota.

    Raises:
        ErrorNotas: si el título no es válido, la nota no existe o no se puede leer.
    """
    ruta = _ruta(directorio, _normalizar_titulo(titulo))
    if ruta.is_symlink() or not ruta.is_file():
        raise ErrorNotas("No existe ninguna nota con ese título.")
    try:
        return ruta.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.exception("No se pudo leer la nota")
        raise ErrorNotas("No se pudo leer la nota.") from None


def registrar(mcp: MCPServer, directorio: Path | None = None) -> None:
    """Registra `guardar_nota` y `listar_notas` en el servidor MCP.

    Args:
        mcp: el servidor donde se registran.
        directorio: carpeta de notas. Por defecto, `directorio_por_defecto()`.
    """
    carpeta = directorio or directorio_por_defecto()

    @mcp.tool()
    def guardar_nota(titulo: str, contenido: str) -> str:
        """Guarda una nota de texto nueva.

        El título admite solo letras minúsculas sin tildes, números, guiones y
        guiones bajos (máximo 50 caracteres), por ejemplo 'lista-compra'.
        El contenido tiene un máximo de 2000 caracteres. No sobrescribe notas
        existentes: si el título ya existe, devuelve un error.
        """
        logger.debug("guardar_nota invocada")
        try:
            return f"Nota '{guardar(carpeta, titulo, contenido)}' guardada."
        except ErrorNotas as e:
            raise ToolError(str(e)) from e

    @mcp.tool()
    def listar_notas(titulo: str = "") -> str:
        """Lista las notas guardadas o lee el contenido de una.

        Sin argumentos, devuelve los títulos de todas las notas. Si se indica
        `titulo`, devuelve el contenido de esa nota.
        """
        logger.debug("listar_notas invocada")
        try:
            if titulo.strip():
                return leer(carpeta, titulo)
            titulos = _titulos(carpeta)
            if not titulos:
                return "No hay notas guardadas."
            return "\n".join(f"- {t}" for t in titulos)
        except ErrorNotas as e:
            raise ToolError(str(e)) from e
