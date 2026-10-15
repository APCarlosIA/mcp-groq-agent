import os
import stat

import pytest

from agente_mcp.herramientas import notas
from agente_mcp.herramientas.notas import ErrorNotas

# Los enlaces simbólicos y los permisos Unix no funcionan igual en Windows
solo_unix = pytest.mark.skipif(os.name == "nt", reason="requiere un sistema Unix")


@pytest.fixture
def directorio(tmp_path):
    """Carpeta de notas aún inexistente, dentro de un directorio temporal."""
    return tmp_path / "notas"


def test_guardar_y_leer(directorio):
    assert notas.guardar(directorio, "lista-compra", "leche y pan") == "lista-compra"
    assert notas.leer(directorio, "lista-compra") == "leche y pan"


def test_titulo_se_normaliza(directorio):
    assert notas.guardar(directorio, "  Mi-Nota  ", "hola") == "mi-nota"
    assert notas.leer(directorio, "MI-NOTA") == "hola"


@pytest.mark.parametrize(
    "titulo",
    [
        "",
        "   ",
        "../secreto",
        "a/b",
        "a\\b",
        "a.b",
        ".oculta",
        "-guion",
        "no\nta",
        "nota\x00",
        "ñandú",
        "con espacios",
        "a" * (notas.MAX_TITULO + 1),
    ],
)
def test_titulos_rechazados(directorio, titulo):
    with pytest.raises(ErrorNotas):
        notas.guardar(directorio, titulo, "contenido")
    # Se rechaza antes de tocar el disco: ni siquiera se crea la carpeta
    assert not directorio.exists()


def test_titulo_de_longitud_maxima_es_valido(directorio):
    titulo = "a" * notas.MAX_TITULO
    assert notas.guardar(directorio, titulo, "ok") == titulo


@pytest.mark.parametrize("contenido", ["", "   \n", "x" * (notas.MAX_CONTENIDO + 1)])
def test_contenidos_rechazados(directorio, contenido):
    with pytest.raises(ErrorNotas):
        notas.guardar(directorio, "titulo", contenido)


def test_no_sobrescribe(directorio):
    notas.guardar(directorio, "nota", "original")
    with pytest.raises(ErrorNotas, match="Ya existe"):
        notas.guardar(directorio, "nota", "intruso")
    assert notas.leer(directorio, "nota") == "original"


def test_limite_de_notas(directorio, monkeypatch):
    monkeypatch.setattr(notas, "MAX_NOTAS", 2)
    notas.guardar(directorio, "a", "uno")
    notas.guardar(directorio, "b", "dos")
    with pytest.raises(ErrorNotas, match="máximo"):
        notas.guardar(directorio, "c", "tres")


def test_listar_ordenado(directorio):
    notas.guardar(directorio, "b", "dos")
    notas.guardar(directorio, "a", "uno")
    assert notas._titulos(directorio) == ["a", "b"]


def test_listar_sin_carpeta(directorio):
    assert notas._titulos(directorio) == []


@solo_unix
def test_listar_ignora_enlaces_y_archivos_ajenos(directorio):
    notas.guardar(directorio, "a", "uno")
    (directorio / "otro.md").write_text("no es una nota")
    (directorio / "enlace.txt").symlink_to(directorio / "a.txt")
    assert notas._titulos(directorio) == ["a"]


def test_leer_inexistente(directorio):
    with pytest.raises(ErrorNotas, match="No existe"):
        notas.leer(directorio, "fantasma")


@solo_unix
def test_leer_rechaza_enlaces(directorio, tmp_path):
    secreto = tmp_path / "secreto.txt"
    secreto.write_text("clave")
    directorio.mkdir()
    (directorio / "robo.txt").symlink_to(secreto)
    with pytest.raises(ErrorNotas, match="No existe"):
        notas.leer(directorio, "robo")


@solo_unix
def test_permisos_solo_para_el_dueno(directorio):
    notas.guardar(directorio, "privada", "texto")
    modo = stat.S_IMODE((directorio / "privada.txt").stat().st_mode)
    assert modo == 0o600


def test_leer_archivo_corrupto(directorio):
    directorio.mkdir()
    (directorio / "rota.txt").write_bytes(b"\xff\xfe\xfa")  # no es UTF-8 válido
    with pytest.raises(ErrorNotas, match="leer"):
        notas.leer(directorio, "rota")