"""
Lectura del TAF (previsión de aeropuerto) y división en franjas de una hora.

Un TAF tiene una previsión base y grupos de cambio:
  FMddhhmm      desde esa hora, condiciones totalmente nuevas
  BECMG d/h     cambio gradual dentro del periodo
  TEMPO d/h     cambios temporales (ratos) dentro del periodo
  PROB30/40     probabilidad del 30 % o 40 % (a veces con TEMPO)

Criterio de cada hora:
  - «Previsto»: base + FM + BECMG. Durante un BECMG se toma el peor
    caso entre antes y después del cambio (por prudencia).
  - «Posible»: cada TEMPO o PROB que afecte a esa hora, aparte.
"""

import copy
import re
from datetime import datetime, timedelta, timezone

from metar import condiciones_vacias, leer_grupo, RE_NUBES, RE_VV, RE_TIEMPO
from reglas import evaluar

RE_PERIODO = re.compile(r"^(\d{2})(\d{2})/(\d{2})(\d{2})$")
RE_FM = re.compile(r"^FM(\d{2})(\d{2})(\d{2})$")
RE_EMISION = re.compile(r"^(\d{2})(\d{2})(\d{2})Z$")
RE_PROB = re.compile(r"^PROB(\d{2})$")
RE_TEMP_EXTREMA = re.compile(r"^T[XN]M?\d{2}/\d{4}Z$")

GRAVEDAD = {"verde": 0, "ambar": 1, "gris": 2, "rojo": 3}


def _fecha(dia, hora, minuto, referencia):
    """
    Convierte día/hora del TAF en fecha completa, usando como referencia
    la fecha de emisión (para saber año y mes). Admite «24» como hora.
    """
    base = referencia.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if dia < referencia.day - 15:          # el TAF cruza a mes siguiente
        base = (base + timedelta(days=32)).replace(day=1)
    elif dia > referencia.day + 15:        # (raro) el día es del mes anterior
        base = (base - timedelta(days=1)).replace(day=1)
    return base + timedelta(days=dia - 1, hours=hora, minutes=minuto)


def leer_taf(texto, ahora=None):
    """
    Trocea el TAF en segmentos. Devuelve un diccionario con la emisión,
    la validez, las condiciones base y la lista de cambios.
    «ahora» sirve para deducir el año y el mes (por defecto, la hora actual).
    """
    ahora = ahora or datetime.now(timezone.utc)
    grupos = " ".join(texto.replace("=", " ").split()).split()
    i = 0
    while i < len(grupos) and grupos[i] in ("TAF", "AMD", "COR"):
        i += 1
    estacion = grupos[i]
    i += 1

    emision = ahora
    if i < len(grupos) and RE_EMISION.match(grupos[i]):
        d, h, m = map(int, RE_EMISION.match(grupos[i]).groups())
        emision = _fecha(d, h, m, ahora)
        i += 1
    d1, h1, d2, h2 = map(int, RE_PERIODO.match(grupos[i]).groups())
    desde, hasta = _fecha(d1, h1, 0, emision), _fecha(d2, h2, 0, emision)
    i += 1

    # Separar en segmentos: [tipo, probabilidad, inicio, fin, grupos]
    segmentos = [{"tipo": "BASE", "prob": None, "inicio": desde, "fin": hasta, "grupos": []}]
    while i < len(grupos):
        g = grupos[i]
        if RE_FM.match(g):
            d, h, m = map(int, RE_FM.match(g).groups())
            segmentos.append({"tipo": "FM", "prob": None, "inicio": _fecha(d, h, m, emision),
                              "fin": hasta, "grupos": []})
        elif g in ("BECMG", "TEMPO") or RE_PROB.match(g):
            prob = None
            tipo = g
            if RE_PROB.match(g):
                prob = int(RE_PROB.match(g).group(1))
                tipo = "PROB"
                if i + 1 < len(grupos) and grupos[i + 1] == "TEMPO":
                    tipo = "PROB TEMPO"
                    i += 1
            if i + 1 < len(grupos) and RE_PERIODO.match(grupos[i + 1]):
                a, b, c, e = map(int, RE_PERIODO.match(grupos[i + 1]).groups())
                inicio, fin = _fecha(a, b, 0, emision), _fecha(c, e, 0, emision)
                i += 1
            else:
                inicio, fin = desde, hasta
            segmentos.append({"tipo": tipo, "prob": prob, "inicio": inicio, "fin": fin, "grupos": []})
        elif not RE_TEMP_EXTREMA.match(g):
            segmentos[-1]["grupos"].append(g)
        i += 1

    return {"texto": " ".join(grupos), "estacion": estacion, "emision": emision,
            "desde": desde, "hasta": hasta, "segmentos": segmentos}


def aplicar(cond, grupos):
    """
    Aplica los grupos de un cambio sobre unas condiciones previas.
    Solo se sustituye lo que el grupo menciona: si un TEMPO solo habla de
    visibilidad y nubes, el viento sigue siendo el anterior.
    """
    nueva = copy.deepcopy(cond)
    nubes_tocadas = tiempo_tocado = False
    for g in grupos:
        es_nube = bool(RE_NUBES.match(g) or RE_VV.match(g)) or g in ("NSC", "SKC", "NCD")
        m = RE_TIEMPO.match(g)
        es_tiempo = g == "NSW" or bool(m and (m.group(2) or m.group(3)))
        if es_nube and not nubes_tocadas:
            nueva["nubes"], nueva["vv_ft"], nueva["vv_desconocida"] = [], None, False
            nubes_tocadas = True
        if es_tiempo and not es_nube and not tiempo_tocado:
            nueva["tiempo"] = []
            tiempo_tocado = True
        if g != "CAVOK" and (es_nube or es_tiempo or re.match(r"^\d{4}$", g)):
            nueva["cavok"] = False
        leer_grupo(g, nueva)
    return nueva


def _peor(resultados):
    return max(resultados, key=lambda r: GRAVEDAD[r["estado"]])


def franjas(taf, config, desde, horas=24):
    """
    Divide el TAF en franjas de una hora a partir de «desde» (UTC).
    Devuelve una lista de diccionarios, uno por hora.
    """
    base = aplicar(condiciones_vacias(), taf["segmentos"][0]["grupos"])
    cambios = taf["segmentos"][1:]
    inicio = desde.replace(minute=0, second=0, microsecond=0)
    lista = []
    for n in range(horas):
        h = inicio + timedelta(hours=n)
        fin_h = h + timedelta(hours=1)
        if fin_h <= taf["desde"] or h >= taf["hasta"]:
            continue

        # Previsto: se recorren los cambios en orden.
        # «estados» guarda las alternativas posibles (varias si hay un BECMG en curso).
        estados = [base]
        for s in cambios:
            if s["tipo"] == "FM" and s["inicio"] < fin_h:
                nuevo = aplicar(condiciones_vacias(), s["grupos"])
                # Si el FM empieza a mitad de hora, esa hora tiene las dos situaciones.
                estados = [nuevo] if s["inicio"] <= h else estados + [nuevo]
            elif s["tipo"] == "BECMG" and s["inicio"] < fin_h:
                despues = [aplicar(e, s["grupos"]) for e in estados]
                estados = despues if s["fin"] <= h else estados + despues
        previsto = _peor([evaluar(e, config) for e in estados])
        actual = estados[-1]  # sobre lo más reciente se aplican los TEMPO/PROB

        posibles = []
        for s in cambios:
            if s["tipo"] in ("TEMPO", "PROB", "PROB TEMPO") and s["inicio"] < fin_h and s["fin"] > h:
                r = evaluar(aplicar(actual, s["grupos"]), config)
                etiqueta = {"TEMPO": "Temporal", "PROB": f"Probabilidad {s['prob']} %",
                            "PROB TEMPO": f"Temporal, probabilidad {s['prob']} %"}[s["tipo"]]
                posibles.append({"tipo": etiqueta, "estado": r["estado"], "texto": r["texto"],
                                 "motivo": r["motivo"], "grupos": " ".join(s["grupos"])})

        lista.append({
            "inicio_utc": h.strftime("%Y-%m-%dT%H:%MZ"),
            "estado": previsto["estado"],
            "texto": previsto["texto"],
            "motivo": previsto["motivo"],
            "posibles": posibles,
        })
    return lista
