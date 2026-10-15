"""Servidor MCP: registra las herramientas y arranca el transporte stdio."""

import logging
import sys

from mcp.server.mcpserver import MCPServer

from agente_mcp.herramientas import calculadora, hora

logger = logging.getLogger(__name__)


def crear_servidor() -> MCPServer:
    """Construye el servidor y registra todas las herramientas."""
    # El nombre va posicional y el resto por keyword (el orden de parámetros
    # cambió en v2). Sin `version`, el servidor se anunciaría con versión vacía.
    mcp = MCPServer("herramientas-demo", version="0.1.0")
    calculadora.registrar(mcp)
    hora.registrar(mcp)
    return mcp


def main() -> None:
    # IMPORTANTE: con stdio, stdout es el canal del protocolo. Un solo print()
    # lo corrompería, así que todos los logs van a stderr.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Iniciando servidor MCP")
    crear_servidor().run()


if __name__ == "__main__":
    main()