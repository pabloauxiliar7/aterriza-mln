"""
Reglas: compara la meteorología con los mínimos de config.yaml.

Semáforo:
  - rojo:  no se cumple ningún procedimiento.
  - ámbar: el mejor procedimiento se cumple, pero algún valor está
           dentro del margen de «marginal».
  - verde: se cumple con holgura.
  - gris:  faltan datos (en el METAR o en config.yaml) para decidir.
"""

import math
from pathlib import Path

import yaml

from metar import techo, miles

RAIZ = Path(__file__).resolve().parent.parent
PENDIENTE = "RELLENAR"

TEXTOS_ESTADO = {
    "verde": "Por encima de los mínimos",
    "ambar": "Condiciones marginales",
    "rojo": "Por debajo de los mínimos",
    "gris": "Sin datos suficientes",
}


# ---------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------

def _valor(v):
    """Convierte «RELLENAR» (o vacío) en None; deja los números igual."""
    if v is None or (isinstance(v, str) and v.strip().upper() == PENDIENTE):
        return None
    return float(v)


def cargar_config(ruta=None):
    """Lee config.yaml y devuelve un diccionario normalizado."""
    ruta = Path(ruta) if ruta else RAIZ / "config.yaml"
    with open(ruta, encoding="utf-8") as f:
        bruto = yaml.safe_load(f)

    pendientes = []

    def leer(valor, nombre):
        v = _valor(valor)
        if v is None:
            pendientes.append(nombre)
        return v

    aeropuerto = bruto["aeropuerto"]
    config = {
        "oaci": aeropuerto["oaci"],
        "nombre": aeropuerto.get("nombre", aeropuerto["oaci"]),
        "zona_horaria": aeropuerto["zona_horaria"],
        "declinacion": leer(aeropuerto.get("declinacion_magnetica_este"),
                            "declinación magnética") or 0.0,
        "pistas": {},
        "procedimientos": [],
        "cruzado_max": leer(bruto["viento"].get("cruzado_maximo_kt"), "viento cruzado máximo"),
        "cola_max": leer(bruto["viento"].get("cola_maximo_kt"), "viento de cola máximo"),
        "margen": (leer(bruto.get("margen_marginal_pct"), "margen de marginal") or 0.0) / 100,
    }
    for nombre, pista in bruto["pistas"].items():
        config["pistas"][str(nombre)] = leer(pista.get("rumbo_magnetico"),
                                             f"rumbo de la pista {nombre}")
    for p in bruto["procedimientos"]:
        config["procedimientos"].append({
            "nombre": p["nombre"],
            "pista": str(p.get("pista", "cualquiera")),
            "techo_min": leer(p.get("techo_minimo_ft"), f"techo mínimo de {p['nombre']}"),
            "vis_min": leer(p.get("visibilidad_minima_m"), f"visibilidad mínima de {p['nombre']}"),
        })
    config["pendientes"] = pendientes
    config["viento_evaluado"] = (config["cruzado_max"] is not None
                                 or config["cola_max"] is not None)
    return config


# ---------------------------------------------------------------------
# Viento por pista
# ---------------------------------------------------------------------

def componentes(direccion_mag, velocidad, rumbo_pista):
    """
    Descompone el viento en cruzado y de cara/cola respecto a una pista.
    Devuelve (cruzado, cara) en nudos; «cara» negativo = viento de cola.
    """
    angulo = math.radians(direccion_mag - rumbo_pista)
    return abs(velocidad * math.sin(angulo)), velocidad * math.cos(angulo)


def viento_por_pista(viento, config):
    """
    Calcula viento cruzado, de cara y de cola en cada pista, con la
    velocidad media y con la ráfaga. Devuelve None si no hay dato.

    Viento variable (VRB): como no se sabe la dirección, por prudencia
    se cuenta toda la velocidad como cruzado y como cola en todas las
    pistas.
    """
    if viento is None or viento.get("desconocido"):
        return None
    resultado = []
    for pista, rumbo in config["pistas"].items():
        if rumbo is None:
            return None
        fila = {"pista": pista}
        for clave, vel in (("", viento["velocidad"]), ("_racha", viento["racha"])):
            if vel is None:
                fila["cruzado" + clave] = fila["cara" + clave] = fila["cola" + clave] = None
                continue
            if viento["calma"]:
                cruzado, cara = 0.0, 0.0
            elif viento["variable"]:
                cruzado, cara = float(vel), -float(vel)
            else:
                # Norte geográfico → norte magnético (declinación este: se resta).
                direccion_mag = viento["direccion"] - config["declinacion"]
                cruzado, cara = componentes(direccion_mag, vel, rumbo)
            fila["cruzado" + clave] = round(cruzado)
            fila["cara" + clave] = max(0, round(cara))
            fila["cola" + clave] = max(0, round(-cara))
        # Valor que se compara con los límites: el peor entre media y ráfaga.
        fila["cruzado_max"] = max(fila["cruzado"], fila["cruzado_racha"] or 0)
        fila["cola_max"] = max(fila["cola"], fila["cola_racha"] or 0)
        resultado.append(fila)
    return resultado


# ---------------------------------------------------------------------
# Evaluación de cada criterio
# ---------------------------------------------------------------------
# Cada criterio devuelve un diccionario con:
#   ok:        True (cumple), False (no cumple) o None (no se sabe)
#   marginal:  True si cumple pero está dentro del margen
#   frase:     explicación corta para el usuario

def _criterio_techo(altura, conocido, minimo, margen):
    if minimo is None:
        return {"ok": None, "marginal": False, "frase": "falta el techo mínimo en config.yaml"}
    if not conocido:
        return {"ok": None, "marginal": False, "frase": "no se conoce el techo de nubes"}
    if altura is None:
        return {"ok": True, "marginal": False, "frase": "sin techo de nubes"}
    if altura < minimo:
        return {"ok": False, "marginal": False,
                "frase": f"techo {miles(altura)} ft, por debajo de {miles(round(minimo))} ft"}
    marginal = altura < minimo * (1 + margen)
    frase = (f"techo {miles(altura)} ft, cerca del mínimo de {miles(round(minimo))} ft"
             if marginal else f"techo {miles(altura)} ft")
    return {"ok": True, "marginal": marginal, "frase": frase}


def _texto_visibilidad(metros):
    return "visibilidad 10 km o más" if metros >= 10000 else f"visibilidad {miles(metros)} m"


def _criterio_visibilidad(metros, minimo, margen):
    if minimo is None:
        return {"ok": None, "marginal": False, "frase": "falta la visibilidad mínima en config.yaml"}
    if metros is None:
        return {"ok": None, "marginal": False, "frase": "no se conoce la visibilidad"}
    if metros < minimo:
        return {"ok": False, "marginal": False,
                "frase": f"visibilidad {miles(metros)} m, por debajo de {miles(round(minimo))} m"}
    marginal = metros < minimo * (1 + margen)
    frase = (f"visibilidad {miles(metros)} m, cerca del mínimo de {miles(round(minimo))} m"
             if marginal else _texto_visibilidad(metros))
    return {"ok": True, "marginal": marginal, "frase": frase}


def _criterio_viento(por_pista, pista_proc, config):
    """El viento cumple si alguna pista permitida está dentro de límites."""
    if not config["viento_evaluado"]:
        return None  # informativo: no cuenta
    if por_pista is None:
        return {"ok": None, "marginal": False, "frase": "no se conoce el viento"}
    lim_c, lim_t, m = config["cruzado_max"], config["cola_max"], config["margen"]
    candidatas = [f for f in por_pista if pista_proc == "cualquiera" or f["pista"] == pista_proc]
    mejor = None
    for f in candidatas:
        fallos, cerca = [], []
        if lim_c is not None:
            if f["cruzado_max"] > lim_c:
                fallos.append(f"viento cruzado {f['cruzado_max']} kt en pista {f['pista']}, "
                              f"por encima de {round(lim_c)} kt")
            elif f["cruzado_max"] > lim_c * (1 - m):
                cerca.append(f"viento cruzado {f['cruzado_max']} kt, cerca del límite de {round(lim_c)} kt")
        if lim_t is not None:
            if f["cola_max"] > lim_t:
                fallos.append(f"viento de cola {f['cola_max']} kt en pista {f['pista']}, "
                              f"por encima de {round(lim_t)} kt")
            elif f["cola_max"] > lim_t * (1 - m):
                cerca.append(f"viento de cola {f['cola_max']} kt, cerca del límite de {round(lim_t)} kt")
        r = {"ok": not fallos, "marginal": not fallos and bool(cerca),
             "frase": " y ".join(fallos or cerca) or f"viento dentro de límites en pista {f['pista']}",
             "pista": f["pista"]}
        # Preferencia: cumple sin margen > cumple en margen > no cumple.
        if mejor is None or (r["ok"], not r["marginal"]) > (mejor["ok"], not mejor["marginal"]):
            mejor = r
    return mejor


def _evaluar_procedimiento(proc, cond, por_pista, config):
    altura, conocido = techo(cond)
    criterios = {
        "techo": _criterio_techo(altura, conocido, proc["techo_min"], config["margen"]),
        "visibilidad": _criterio_visibilidad(cond["visibilidad_m"], proc["vis_min"], config["margen"]),
    }
    viento = _criterio_viento(por_pista, proc["pista"], config)
    if viento is not None:
        criterios["viento"] = viento
    oks = [c["ok"] for c in criterios.values()]
    if False in oks:
        ok = False
    elif None in oks:
        ok = None
    else:
        ok = True
    marginal = ok is True and any(c["marginal"] for c in criterios.values())
    return {"procedimiento": proc["nombre"], "ok": ok, "marginal": marginal, "criterios": criterios}


def _orden(res):
    """Para elegir el mejor procedimiento: mayor es mejor."""
    puntos = {True: 3, None: 1, False: 0}[res["ok"]]
    if res["ok"] and not res["marginal"]:
        puntos += 1
    fallos = sum(1 for c in res["criterios"].values() if c["ok"] is False)
    return (puntos, -fallos)


def _frase(lista):
    texto = " y ".join(lista)
    return texto[:1].upper() + texto[1:] + "." if texto else ""


# ---------------------------------------------------------------------
# Semáforo
# ---------------------------------------------------------------------

def evaluar(cond, config):
    """
    Aplica las reglas a unas condiciones (de un METAR o de una hora del
    TAF) y devuelve el semáforo con su motivo.
    """
    por_pista = viento_por_pista(cond["viento"], config)
    resultados = [_evaluar_procedimiento(p, cond, por_pista, config)
                  for p in config["procedimientos"]]
    mejor = max(resultados, key=_orden)  # en caso de empate, el primero
    criterios = mejor["criterios"]

    if mejor["ok"] is True:
        estado = "ambar" if mejor["marginal"] else "verde"
        if estado == "ambar":
            motivo = _frase([c["frase"] for c in criterios.values() if c["marginal"]])
        else:
            # El titular ya dice «Por encima de los mínimos»; aquí, los valores.
            partes = [criterios["techo"]["frase"], criterios["visibilidad"]["frase"]]
            motivo = _frase(partes)
            if "viento" in criterios:
                motivo += " Viento dentro de límites."
    elif mejor["ok"] is None:
        estado = "gris"
        motivo = "No se puede calcular: " + " y ".join(
            c["frase"] for c in criterios.values() if c["ok"] is None) + "."
    else:
        estado = "rojo"
        motivo = _frase([c["frase"] for c in criterios.values() if c["ok"] is False])

    altura, conocido = techo(cond)
    return {
        "estado": estado,
        "texto": TEXTOS_ESTADO[estado],
        "motivo": motivo,
        "procedimiento": mejor["procedimiento"],
        # Causas por las que no se cumple (sirven para el histórico).
        "causas": [k for k, c in criterios.items() if c["ok"] is False],
        "techo_ft": altura,
        "techo_conocido": conocido,
        "visibilidad_m": cond["visibilidad_m"],
        "viento_por_pista": por_pista,
        "viento_evaluado": config["viento_evaluado"],
        "procedimientos": [{"nombre": r["procedimiento"], "ok": r["ok"], "marginal": r["marginal"]}
                           for r in resultados],
    }
