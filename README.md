# Aterriza MLN

Web instalable que compara cada 30 minutos la meteorología del aeropuerto de
Melilla (OACI GEML) con los mínimos de sus aproximaciones y muestra, con diez
años de histórico, la probabilidad de operar por mes y franja horaria.

> Información orientativa elaborada con datos meteorológicos públicos. No es
> información aeronáutica oficial ni anticipa las decisiones de las aerolíneas.
> Consulte siempre con su compañía.

Sin servidor, sin base de datos, sin cookies ni analítica. Coste: 0 €.

## Cómo funciona

```
aviationweather.gov ──► scripts/actualizar.py ──► data/ahora.json, data/24h.json
 (METAR y TAF)            (cada 30 min,            data/historico/AAAA-MM.csv
                           GitHub Actions)
Iowa Mesonet ──► data/bruto/ ──► scripts/historico.py ──► estadisticas.json
 (10 años)                        (en cada publicación)
                                        │
                     web/ + data/ ──► GitHub Pages (la web)
```

| Carpeta / archivo | Qué es |
|---|---|
| `config.yaml` | **Tus reglas**: mínimos, pistas, viento y margen. |
| `scripts/` | Programas en Python que descargan y calculan. |
| `data/` | Datos generados. `historico/` crece con cada METAR nuevo. |
| `web/` | La web (HTML, CSS y JavaScript sin librerías). |
| `tests/` | Pruebas automáticas (63). |
| `.github/workflows/actualizar.yml` | La tarea programada. |

Semáforo: **rojo** si no se cumple ningún procedimiento; **ámbar** si el mejor
se cumple pero está dentro del margen; **verde** en otro caso; **gris** si faltan
datos. Techo = capa BKN, OVC o VV más baja.

---

## Guía rápida

### 1. Cambiar los mínimos

1. En GitHub, abre `config.yaml` y pulsa el lápiz (✏️ «Edit this file»).
2. Cambia el número que quieras. Si no conoces un valor, escribe `RELLENAR`.
3. Pulsa **Commit changes…** y luego otra vez **Commit changes**.
4. En 2–3 minutos la tarea se ejecuta sola, recalcula el histórico y publica.

Revisa los valores en cada ciclo AIRAC (cada 28 días) en el
[AIP de Melilla](https://aip.enaire.es/AIP/#GEML). Para que el viento cuente en
el semáforo, rellena `cruzado_maximo_kt` y `cola_maximo_kt`.

### 2. Comprobar que la tarea programada funciona

- Pestaña **Actions** del repositorio → «Actualizar y publicar».
  Cada ejecución con ✅ verde ha ido bien; ❌ rojo, ha fallado.
- En la web, pantalla **Ahora**: la hora del parte no debe tener más de una hora
  o poco más. Si sale «Dato desactualizado», algo falla.
- GitHub no es puntual: es normal que se retrase 5–20 minutos.

### 3. Qué hacer si falla

1. Abre la ejecución con ❌ y pulsa el paso en rojo para leer el mensaje.
2. Casos habituales:
   - **«config.yaml…» o un error de YAML**: hay una errata en `config.yaml`
     (un espacio de más al principio, comillas…). Compáralo con la versión
     anterior (botón *History*) y corrígelo.
   - **«No se pudo descargar…»**: aviationweather.gov estaba caído. No hagas nada;
     se arregla solo en la siguiente ejecución.
   - **Pruebas que fallan** (`FAILED`): un cambio en `scripts/` ha roto algo.
     Deshaz el último cambio de esa carpeta.
3. Para relanzarla a mano: **Actions** → «Actualizar y publicar» → **Run workflow**.
4. Si GitHub avisa por correo de que ha **desactivado** la tarea por inactividad,
   entra en **Actions** y pulsa **Enable workflow**.

---

## Trabajar en tu ordenador

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q tests/        # pruebas
.venv/bin/python scripts/actualizar.py      # descargar datos ahora
.venv/bin/python scripts/historico.py       # recalcular estadísticas
.venv/bin/python scripts/servir_local.py    # ver la web en http://localhost:8000
```

`scripts/descargar_historico.py` solo se ejecuta una vez (ya está hecho).

## Fuentes

- METAR y TAF: [aviationweather.gov](https://aviationweather.gov/) (NOAA, EE. UU.).
- Histórico: [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/request/download.phtml).
- Pistas y mínimos: [AIP de España, GEML](https://aip.enaire.es/AIP/#GEML) (AIRAC AMDT 09/26) y
  Reglamento (UE) 965/2012, AMC CAT.OP.MPA.110 (visibilidad en circuito, categoría B).
