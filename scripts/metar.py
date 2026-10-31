"""
Lectura de METAR y TAF: convierte el texto codificado en datos.

Un METAR es un parte meteorológico de aeropuerto, por ejemplo:
    METAR GEML 311100Z 08005KT 9999 FEW006 SCT014 24/17 Q1019
Este módulo lo trocea en «grupos» (palabras separadas por espacios) y
reconoce cada uno: viento, visibilidad, tiempo presente, nubes, etc.

Lo usan actualizar.py, historico.py y taf.py, así que el criterio es
siempre el mismo en todas partes.
"""

import re

# ---------------------------------------------------------------------
# Patrones de cada grupo (expresiones regulares)
# ---------------------------------------------------------------------

# Viento: dirección (3 cifras o VRB), velocidad, ráfaga opcional, KT.
# Ejemplos: 08005KT, 24020G40KT, VRB02KT, 00000KT, /////KT
RE_VIENTO = re.compile(r"^(\d{3}|VRB|///)(\d{2,3}|//)(?:G(\d{2,3}))?(KT|MPS)$")
# Variación de dirección: 350V150
RE_VARIACION = re.compile(r"^(\d{3})V(\d{3})$")
# Visibilidad general en metros (0000 a 9999) o //// si falta.
RE_VISIBILIDAD = re.compile(r"^(\d{4}|////)(NDV)?$")
# Visibilidad mínima en una dirección: 2500SE
RE_VIS_DIRECCION = re.compile(r"^(\d{4})(N|NE|E|SE|S|SW|W|NW)$")
# Alcance visual en pista: R33/P2000, R33/0125N, R33/1300U
RE_RVR = re.compile(r"^R(\d{2}[LCR]?)/([PM]?)(\d{4})(?:V([PM]?)(\d{4}))?([UDN]?)$")
# Nubes: cobertura + altura en centenares de pies + tipo opcional.
# Ejemplos: FEW006, BKN011, SCT030CB, FEW017///, //////, //////CB, ///CB
RE_NUBES = re.compile(r"^(FEW|SCT|BKN|OVC|///)(\d{3}|///)?(CB|TCU|///)?$")
# Visibilidad vertical (cielo oculto): VV001, VV///
RE_VV = re.compile(r"^VV(\d{3}|///)$")
# Temperatura / punto de rocío: 24/17, M01/M03
RE_TEMPERATURA = re.compile(r"^(M?\d{2}|//)/(M?\d{2}|//)$")
# Presión (QNH) en hectopascales: Q1019
RE_QNH = re.compile(r"^Q(\d{4}|////)$")
# Tiempo presente: intensidad, descriptor y fenómenos. Ej.: -RA, VCTS, BCFG
RE_TIEMPO = re.compile(
    r"^(\+|-|VC)?(MI|PR|BC|DR|BL|SH|TS|FZ)?"
    r"((?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PO|SQ|FC|SS|DS)+)?$"
)
# Hora del parte: 311100Z → día 31, 11:00 UTC
RE_HORA = re.compile(r"^(\d{2})(\d{2})(\d{2})Z$")

# Palabras que marcan el final del parte principal (lo que va detrás
# es tendencia u observaciones y no describe la situación actual).
FIN_DEL_PARTE = {"NOSIG", "BECMG", "TEMPO", "RMK"}

# ---------------------------------------------------------------------
# Traducciones al castellano
# ---------------------------------------------------------------------

COBERTURAS = {
    "FEW": "pocas nubes",
    "SCT": "nubes dispersas",
    "BKN": "nuboso",
    "OVC": "cubierto",
}
TIPOS_NUBE = {"CB": "cumulonimbos", "TCU": "cúmulos de gran desarrollo"}
INTENSIDADES = {"-": "débil", "+": "fuerte"}
DESCRIPTORES = {
    "MI": "baja", "PR": "parcial", "BC": "en bancos", "DR": "levantada",
    "BL": "ventisca", "SH": "chubascos de", "TS": "tormenta", "FZ": "engelante",
}
FENOMENOS = {
    "DZ": "llovizna", "RA": "lluvia", "SN": "nieve", "SG": "cinarra",
    "IC": "cristales de hielo", "PL": "hielo granulado", "GR": "granizo",
    "GS": "granizo pequeño", "UP": "precipitación sin identificar",
    "BR": "neblina", "FG": "niebla", "FU": "humo", "VA": "ceniza volcánica",
    "DU": "polvo", "SA": "arena", "HZ": "calima", "PO": "remolinos de polvo",
    "SQ": "turbonada", "FC": "tromba", "SS": "tempestad de arena",
    "DS": "tempestad de polvo",
}
PUNTOS_CARDINALES = {
    "N": "norte", "NE": "noreste", "E": "este", "SE": "sureste",
    "S": "sur", "SW": "suroeste", "W": "oeste", "NW": "noroeste",
}


# ---------------------------------------------------------------------
# Lectura de los grupos de condiciones (común a METAR y TAF)
# ---------------------------------------------------------------------

def condiciones_vacias():
    """Devuelve un diccionario con todos los elementos sin rellenar."""
    return {
        "viento": None,          # dict con dirección, velocidad, ráfaga…
        "visibilidad_m": None,   # metros; 10000 significa «10 km o más»
        "visibilidad_desconocida": False,
        "vis_minima": None,      # {"metros": 2500, "direccion": "SE"}
        "cavok": False,
        "tiempo": [],            # lista de códigos: ["-RA", "BR"]
        "nubes": [],             # lista de capas
        "sin_nubes": False,      # NSC, NCD, SKC, CAVOK
        "vv_ft": None,           # visibilidad vertical en pies
        "vv_desconocida": False,
    }


def leer_grupo(grupo, cond):
    """
    Intenta reconocer un grupo de condiciones y lo guarda en «cond».
    Devuelve True si lo ha reconocido, False si no.
    """
    m = RE_VIENTO.match(grupo)
    if m:
        direccion, velocidad, racha, unidad = m.groups()
        if velocidad == "//":
            cond["viento"] = {"desconocido": True}
            return True
        factor = 1.94384 if unidad == "MPS" else 1  # m/s → nudos
        vel = round(int(velocidad) * factor)
        cond["viento"] = {
            "desconocido": direccion == "///",
            "variable": direccion == "VRB",
            "direccion": int(direccion) if direccion.isdigit() else None,
            "velocidad": vel,
            "racha": round(int(racha) * factor) if racha else None,
            "calma": vel == 0,
            "desde": None,
            "hasta": None,
        }
        return True

    m = RE_VARIACION.match(grupo)
    if m and cond["viento"]:
        cond["viento"]["desde"] = int(m.group(1))
        cond["viento"]["hasta"] = int(m.group(2))
        return True

    if grupo == "CAVOK":
        # CAVOK: visibilidad ≥ 10 km, sin nubes por debajo de 5000 ft
        # ni cumulonimbos, y sin tiempo significativo.
        cond["cavok"] = True
        cond["visibilidad_m"] = 10000
        cond["sin_nubes"] = True
        cond["nubes"] = []
        cond["vv_ft"] = None
        cond["tiempo"] = []
        return True

    m = RE_VISIBILIDAD.match(grupo)
    if m:
        if m.group(1) == "////":
            cond["visibilidad_desconocida"] = True
            cond["visibilidad_m"] = None
        else:
            metros = int(m.group(1))
            cond["visibilidad_m"] = 10000 if metros == 9999 else metros
            cond["visibilidad_desconocida"] = False
        return True

    m = RE_VIS_DIRECCION.match(grupo)
    if m:
        cond["vis_minima"] = {"metros": int(m.group(1)), "direccion": m.group(2)}
        return True

    if grupo in ("NSC", "NCD", "SKC", "CLR"):
        cond["sin_nubes"] = True
        cond["nubes"] = []
        cond["vv_ft"] = None
        return True

    m = RE_VV.match(grupo)
    if m:
        if m.group(1) == "///":
            cond["vv_desconocida"] = True
        else:
            cond["vv_ft"] = int(m.group(1)) * 100
        return True

    m = RE_NUBES.match(grupo)
    if m:
        cobertura, altura, tipo = m.groups()
        cond["nubes"].append({
            "cobertura": None if cobertura == "///" else cobertura,
            "altura_ft": None if altura in (None, "///") else int(altura) * 100,
            "tipo": None if tipo in (None, "///") else tipo,
        })
        cond["sin_nubes"] = False
        return True

    if grupo == "NSW":  # «sin tiempo significativo» (solo en TAF)
        cond["tiempo"] = []
        return True

    m = RE_TIEMPO.match(grupo)
    if m and (m.group(2) or m.group(3)):
        cond["tiempo"].append(grupo)
        return True

    return False


# ---------------------------------------------------------------------
# Lectura de un METAR completo
# ---------------------------------------------------------------------

def leer_metar(texto):
    """
    Convierte el texto de un METAR en un diccionario de datos.
    Acepta el formato de aviationweather.gov («METAR GEML 311100Z …»)
    y el del archivo de Iowa («GEML 311100Z …»).
    """
    texto = " ".join(texto.replace("=", " ").split())
    datos = condiciones_vacias()
    datos.update({
        "texto": texto,
        "estacion": None,
        "dia": None, "hora": None, "minuto": None,
        "automatico": False,
        "corregido": False,
        "rvr": [],
        "temperatura": None, "rocio": None, "qnh": None,
        "tiempo_reciente": [],
        "cizalladura": False,
        "no_reconocido": [],
    })

    grupos = texto.split()
    i = 0
    # Cabecera: tipo de parte, estación y hora.
    while i < len(grupos) and grupos[i] in ("METAR", "SPECI", "COR"):
        if grupos[i] == "COR":
            datos["corregido"] = True
        i += 1
    if i < len(grupos):
        datos["estacion"] = grupos[i]
        i += 1
    if i < len(grupos) and RE_HORA.match(grupos[i]):
        d, h, mi = RE_HORA.match(grupos[i]).groups()
        datos["dia"], datos["hora"], datos["minuto"] = int(d), int(h), int(mi)
        i += 1

    while i < len(grupos):
        g = grupos[i]
        i += 1
        if g in FIN_DEL_PARTE:
            break
        if g == "AUTO":
            datos["automatico"] = True
        elif g == "COR":
            datos["corregido"] = True
        elif g == "WS":
            # Cizalladura: «WS R33» o «WS ALL RWY»
            datos["cizalladura"] = True
            if i < len(grupos) and grupos[i] == "ALL":
                i += 2
            elif i < len(grupos) and grupos[i].startswith("R"):
                i += 1
        elif RE_RVR.match(g):
            datos["rvr"].append(g)
        elif re.match(r"^R\d{2}[LCR]?/+$", g):
            pass  # alcance visual en pista no disponible
        elif g.startswith("RE") and len(g) > 2 and RE_TIEMPO.match(g[2:]):
            datos["tiempo_reciente"].append(g[2:])
        elif RE_TEMPERATURA.match(g):
            t, r = RE_TEMPERATURA.match(g).groups()
            datos["temperatura"] = _grados(t)
            datos["rocio"] = _grados(r)
        elif RE_QNH.match(g):
            q = RE_QNH.match(g).group(1)
            datos["qnh"] = None if q == "////" else int(q)
        elif not leer_grupo(g, datos):
            datos["no_reconocido"].append(g)
    return datos


def _grados(valor):
    """«M03» → -3, «17» → 17, «//» → None."""
    if valor == "//":
        return None
    return -int(valor[1:]) if valor.startswith("M") else int(valor)


# ---------------------------------------------------------------------
# Techo de nubes
# ---------------------------------------------------------------------

def techo(cond):
    """
    Calcula el techo: la capa más baja BKN (nuboso), OVC (cubierto) o
    VV (cielo oculto).

    Devuelve un par (altura_ft, conocido):
      (600, True)    → techo a 600 ft
      (None, True)   → no hay techo (despejado o solo FEW/SCT)
      (None, False)  → no se puede saber (VV/// o capa «//////»)
    """
    if cond["vv_desconocida"]:
        return None, False
    candidatos = []
    if cond["vv_ft"] is not None:
        candidatos.append(cond["vv_ft"])
    dudosa = False
    for capa in cond["nubes"]:
        if capa["cobertura"] in ("BKN", "OVC") and capa["altura_ft"] is not None:
            candidatos.append(capa["altura_ft"])
        elif capa["cobertura"] is None or capa["altura_ft"] is None:
            # Capa de cobertura o altura desconocida: podría ser un techo.
            if capa["cobertura"] in (None, "BKN", "OVC"):
                dudosa = True
    if candidatos:
        return min(candidatos), True
    if dudosa:
        return None, False
    return None, True


# ---------------------------------------------------------------------
# Descripción en castellano
# ---------------------------------------------------------------------

def miles(numero):
    """Formatea con punto de millares: 1150 → «1.150»."""
    return f"{numero:,}".replace(",", ".")


def describir_viento(v):
    if v is None:
        return "Viento: sin dato."
    if v.get("desconocido"):
        return "Viento: no disponible."
    if v["calma"]:
        return "Viento: en calma."
    if v["variable"]:
        texto = f"Viento: de dirección variable, {v['velocidad']} kt"
    else:
        texto = f"Viento: del {v['direccion']:03d}° a {v['velocidad']} kt"
    if v["racha"]:
        texto += f", con ráfagas de {v['racha']} kt"
    if v.get("desde") is not None:
        texto += f" (cambiando entre {v['desde']:03d}° y {v['hasta']:03d}°)"
    return texto + "."


def describir_tiempo(codigo):
    """«-RA» → «lluvia débil», «VCTS» → «tormenta en las proximidades»."""
    m = RE_TIEMPO.match(codigo)
    if not m:
        return codigo
    intensidad, descriptor, fenomenos = m.groups()
    nombres = [FENOMENOS[fenomenos[k:k + 2]] for k in range(0, len(fenomenos or ""), 2)]
    partes = []
    if descriptor == "TS":
        partes.append("tormenta")
        if nombres:
            partes.append("con " + " y ".join(nombres))
    elif descriptor == "SH":
        partes.append("chubascos de " + " y ".join(nombres or ["precipitación"]))
    else:
        partes.append(" y ".join(nombres))
        if descriptor:
            partes.append(DESCRIPTORES[descriptor])
    if intensidad in INTENSIDADES:
        partes.append(INTENSIDADES[intensidad])
    if intensidad == "VC":
        partes.append("en las proximidades")
    return " ".join(p for p in partes if p)


def describir_condiciones(cond):
    """Frases en castellano para viento, visibilidad, tiempo y nubes."""
    frases = [describir_viento(cond["viento"])]

    if cond["cavok"]:
        frases.append("CAVOK: visibilidad de 10 km o más, sin nubes por "
                      "debajo de 5.000 ft y sin fenómenos significativos.")
    else:
        if cond["visibilidad_desconocida"] or cond["visibilidad_m"] is None:
            frases.append("Visibilidad: no disponible.")
        elif cond["visibilidad_m"] >= 10000:
            frases.append("Visibilidad: 10 km o más.")
        else:
            frases.append(f"Visibilidad: {miles(cond['visibilidad_m'])} m.")
        if cond["vis_minima"]:
            vm = cond["vis_minima"]
            frases.append(f"Visibilidad mínima: {miles(vm['metros'])} m hacia "
                          f"el {PUNTOS_CARDINALES[vm['direccion']]}.")
        if cond["tiempo"]:
            frases.append("Tiempo: " + ", ".join(describir_tiempo(t) for t in cond["tiempo"]) + ".")
        if cond["vv_desconocida"]:
            frases.append("Cielo oculto, altura no disponible.")
        elif cond["vv_ft"] is not None:
            frases.append(f"Cielo oculto: visibilidad vertical {miles(cond['vv_ft'])} ft.")
        capas = []
        for capa in cond["nubes"]:
            if capa["cobertura"] is None and capa["altura_ft"] is None:
                texto = "nubes no identificadas"
            else:
                texto = COBERTURAS.get(capa["cobertura"], "nubes de cobertura desconocida")
                texto += (f" a {miles(capa['altura_ft'])} ft" if capa["altura_ft"] is not None
                          else " a altura desconocida")
            if capa["tipo"]:
                texto += f" ({TIPOS_NUBE[capa['tipo']]})"
            capas.append(texto)
        if capas:
            frases.append("Nubes: " + "; ".join(capas) + ".")
        elif cond["sin_nubes"]:
            frases.append("Nubes: ninguna significativa.")
    return frases


def describir_metar(datos):
    """Lista de frases en castellano que explican el METAR completo."""
    frases = []
    if datos["automatico"]:
        frases.append("Parte automático (sin observador).")
    frases += describir_condiciones(datos)
    if datos["rvr"]:
        frases.append("Alcance visual en pista: " + ", ".join(_describir_rvr(r) for r in datos["rvr"]) + ".")
    if datos["temperatura"] is not None:
        frases.append(f"Temperatura {datos['temperatura']} °C, punto de rocío {datos['rocio']} °C.")
    if datos["qnh"] is not None:
        frases.append(f"Presión (QNH): {datos['qnh']} hPa.")
    if datos["tiempo_reciente"]:
        frases.append("Tiempo reciente: " + ", ".join(describir_tiempo(t) for t in datos["tiempo_reciente"]) + ".")
    if datos["cizalladura"]:
        frases.append("Aviso de cizalladura (cambios bruscos de viento).")
    return frases


def _describir_rvr(grupo):
    pista, signo, valor, _, _, _ = RE_RVR.match(grupo).groups()
    prefijo = {"P": "más de ", "M": "menos de "}.get(signo, "")
    return f"pista {pista} {prefijo}{miles(int(valor))} m"
