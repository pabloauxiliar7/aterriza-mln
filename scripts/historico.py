"""
Estadísticas del histórico → data/estadisticas.json

Lee los 10 años descargados (data/bruto/) y los METAR añadidos después
(data/historico/), toma un parte por hora (el más cercano a la hora en
punto), le aplica las reglas de config.yaml y guarda, hora a hora, lo
que la web necesita para el mapa de calor y los comparadores.

Formato compacto (listas paralelas, una posición por hora):
  m: mes local (1–12)          h: hora local (0–23)
  e: estado  0 verde · 1 ámbar · 2 rojo · 3 gris (sin datos)
  c: causas de rojo, sumadas: 1 techo · 2 visibilidad · 4 viento
  t: techo en centenares de pies (-1 = sin techo, -2 = desconocido)
  x: viento cruzado máximo con ráfaga, en kt (-1 = desconocido)

Uso:  python scripts/historico.py
"""

import csv
import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from metar import leer_metar
from reglas import cargar_config, evaluar, RAIZ
from actualizar import resumen_reglas

DATOS = RAIZ / "data"
ESTADOS = {"verde": 0, "ambar": 1, "rojo": 2, "gris": 3}
CAUSAS = {"techo": 1, "visibilidad": 2, "viento": 4}


def leer_observaciones():
    """Junta el archivo de 10 años y los CSV mensuales, sin duplicados."""
    vistos = set()
    fuentes = [DATOS / "bruto" / "geml_10_anos.csv.gz"] + sorted((DATOS / "historico").glob("*.csv"))
    for ruta in fuentes:
        if not ruta.exists():
            continue
        abrir = gzip.open if ruta.suffix == ".gz" else open
        with abrir(ruta, "rt", encoding="utf-8", newline="") as f:
            for fila in csv.DictReader(f):
                clave = (fila["valido_utc"], fila["metar"])
                if clave not in vistos:
                    vistos.add(clave)
                    yield fila["valido_utc"], fila["metar"]


def un_parte_por_hora(observaciones):
    """
    Para cada hora, el parte más cercano a la hora en punto
    (como mucho 30 minutos antes o después).
    """
    elegidos = {}
    for valido, texto in observaciones:
        momento = datetime.strptime(valido, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        hora = (momento + timedelta(minutes=30)).replace(minute=0)
        if momento.minute == 30:
            hora = momento.replace(minute=0)  # en empate, se asigna a la hora anterior
        distancia = abs((momento - hora).total_seconds())
        if hora not in elegidos or distancia < elegidos[hora][0]:
            elegidos[hora] = (distancia, texto)
    return {hora: texto for hora, (_, texto) in sorted(elegidos.items())}


def calcular(config):
    zona = ZoneInfo(config["zona_horaria"])
    horas = un_parte_por_hora(leer_observaciones())
    columnas = {k: [] for k in "mhectx"}
    for hora_utc, texto in horas.items():
        local = hora_utc.astimezone(zona)
        r = evaluar(leer_metar(texto), config)
        if not r["techo_conocido"]:
            t = -2
        elif r["techo_ft"] is None:
            t = -1
        else:
            t = r["techo_ft"] // 100
        pistas = r["viento_por_pista"]
        x = min(p["cruzado_max"] for p in pistas) if pistas else -1
        columnas["m"].append(local.month)
        columnas["h"].append(local.hour)
        columnas["e"].append(ESTADOS[r["estado"]])
        columnas["c"].append(sum(CAUSAS[c] for c in r["causas"]))
        columnas["t"].append(t)
        columnas["x"].append(x)

    primera, ultima = min(horas), max(horas)
    validas = sum(1 for e in columnas["e"] if e != 3)
    return {
        "oaci": config["oaci"],
        "desde_utc": primera.strftime("%Y-%m-%dT%H:%MZ"),
        "hasta_utc": ultima.strftime("%Y-%m-%dT%H:%MZ"),
        "horas_totales": len(horas),
        "horas_con_datos": validas,
        "anos": round(validas / 8766, 2),  # 8766 h = un año medio
        "reglas": resumen_reglas(config),
        "datos": columnas,
    }


def main():
    config = cargar_config()
    estadisticas = calcular(config)
    ruta = DATOS / "estadisticas.json"
    nuevo = json.dumps(estadisticas, ensure_ascii=False, separators=(",", ":"))
    if ruta.exists() and ruta.read_text(encoding="utf-8") == nuevo:
        print("Estadísticas sin cambios.")
        return 0
    ruta.write_text(nuevo, encoding="utf-8")
    e = estadisticas["datos"]["e"]
    rojo = sum(1 for v in e if v == 2)
    print(f"{estadisticas['horas_totales']} horas ({estadisticas['desde_utc']} → {estadisticas['hasta_utc']}), "
          f"{estadisticas['horas_con_datos']} con datos; en rojo: {rojo} "
          f"({100 * rojo / estadisticas['horas_con_datos']:.1f} %). "
          f"Tamaño: {len(nuevo) // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
