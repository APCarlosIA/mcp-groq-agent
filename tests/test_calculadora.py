import pytest

from agente_mcp.herramientas.calculadora import LONGITUD_MAXIMA, ErrorCalculo, evaluar


@pytest.mark.parametrize(
    ("expresion", "esperado"),
    [
        ("2 + 3", 5),
        ("2 * (3 + 4)", 14),
        ("-5 + 2", -3),
        ("10 / 4", 2.5),
        ("  7  ", 7),
    ],
)
def test_expresiones_validas(expresion, esperado):
    assert evaluar(expresion) == esperado


@pytest.mark.parametrize(
    "expresion",
    [
        "",
        "   ",
        "abc",
        "1 +",
        "2 ** 3",
        "True + 1",
        "(1, 2)",
        "1j",
        "__import__('os').system('ls')",
    ],
)
def test_expresiones_rechazadas(expresion):
    with pytest.raises(ErrorCalculo):
        evaluar(expresion)


def test_division_entre_cero():
    with pytest.raises(ErrorCalculo, match="cero"):
        evaluar("1 / 0")


def test_resultado_desbordado():
    with pytest.raises(ErrorCalculo, match="grande"):
        evaluar("1e308 * 10")


def test_expresion_demasiado_larga():
    with pytest.raises(ErrorCalculo, match="caracteres"):
        evaluar("1+" * LONGITUD_MAXIMA + "1")
