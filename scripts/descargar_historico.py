"""
Descarga (UNA sola vez) los últimos 10 años de METAR de Melilla del
archivo del Iowa Environmental Mesonet y los guarda comprimidos en
data/bruto/geml_10_anos.csv.gz

Pide los datos año a año para no saturar su servidor.

Uso:  python scripts/descargar_historico.py
"""

import csv
import gzip
import io
import sys
import time
import urllib.request
from datetime import date, timedelta

from reglas import RAIZ, cargar_config

DESTINO = RAIZ / "data" / "bruto" / "geml_10_anos.csv.gz"
URL = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station={oaci}"
       "&data=metar&tz=Etc/UTC&format=onlycomma&latlon=no&missing=empty&trace=empty"
       "&report_type=3&report_type=4"   # 3 = METAR ordinario, 4 = especial
       "&year1={a.year}&month1={a.month}&day1={a.day}"
       "&year2={b.year}&month2={b.month}&day2={b.day}")


def descargar(url, intentos=3):
    for n in range(intentos):
        try:
            peticion = urllib.request.Request(url, headers={"User-Agent": "AterrizaMLN/1.0"})
            with urllib.request.urlopen(peticion, timeout=300) as r:
                return r.read().decode("utf-8")
        except Exception as error:  # noqa: BLE001
            print(f"  fallo ({error}); reintentando…")
            time.sleep(10 * (n + 1))
    raise RuntimeError(f"No se pudo descargar {url}")


def main():
    oaci = cargar_config()["oaci"]
    fin = date.today()
    inicio = fin.replace(year=fin.year - 10)
    filas = []
    tramo = inicio
    while tramo < fin:
        siguiente = min(tramo.replace(year=tramo.year + 1), fin)
        print(f"Descargando {tramo} → {siguiente}…")
        texto = descargar(URL.format(oaci=oaci, a=tramo, b=siguiente))
        for fila in csv.DictReader(io.StringIO(texto)):
            if fila.get("metar"):
                filas.append((fila["valid"], " ".join(fila["metar"].split())))
        tramo = siguiente
        time.sleep(2)  # cortesía con el servidor

    filas = sorted(set(filas))
    if not filas:
        print("Error: no se ha descargado ningún METAR.")
        return 1
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(DESTINO, "wt", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["valido_utc", "metar"])
        escritor.writerows(filas)
    print(f"Guardados {len(filas)} METAR ({filas[0][0]} → {filas[-1][0]}) en {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
