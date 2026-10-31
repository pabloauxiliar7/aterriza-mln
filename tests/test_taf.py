"""Pruebas del TAF dividido en horas (scripts/taf.py)."""

from datetime import datetime, timezone
from pathlib import Path

from reglas import cargar_config
from taf import leer_taf, franjas

CONFIG = cargar_config(Path(__file__).resolve().parent / "config_pruebas.yaml")

# TAF real de Melilla del 31 de octubre de 2026.
TAF_REAL = ("TAF GEML 310500Z 3106/0106 VRB02KT CAVOK TX24/3115Z TN19/3108Z "
            "PROB40 TEMPO 3106/3110 2000 BR BKN008 PROB30 TEMPO 3106/3110 BKN010 "
            "BECMG 3108/3110 10010KT")


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_lectura_del_taf_real():
    t = leer_taf(TAF_REAL, ahora=utc(2026, 10, 31, 6))
    assert t["emision"] == utc(2026, 10, 31, 5)
    assert t["desde"] == utc(2026, 10, 31, 6)
    assert t["hasta"] == utc(2026, 11, 1, 6)      # cruza al mes siguiente
    tipos = [s["tipo"] for s in t["segmentos"]]
    assert tipos == ["BASE", "PROB TEMPO", "PROB TEMPO", "BECMG"]
    assert t["segmentos"][0]["grupos"] == ["VRB02KT", "CAVOK"]  # sin TX/TN


def test_franjas_del_taf_real():
    t = leer_taf(TAF_REAL, ahora=utc(2026, 10, 31, 6))
    horas = franjas(t, CONFIG, desde=utc(2026, 10, 31, 6, 20))
    assert len(horas) == 24
    assert horas[0]["inicio_utc"] == "2026-10-31T06:00Z"
    # 06–10 UTC: previsto CAVOK (verde) con dos «posibles».
    h06 = horas[0]
    assert h06["estado"] == "verde"
    assert [p["tipo"] for p in h06["posibles"]] == [
        "Temporal, probabilidad 40 %", "Temporal, probabilidad 30 %"]
    # PROB40: 2000 m y BKN008 → techo 800 ft → rojo.
    assert h06["posibles"][0]["estado"] == "rojo"
    assert "techo 800 ft" in h06["posibles"][0]["motivo"].lower()
    # PROB30: BKN010 → techo 1000 ft, en el margen → ámbar.
    assert h06["posibles"][1]["estado"] == "ambar"
    # A partir de las 10 UTC ya no hay grupos temporales.
    assert horas[4]["inicio_utc"] == "2026-10-31T10:00Z"
    assert horas[4]["posibles"] == []
    assert all(h["estado"] == "verde" for h in horas)


def test_fm_sustituye_todo():
    taf = ("TAF GEML 302300Z 3100/3124 27010KT 9999 FEW030 "
           "FM311200 09015KT 3000 BR OVC006")
    t = leer_taf(taf, ahora=utc(2026, 10, 30, 23))
    horas = franjas(t, CONFIG, desde=utc(2026, 10, 31, 0))
    assert horas[11]["estado"] == "verde"          # 11 UTC
    assert horas[12]["estado"] == "rojo"           # 12 UTC: techo 600 ft
    assert "techo 600 ft" in horas[12]["motivo"].lower()
    assert t["hasta"] == utc(2026, 11, 1, 0)       # «24» = 00 del día siguiente


def test_becmg_durante_el_cambio_toma_el_peor_caso():
    taf = "TAF GEML 310500Z 3106/0106 27010KT 9999 SCT030 BECMG 3110/3112 4000 BKN007"
    t = leer_taf(taf, ahora=utc(2026, 10, 31, 6))
    horas = franjas(t, CONFIG, desde=utc(2026, 10, 31, 6))
    por_hora = {h["inicio_utc"][11:13]: h["estado"] for h in horas}
    assert por_hora["09"] == "verde"
    assert por_hora["10"] == "rojo"   # durante el cambio: peor caso
    assert por_hora["12"] == "rojo"   # después del cambio


def test_tempo_hereda_lo_que_no_menciona():
    # El TEMPO solo cambia visibilidad y tiempo; las nubes (BKN015) siguen.
    taf = "TAF GEML 310500Z 3106/0106 27010KT 9999 BKN015 TEMPO 3106/3112 1800 RA"
    t = leer_taf(taf, ahora=utc(2026, 10, 31, 6))
    h = franjas(t, CONFIG, desde=utc(2026, 10, 31, 6))[0]
    assert h["estado"] == "verde"
    assert h["posibles"][0]["estado"] == "ambar"   # 1800 m: entre 1600 y 1919
