import copy
import json
from types import SimpleNamespace

import groq
import httpx
import pytest

from agente_mcp import agente as modulo_agente
from agente_mcp.agente import (
    MAX_ITERACIONES,
    MAX_LLAMADAS_POR_TURNO,
    MAX_PREGUNTA,
    Agente,
    ErrorAgente,
)
from agente_mcp.cliente import conectar

pytestmark = pytest.mark.anyio


def _llamada(id_llamada, nombre, argumentos):
    texto = argumentos if isinstance(argumentos, str) else json.dumps(argumentos)
    return SimpleNamespace(id=id_llamada, function=SimpleNamespace(name=nombre, arguments=texto))


def _respuesta(contenido=None, llamadas=None):
    mensaje = SimpleNamespace(content=contenido, tool_calls=llamadas)
    return SimpleNamespace(choices=[SimpleNamespace(message=mensaje, finish_reason="stop")])


def _respuesta_http(codigo, cabeceras=None):
    peticion = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return httpx.Response(codigo, headers=cabeceras, request=peticion)


class LLMFalso:
    """Imita a AsyncGroq: entrega respuestas preparadas y guarda las peticiones.

    Si una respuesta preparada es una excepción, se lanza en vez de devolverse.
    """

    def __init__(self, *respuestas):
        self._pendientes = list(respuestas)
        self.peticiones = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._crear))

    async def _crear(self, **kwargs):
        self.peticiones.append(copy.deepcopy(kwargs))  # copia: el historial sigue cambiando
        siguiente = self._pendientes.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


def _mensajes_tool(peticion):
    return [m for m in peticion["messages"] if m["role"] == "tool"]


async def test_responde_sin_herramientas(servidor):
    llm = LLMFalso(_respuesta("Hola"))
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "modelo-falso")
        assert await agente.preguntar("hola") == "Hola"
    peticion = llm.peticiones[0]
    assert len(peticion["tools"]) == 4
    assert peticion["messages"][0]["role"] == "system"
    assert peticion["model"] == "modelo-falso"


async def test_usa_una_herramienta_y_responde(servidor):
    llm = LLMFalso(
        _respuesta(llamadas=[_llamada("c1", "calcular", {"expresion": "2 * (3 + 4)"})]),
        _respuesta("El resultado es 14"),
    )
    avisos = []
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m", al_llamar=lambda n, a: avisos.append((n, a)))
        assert await agente.preguntar("¿cuánto es 2 * (3 + 4)?") == "El resultado es 14"
    (resultado,) = _mensajes_tool(llm.peticiones[1])
    assert resultado["tool_call_id"] == "c1"
    assert resultado["content"] == "14"
    assert avisos == [("calcular", {"expresion": "2 * (3 + 4)"})]


async def test_herramienta_inexistente_se_devuelve_como_error_al_modelo(servidor):
    llm = LLMFalso(
        _respuesta(llamadas=[_llamada("c1", "borrar_todo", {})]),
        _respuesta("No puedo hacer eso"),
    )
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m")
        assert await agente.preguntar("borra todo") == "No puedo hacer eso"
    (resultado,) = _mensajes_tool(llm.peticiones[1])
    assert json.loads(resultado["content"])["is_error"] is True


@pytest.mark.parametrize("argumentos", ["{roto", "[1, 2]"])
async def test_argumentos_invalidos_se_devuelven_como_error_al_modelo(servidor, argumentos):
    llm = LLMFalso(
        _respuesta(llamadas=[_llamada("c1", "calcular", argumentos)]),
        _respuesta("Disculpa"),
    )
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m")
        await agente.preguntar("calcula algo")
    (resultado,) = _mensajes_tool(llm.peticiones[1])
    assert json.loads(resultado["content"])["is_error"] is True


async def test_limite_de_llamadas_por_turno_responde_a_todas(servidor):
    total = MAX_LLAMADAS_POR_TURNO + 1
    llamadas = [_llamada(f"c{i}", "calcular", {"expresion": "1 + 1"}) for i in range(total)]
    llm = LLMFalso(_respuesta(llamadas=llamadas), _respuesta("Hecho"))
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m")
        await agente.preguntar("calcula muchas cosas")
    resultados = _mensajes_tool(llm.peticiones[1])
    assert len(resultados) == total  # ninguna llamada se queda sin respuesta
    assert [r["content"] for r in resultados[:-1]] == ["2"] * MAX_LLAMADAS_POR_TURNO
    assert json.loads(resultados[-1]["content"])["is_error"] is True


async def test_limite_de_iteraciones(servidor):
    respuestas = [
        _respuesta(llamadas=[_llamada(f"c{i}", "calcular", {"expresion": "1 + 1"})])
        for i in range(MAX_ITERACIONES)
    ]
    llm = LLMFalso(*respuestas)
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m")
        respuesta = await agente.preguntar("sin fin")
    assert "No pude completar" in respuesta
    assert len(llm.peticiones) == MAX_ITERACIONES


@pytest.mark.parametrize("pregunta", ["", "   ", "x" * (MAX_PREGUNTA + 1)])
async def test_preguntas_no_validas_no_llegan_al_llm(servidor, pregunta):
    llm = LLMFalso()
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m")
        with pytest.raises(ErrorAgente):
            await agente.preguntar(pregunta)
    assert llm.peticiones == []


async def test_historial_se_recorta_por_turnos_completos(servidor, monkeypatch):
    monkeypatch.setattr(modulo_agente, "MAX_MENSAJES", 6)
    llm = LLMFalso(*[_respuesta(f"r{i}") for i in range(5)])
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m")
        for i in range(5):
            await agente.preguntar(f"p{i}")
    historial = agente.historial
    assert len(historial) <= 6
    assert historial[0]["role"] == "system"
    assert historial[1]["role"] == "user"  # nunca empieza a mitad de un turno
    assert historial[-1]["content"] == "r4"


async def test_un_turno_fallido_no_deja_el_historial_a_medias(servidor):
    llm = LLMFalso(RuntimeError("fallo inesperado"))
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m")
        with pytest.raises(RuntimeError):
            await agente.preguntar("hola")
    assert [m["role"] for m in agente.historial] == ["system"]


async def test_limite_de_uso_de_groq_da_un_mensaje_claro(servidor):
    error = groq.RateLimitError(
        "límite", response=_respuesta_http(429, {"retry-after": "7"}), body=None
    )
    llm = LLMFalso(error)
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m")
        with pytest.raises(ErrorAgente, match="7 segundos"):
            await agente.preguntar("hola")


async def test_llamada_invalida_se_reintenta_con_temperatura_cero(servidor):
    error = groq.BadRequestError("llamada inválida", response=_respuesta_http(400), body=None)
    llm = LLMFalso(error, _respuesta("Listo"))
    async with conectar(servidor) as sesion:
        agente = Agente(sesion, llm, "m")
        assert await agente.preguntar("hola") == "Listo"
    assert [p["temperature"] for p in llm.peticiones] == [modulo_agente.TEMPERATURA, 0.0]