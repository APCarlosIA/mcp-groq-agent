import pytest

from agente_mcp import cliente
from agente_mcp.cliente import conectar

pytestmark = pytest.mark.anyio  # todos los tests de este archivo son asíncronos


@pytest.fixture
async def test_lista_las_cuatro_herramientas(servidor):
    async with conectar(servidor) as sesion:
        nombres = {h.name for h in await sesion.listar_herramientas()}
    assert nombres == {"calcular", "hora_actual", "guardar_nota", "listar_notas"}


async def test_ejecuta_una_herramienta(servidor):
    async with conectar(servidor) as sesion:
        resultado = await sesion.ejecutar("calcular", {"expresion": "2 * (3 + 4)"})
    assert resultado.texto == "14"
    assert not resultado.es_error


async def test_error_de_herramienta_se_devuelve_como_resultado(servidor):
    async with conectar(servidor) as sesion:
        resultado = await sesion.ejecutar("calcular", {"expresion": "1 / 0"})
    assert resultado.es_error
    assert "cero" in resultado.texto


async def test_herramienta_inexistente_no_lanza_excepcion(servidor):
    async with conectar(servidor) as sesion:
        resultado = await sesion.ejecutar("no_existe", {})
    assert resultado.es_error


async def test_argumentos_invalidos_no_lanzan_excepcion(servidor):
    async with conectar(servidor) as sesion:
        resultado = await sesion.ejecutar("calcular", {})  # falta `expresion`
    assert resultado.es_error


async def test_resultados_largos_se_truncan(servidor, monkeypatch):
    monkeypatch.setattr(cliente, "MAX_RESULTADO", 10)
    async with conectar(servidor) as sesion:
        resultado = await sesion.ejecutar("hora_actual", {"zona_horaria": "UTC"})
    assert "truncado" in resultado.texto
