"""
Actualización periódica (cada 30 minutos, desde GitHub Actions).

1. Descarga el METAR y el TAF de Melilla de aviationweather.gov.
2. Aplica las reglas de config.yaml.
3. Escribe data/ahora.json y data/24h.json.
4. Añade el METAR nuevo a data/historico/AAAA-MM.csv (sin duplicados).

Solo reescribe un archivo si su contenido cambia de verdad; así la
tarea programada no guarda nada cuando no hay datos nuevos.

Uso:  python scripts/actualizar.py
"""

import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from metar import leer_metar, describir_metar
from reglas import cargar_config, evaluar, RAIZ
from taf import leer_taf, franjas

DATOS = RAIZ / "data"
URL = "https://aviationweather.gov/api/data/{tipo}?ids={oaci}&format=json"
AGENTE = "AterrizaMLN/1.0 (proyecto sin ánimo de lucro; github.com)"


# ---------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------

def descargar_json(url, intentos=3):
    """Descarga un JSON; reintenta si falla (la red a veces falla)."""
    ultimo_error = None
    for n in range(intentos):
        try:
            peticion = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(peticion, timeout=30) as r:
                contenido = r.read().decode("utf-8")
            return json.loads(contenido) if contenido.strip() else []
        except Exception as error:  # noqa: BLE001 (cualquier fallo de red)
            ultimo_error = error
            time.sleep(5 * (n + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {ultimo_error}")


# ---------------------------------------------------------------------
# Construcción de los archivos
# ---------------------------------------------------------------------

def resumen_reglas(config):
    """Mínimos aplicados, para la pantalla «Ajustes»."""
    return {
        "procedimientos": [
            {"nombre": p["nombre"], "pista": p["pista"],
             "techo_minimo_ft": p["techo_min"], "visibilidad_minima_m": p["vis_min"]}
            for p in config["procedimientos"]],
        "pistas": config["pistas"],
        "declinacion_magnetica_este": config["declinacion"],
        "cruzado_maximo_kt": config["cruzado_max"],
        "cola_maximo_kt": config["cola_max"],
        "margen_marginal_pct": round(config["margen"] * 100),
        "viento_evaluado": config["viento_evaluado"],
        "pendientes": config["pendientes"],
        "zona_horaria": config["zona_horaria"],
    }


def construir_ahora(texto_metar, hora_obs, config):
    """Contenido de data/ahora.json a partir del METAR."""
    datos = leer_metar(texto_metar)
    r = evaluar(datos, config)
    aviso_viento = None
    if not config["viento_evaluado"]:
        aviso_viento = ("El viento no se tiene en cuenta en este resultado: "
                        "faltan sus límites en config.yaml.")
    return {
        "oaci": config["oaci"],
        "metar": {
            "texto": datos["texto"],
            "hora_utc": hora_obs.strftime("%Y-%m-%dT%H:%MZ"),
            "descifrado": describir_metar(datos),
        },
        "semaforo": {k: r[k] for k in ("estado", "texto", "motivo", "procedimiento", "causas")},
        "techo_ft": r["techo_ft"],
        "techo_conocido": r["techo_conocido"],
        "visibilidad_m": r["visibilidad_m"],
        "viento_por_pista": r["viento_por_pista"],
        "viento_evaluado": r["viento_evaluado"],
        "aviso_viento": aviso_viento,
        "procedimientos": r["procedimientos"],
        "reglas": resumen_reglas(config),
    }


def construir_24h(texto_taf, config, ahora):
    """Contenido de data/24h.json a partir del TAF."""
    taf = leer_taf(texto_taf, ahora=ahora)
    return {
        "oaci": config["oaci"],
        "taf": {
            "texto": taf["texto"],
            "emision_utc": taf["emision"].strftime("%Y-%m-%dT%H:%MZ"),
            "desde_utc": taf["desde"].strftime("%Y-%m-%dT%H:%MZ"),
            "hasta_utc": taf["hasta"].strftime("%Y-%m-%dT%H:%MZ"),
        },
        # Las 24 horas empiezan ahora o, si el TAF aún no ha empezado, en su inicio.
        "horas": franjas(taf, config, desde=max(ahora, taf["desde"])),
    }


def guardar_si_cambia(ruta, contenido):
    """
    Escribe el JSON solo si el contenido es distinto del que ya había
    (sin contar la hora de generación). Devuelve True si lo ha escrito.
    """
    if ruta.exists():
        try:
            anterior = json.loads(ruta.read_text(encoding="utf-8"))
            anterior.pop("generado_utc", None)
            if anterior == contenido:
                return False
        except json.JSONDecodeError:
            pass
    final = {"generado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), **contenido}
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(final, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


def anadir_historico(hora_obs, texto_metar, carpeta=DATOS / "historico"):
    """
    Añade el METAR a data/historico/AAAA-MM.csv si no estaba ya.
    Devuelve True si lo ha añadido.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{hora_obs:%Y-%m}.csv"
    valido = hora_obs.strftime("%Y-%m-%d %H:%M")
    # Mismo formato que el archivo de Iowa: sin la palabra METAR/SPECI delante.
    grupos = texto_metar.split()
    if grupos and grupos[0] in ("METAR", "SPECI"):
        grupos = grupos[1:]
    texto = " ".join(grupos)
    if ruta.exists():
        with open(ruta, encoding="utf-8", newline="") as f:
            for fila in csv.DictReader(f):
                if fila["valido_utc"] == valido and fila["metar"] == texto:
                    return False
    nuevo = not ruta.exists()
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        if nuevo:
            escritor.writerow(["valido_utc", "metar"])
        escritor.writerow([valido, texto])
    return True


# ---------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------

def main():
    config = cargar_config()
    ahora = datetime.now(timezone.utc)
    cambios = []

    # METAR (imprescindible: si falla, la tarea termina con error).
    metares = descargar_json(URL.format(tipo="metar", oaci=config["oaci"]))
    if not metares:
        print("Error: aviationweather.gov no ha devuelto ningún METAR.")
        return 1
    m = metares[0]
    hora_obs = datetime.fromtimestamp(m["obsTime"], tz=timezone.utc)
    if guardar_si_cambia(DATOS / "ahora.json", construir_ahora(m["rawOb"], hora_obs, config)):
        cambios.append("ahora.json")
    if anadir_historico(hora_obs, m["rawOb"]):
        cambios.append(f"historico/{hora_obs:%Y-%m}.csv")

    # TAF (si falla, se conserva el anterior y se avisa).
    try:
        tafs = descargar_json(URL.format(tipo="taf", oaci=config["oaci"]))
        if tafs:
            if guardar_si_cambia(DATOS / "24h.json", construir_24h(tafs[0]["rawTAF"], config, ahora)):
                cambios.append("24h.json")
        else:
            print("Aviso: no hay TAF en vigor ahora mismo.")
    except Exception as error:  # noqa: BLE001
        print(f"Aviso: no se pudo actualizar el TAF ({error}). Se conserva el anterior.")

    print(f"METAR {hora_obs:%d/%m %H:%M} UTC: {m['rawOb']}")
    print("Archivos actualizados: " + (", ".join(cambios) if cambios else "ninguno (sin datos nuevos)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
