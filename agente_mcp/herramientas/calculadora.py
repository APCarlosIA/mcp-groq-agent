"""Evaluador aritmético seguro basado en el árbol sintáctico (AST).

No usa eval(): solo se aceptan números y los operadores + - * / con paréntesis.
"""

import ast
import logging
import math
import operator
from collections.abc import Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

logger = logging.getLogger(__name__)

LONGITUD_MAXIMA = 200  # limita el coste de analizar la expresión

Numero = int | float

_OPERADORES_BINARIOS: dict[type[ast.operator], Callable[[Numero, Numero], Numero]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

_OPERADORES_UNARIOS: dict[type[ast.unaryop], Callable[[Numero], Numero]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class ErrorCalculo(ValueError):
    """Error controlado: su mensaje es seguro de mostrar al LLM."""


def _evaluar_nodo(nodo: ast.AST) -> Numero:
    """Evalúa recursivamente un nodo del AST, rechazando todo lo no permitido."""
    match nodo:
        # type(...) in (int, float) excluye bool, que en Python es subclase de int
        case ast.Constant(value=valor) if type(valor) in (int, float):
            return valor
        case ast.BinOp(left=izq, op=op, right=der) if type(op) in _OPERADORES_BINARIOS:
            return _OPERADORES_BINARIOS[type(op)](_evaluar_nodo(izq), _evaluar_nodo(der))
        case ast.UnaryOp(op=op, operand=operando) if type(op) in _OPERADORES_UNARIOS:
            return _OPERADORES_UNARIOS[type(op)](_evaluar_nodo(operando))
        case _:
            raise ErrorCalculo("Solo se permiten números y los operadores + - * / con paréntesis.")


def evaluar(expresion: str) -> Numero:
    """Evalúa una expresión aritmética de forma segura.

    Raises:
        ErrorCalculo: si la expresión es inválida, no permitida o su resultado
            no se puede representar.
    """
    expresion = expresion.strip()
    if not expresion:
        raise ErrorCalculo("La expresión está vacía.")
    if len(expresion) > LONGITUD_MAXIMA:
        raise ErrorCalculo(f"La expresión supera los {LONGITUD_MAXIMA} caracteres.")

    try:
        resultado = _evaluar_nodo(ast.parse(expresion, mode="eval").body)
    except ErrorCalculo:
        raise
    except ZeroDivisionError:
        raise ErrorCalculo("División entre cero.") from None
    except OverflowError:
        raise ErrorCalculo("El resultado es demasiado grande.") from None
    except (SyntaxError, ValueError, RecursionError):
        raise ErrorCalculo("La expresión no es válida.") from None

    # Un float puede desbordar a inf sin lanzar excepción (p. ej. 1e308 * 10)
    if isinstance(resultado, float) and not math.isfinite(resultado):
        raise ErrorCalculo("El resultado es demasiado grande.")
    return resultado


def registrar(mcp: MCPServer) -> None:
    """Registra la herramienta `calcular` en el servidor MCP."""

    @mcp.tool()
    def calcular(expresion: str) -> str:
        """Calcula una expresión aritmética.

        Admite números, paréntesis y los operadores + - * /. No admite potencias
        ni funciones. Ejemplo: '2 * (3 + 4)' devuelve '14'.
        """
        logger.debug("calcular invocada")
        try:
            return str(evaluar(expresion))
        except ErrorCalculo as e:
            # ToolError marca la llamada como fallida (is_error=true) y el LLM
            # recibe solo nuestro mensaje controlado, sin detalles internos.
            raise ToolError(str(e)) from e
