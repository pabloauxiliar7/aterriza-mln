"""
Pruebas del viento por pista y del semáforo (scripts/reglas.py).

- Los 20 METAR reales de casos_reales.yaml, con tests/config_pruebas.yaml.
- Casos inventados con una configuración de prueba que SÍ tiene
  límites de viento (valores ficticios, solo para probar el cálculo).
"""

from pathlib import Path

import pytest
import yaml

from metar import leer_metar
from reglas import cargar_config, evaluar, viento_por_pista

CARPETA = Path(__file__).resolve().parent
CASOS = yaml.safe_load((CARPETA / "casos_reales.yaml").read_text(encoding="utf-8"))
CONFIG_CASOS = cargar_config(Path(__file__).resolve().parent / "config_pruebas.yaml")


# --- Configuración de prueba ------------------------------------------
# Límites de viento FICTICIOS (30 kt cruzado, 10 kt cola): no son
# valores reales de ningún avión; solo sirven para probar el cálculo.

CONFIG_PRUEBA_TEXTO = """
aeropuerto: {oaci: GEML, zona_horaria: Europe/Madrid, declinacion_magnetica_este: 1}
pistas: {"15": {rumbo_magnetico: 146}, "33": {rumbo_magnetico: 326}}
procedimientos:
  - {nombre: Circuito, pista: cualquiera, techo_minimo_ft: 1000, visibilidad_minima_m: 1600}
  - {nombre: Solo 33, pista: "33", techo_minimo_ft: 500, visibilidad_minima_m: 1000}
viento: {cruzado_maximo_kt: 30, cola_maximo_kt: 10}
margen_marginal_pct: 20
"""


@pytest.fixture
def config_prueba(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text(CONFIG_PRUEBA_TEXTO, encoding="utf-8")
    return cargar_config(ruta)


def semaforo(texto, config):
    return evaluar(leer_metar(texto), config)


# --- Los 20 METAR reales -----------------------------------------------

def test_hay_20_casos_reales():
    assert len(CASOS) == 20


@pytest.mark.parametrize("caso", CASOS, ids=[c["metar"][:30] for c in CASOS])
def test_caso_real(caso):
    r = semaforo(caso["metar"], CONFIG_CASOS)
    assert r["estado"] == caso["estado"], f"{caso['razon']} → motivo: {r['motivo']}"
    if "motivo_contiene" in caso:
        assert caso["motivo_contiene"] in r["motivo"].lower()
    if "causas" in caso:
        assert r["causas"] == caso["causas"]
    for pista, esperado in caso.get("viento", {}).items():
        fila = next(f for f in r["viento_por_pista"] if f["pista"] == pista)
        for clave, valor in esperado.items():
            assert fila[clave] == valor, f"pista {pista}, {clave}"


def test_config_de_pruebas_tiene_viento_informativo():
    assert CONFIG_CASOS["viento_evaluado"] is False
    assert "viento cruzado máximo" in CONFIG_CASOS["pendientes"]


# --- Cálculo de viento -------------------------------------------------

def test_viento_en_calma(config_prueba):
    filas = viento_por_pista(leer_metar("GEML 010000Z 00000KT CAVOK 20/10 Q1015")["viento"], config_prueba)
    assert all(f["cruzado"] == 0 and f["cola"] == 0 for f in filas)


def test_viento_en_el_eje_de_la_pista(config_prueba):
    # 327° geográfico = 326° magnético: de cara pura en la 33.
    filas = viento_por_pista(leer_metar("GEML 010000Z 32720KT 9999 20/10 Q1015")["viento"], config_prueba)
    p33 = next(f for f in filas if f["pista"] == "33")
    p15 = next(f for f in filas if f["pista"] == "15")
    assert (p33["cruzado"], p33["cara"], p33["cola"]) == (0, 20, 0)
    assert (p15["cruzado"], p15["cara"], p15["cola"]) == (0, 0, 20)


def test_viento_perpendicular(config_prueba):
    # 237° geográfico = 236° magnético: 90° respecto a la 15 y a la 33.
    filas = viento_por_pista(leer_metar("GEML 010000Z 23725KT 9999 20/10 Q1015")["viento"], config_prueba)
    assert all(f["cruzado"] == 25 and f["cara"] == 0 and f["cola"] == 0 for f in filas)


def test_viento_desconocido():
    assert viento_por_pista(leer_metar("GEML 010000Z AUTO /////KT 9999 Q1015")["viento"], CONFIG_CASOS) is None


# --- Semáforo con límites de viento (ficticios) -----------------------

def test_rafagas_por_encima_del_cruzado(config_prueba):
    # Media 20 kt perpendicular: cumple; ráfaga 35: supera 30 kt → rojo.
    r = semaforo("GEML 010000Z 23720G35KT 9999 FEW030 20/10 Q1015", config_prueba)
    assert r["estado"] == "rojo"
    assert r["causas"] == ["viento"]
    assert "viento cruzado 35 kt" in r["motivo"].lower()


def test_rafagas_en_margen(config_prueba):
    # Ráfaga 26 kt perpendicular: cumple (≤ 30) pero > 24 (30 − 20 %) → ámbar.
    r = semaforo("GEML 010000Z 23715G26KT 9999 FEW030 20/10 Q1015", config_prueba)
    assert r["estado"] == "ambar"


def test_se_elige_la_pista_con_viento_de_cara(config_prueba):
    # 15 kt del 120°: cola en la 33 (> 10 kt) pero de cara en la 15 → verde.
    r = semaforo("GEML 010000Z 12015KT 9999 FEW030 20/10 Q1015", config_prueba)
    assert r["estado"] == "verde"


def test_procedimiento_con_pista_fija(config_prueba):
    # Techo 700 ft: falla «Circuito» (1000 ft) pero cumple «Solo 33» (500 ft)…
    r = semaforo("GEML 010000Z 32710KT 9999 BKN007 20/10 Q1015", config_prueba)
    assert r["estado"] == "verde" and r["procedimiento"] == "Solo 33"
    # …salvo que en la 33 haya más de 10 kt de cola.
    r = semaforo("GEML 010000Z 14715KT 9999 BKN007 20/10 Q1015", config_prueba)
    assert r["estado"] == "rojo"


def test_viento_variable_se_trata_con_prudencia(config_prueba):
    # VRB 12 kt: se cuentan 12 kt de cola en todas las pistas (> 10) → rojo.
    r = semaforo("GEML 010000Z VRB12KT CAVOK 20/10 Q1015", config_prueba)
    assert r["estado"] == "rojo"


# --- Semáforo gris (faltan datos) --------------------------------------

def test_gris_si_falta_la_visibilidad():
    r = semaforo("GEML 010000Z 27005KT //// FEW030 20/10 Q1015", CONFIG_CASOS)
    assert r["estado"] == "gris"
    assert "visibilidad" in r["motivo"]


def test_rojo_aunque_falte_el_techo_si_la_visibilidad_ya_no_cumple():
    r = semaforo("GEML 010000Z AUTO 00000KT 0100 FG VV/// 12/12 Q1020", CONFIG_CASOS)
    assert r["estado"] == "rojo"


def test_gris_si_faltan_minimos_en_config(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text(CONFIG_PRUEBA_TEXTO.replace("techo_minimo_ft: 1000", "techo_minimo_ft: RELLENAR")
                    .replace("techo_minimo_ft: 500", "techo_minimo_ft: RELLENAR"), encoding="utf-8")
    r = semaforo("GEML 010000Z 27005KT CAVOK 20/10 Q1015", cargar_config(ruta))
    assert r["estado"] == "gris"
    assert "config.yaml" in r["motivo"]


def test_el_config_yaml_real_se_lee_sin_errores():
    # Comprueba solo que tu config.yaml está bien escrito, no sus valores.
    config = cargar_config()
    assert config["procedimientos"] and config["pistas"]
