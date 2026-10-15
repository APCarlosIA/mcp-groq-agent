from datetime import UTC, datetime

import pytest

from agente_mcp.herramientas.hora import LONGITUD_MAXIMA, ErrorHora, hora_en

# Instantes fijos para que los tests no dependan del reloj
INVIERNO = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
VERANO = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("zona", "instante", "esperado"),
    [
        ("UTC", INVIERNO, "2026-01-15T12:00:00+00:00 (UTC)"),
        ("Europe/Madrid", INVIERNO, "2026-01-15T13:00:00+01:00 (Europe/Madrid)"),
        ("Europe/Madrid", VERANO, "2026-07-15T14:00:00+02:00 (Europe/Madrid)"),
        ("Asia/Tokyo", INVIERNO, "2026-01-15T21:00:00+09:00 (Asia/Tokyo)"),
        ("  europe/madrid  ", INVIERNO, "2026-01-15T13:00:00+01:00 (Europe/Madrid)"),
    ],
)
def test_zonas_validas(zona, instante, esperado):
    assert hora_en(zona, instante) == esperado


@pytest.mark.parametrize(
    "zona",
    [
        "",
        "   ",
        "Marte/Olimpo",
        "America",  # es un directorio, no una zona
        "../etc/passwd",
        "/etc/passwd",
        "Europe/Madrid\x00",
    ],
)
def test_zonas_rechazadas(zona):
    with pytest.raises(ErrorHora):
        hora_en(zona)


def test_zona_demasiado_larga():
    with pytest.raises(ErrorHora, match="caracteres"):
        hora_en("A" * (LONGITUD_MAXIMA + 1))


def test_sin_instante_usa_la_hora_actual():
    assert hora_en("UTC").endswith("+00:00 (UTC)")
