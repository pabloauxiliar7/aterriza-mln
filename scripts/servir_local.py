"""
Prepara la web y la muestra en tu ordenador.

Junta web/ y data/ en la carpeta _site/ (lo mismo que se publicará en
GitHub Pages) y arranca un pequeño servidor en http://localhost:8000

Uso:  python scripts/servir_local.py          (Ctrl+C para pararlo)
      python scripts/servir_local.py --solo-preparar
"""

import functools
import http.server
import shutil
import sys

from reglas import RAIZ

SITIO = RAIZ / "_site"


def preparar():
    """Copia web/ y los JSON de data/ en _site/."""
    if SITIO.exists():
        shutil.rmtree(SITIO)
    shutil.copytree(RAIZ / "web", SITIO)
    (SITIO / "data").mkdir()
    for nombre in ("ahora.json", "24h.json", "estadisticas.json"):
        origen = RAIZ / "data" / nombre
        if origen.exists():
            shutil.copy2(origen, SITIO / "data" / nombre)
    print(f"Sitio preparado en {SITIO.relative_to(RAIZ)}/")


if __name__ == "__main__":
    preparar()
    if "--solo-preparar" in sys.argv:
        sys.exit(0)
    puerto = 8000
    manejador = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITIO))
    print(f"Abre http://localhost:{puerto} en el navegador (Ctrl+C para parar).")
    http.server.ThreadingHTTPServer(("127.0.0.1", puerto), manejador).serve_forever()
