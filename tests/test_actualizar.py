"""Pruebas de actualizar.py (sin conexión a internet)."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from actualizar import anadir_historico, guardar_si_cambia, construir_ahora
from reglas import cargar_config

HORA = datetime(2026, 10, 31, 11, 0, tzinfo=timezone.utc)
METAR = "METAR GEML 311100Z 08005KT 350V150 9999 FEW006 SCT014 24/17 Q1019"


def test_historico_sin_duplicados(tmp_path):
    assert anadir_historico(HORA, METAR, carpeta=tmp_path) is True
    assert anadir_historico(HORA, METAR, carpeta=tmp_path) is False
    filas = list(csv.DictReader(open(tmp_path / "2026-10.csv", encoding="utf-8")))
    assert len(filas) == 1
    assert filas[0]["metar"].startswith("GEML 311100Z")   # sin «METAR» delante


def test_solo_escribe_si_cambia(tmp_path):
    ruta = tmp_path / "ahora.json"
    contenido = construir_ahora(METAR, HORA, cargar_config(Path(__file__).resolve().parent / "config_pruebas.yaml"))
    assert guardar_si_cambia(ruta, contenido) is True
    assert guardar_si_cambia(ruta, contenido) is False
    assert "generado_utc" in json.loads(ruta.read_text(encoding="utf-8"))


def test_ahora_avisa_de_viento_informativo():
    contenido = construir_ahora(METAR, HORA, cargar_config(Path(__file__).resolve().parent / "config_pruebas.yaml"))
    assert contenido["semaforo"]["estado"] == "verde"
    assert contenido["aviso_viento"]
    assert contenido["metar"]["hora_utc"] == "2026-10-31T11:00Z"
