"""
Genera los iconos de la aplicación (web/iconos/) sin programas externos.

Diseño propio y neutro: fondo azul oscuro, una pista vista desde arriba
y un punto verde. Sin logotipos de ninguna organización.

Uso:  python scripts/generar_iconos.py
"""

import math
import struct
import zlib

from reglas import RAIZ

FONDO = (13, 54, 107)
PISTA = (240, 239, 236)
MARCAS = (13, 54, 107)
VERDE = (47, 191, 47)


def color_en(x, y):
    """Color del píxel (x, y) en un lienzo de 0 a 1."""
    # Pista: rectángulo vertical inclinado ligeramente (como la 15/33)
    cx, cy = x - 0.5, y - 0.5
    # giro de 34° hacia la izquierda: pista noroeste–sureste (146°/326°)
    a = math.radians(-34)
    u = cx * math.cos(a) + cy * math.sin(a)
    v = -cx * math.sin(a) + cy * math.cos(a)
    if abs(u) < 0.085 and abs(v) < 0.36:
        # Línea central discontinua
        if abs(u) < 0.012 and (int((v + 0.36) * 14) % 2 == 0) and abs(v) < 0.28:
            return MARCAS
        return PISTA
    # Punto verde (semáforo) en la esquina superior derecha
    if (x - 0.76) ** 2 + (y - 0.24) ** 2 < 0.085 ** 2:
        return VERDE
    return FONDO


def png(tamano, ruta):
    filas = []
    for j in range(tamano):
        fila = bytearray([0])  # filtro «ninguno»
        for i in range(tamano):
            # Suavizado: media de 4 muestras por píxel
            muestras = [color_en((i + dx) / tamano, (j + dy) / tamano) for dx in (0.25, 0.75) for dy in (0.25, 0.75)]
            fila += bytes(round(sum(c[k] for c in muestras) / 4) for k in range(3))
        filas.append(bytes(fila))
    datos = zlib.compress(b"".join(filas), 9)

    def bloque(tipo, contenido):
        return (struct.pack(">I", len(contenido)) + tipo + contenido
                + struct.pack(">I", zlib.crc32(tipo + contenido) & 0xFFFFFFFF))

    with open(ruta, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(bloque(b"IHDR", struct.pack(">IIBBBBB", tamano, tamano, 8, 2, 0, 0, 0)))
        f.write(bloque(b"IDAT", datos))
        f.write(bloque(b"IEND", b""))


if __name__ == "__main__":
    carpeta = RAIZ / "web" / "iconos"
    carpeta.mkdir(parents=True, exist_ok=True)
    for t in (180, 192, 512):
        png(t, carpeta / f"icono-{t}.png")
        print(f"Creado web/iconos/icono-{t}.png")
