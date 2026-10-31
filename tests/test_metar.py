"""Pruebas del descifrado de METAR (scripts/metar.py)."""

from metar import leer_metar, techo, describir_metar, describir_tiempo


def test_formato_aviationweather():
    d = leer_metar("METAR GEML 311100Z 08005KT 350V150 9999 FEW006 SCT014 24/17 Q1019")
    assert d["estacion"] == "GEML"
    assert (d["dia"], d["hora"], d["minuto"]) == (31, 11, 0)
    assert d["viento"]["direccion"] == 80
    assert d["viento"]["velocidad"] == 5
    assert (d["viento"]["desde"], d["viento"]["hasta"]) == (350, 150)
    assert d["visibilidad_m"] == 10000
    assert len(d["nubes"]) == 2
    assert d["temperatura"] == 24 and d["rocio"] == 17 and d["qnh"] == 1019
    assert d["no_reconocido"] == []


def test_capas_few_y_sct_no_son_techo():
    d = leer_metar("GEML 311100Z 08005KT 9999 FEW006 SCT014 24/17 Q1019")
    assert techo(d) == (None, True)


def test_techo_es_la_capa_bkn_u_ovc_mas_baja():
    d = leer_metar("GEML 040800Z 08019G31KT 050V120 9999 BKN011 OVC017 13/10 Q1005")
    assert techo(d) == (1100, True)
    d = leer_metar("GEML 030900Z 25003KT 1500 BR SCT002 OVC003 10/10 Q1028")
    assert techo(d) == (300, True)


# --- Casos inventados -------------------------------------------------

def test_cavok():
    d = leer_metar("GEML 010000Z 00000KT CAVOK 20/10 Q1015")
    assert d["cavok"] is True
    assert d["visibilidad_m"] == 10000
    assert d["viento"]["calma"] is True
    assert techo(d) == (None, True)
    assert any("CAVOK" in f for f in describir_metar(d))


def test_vv_es_techo():
    d = leer_metar("GEML 010600Z VRB01KT 0200 FG VV002 12/12 Q1020")
    assert d["vv_ft"] == 200
    assert techo(d) == (200, True)
    assert d["viento"]["variable"] is True


def test_vv_desconocida():
    d = leer_metar("GEML 010600Z AUTO 00000KT 0100 FG VV/// 12/12 Q1020")
    assert techo(d) == (None, False)


def test_niebla_sin_techo():
    d = leer_metar("GEML 180500Z 25003KT 0800 R33/P2000 FG SCT001 10/09 Q1020")
    assert d["visibilidad_m"] == 800
    assert d["tiempo"] == ["FG"]
    assert techo(d) == (None, True)
    assert d["rvr"] == ["R33/P2000"]


def test_rafagas():
    d = leer_metar("GEML 010000Z 27025G45KT 9999 FEW030 18/05 Q1005")
    assert d["viento"]["velocidad"] == 25
    assert d["viento"]["racha"] == 45


def test_nubes_desconocidas_dejan_el_techo_sin_saber():
    d = leer_metar("GEML 010000Z AUTO 10007KT 9999 FEW015 //////CB 16/14 Q1021")
    assert techo(d) == (None, False)
    d = leer_metar("GEML 010000Z AUTO 10007KT 9999 FEW015 ///CB 16/14 Q1021")
    assert techo(d) == (None, False)
    assert d["no_reconocido"] == []


def test_capa_desconocida_no_importa_si_hay_techo_conocido_mas_bajo():
    d = leer_metar("GEML 010000Z AUTO 10007KT 6000 BKN008 ////// 16/14 Q1021")
    assert techo(d) == (800, True)


def test_parte_automatico_sin_datos():
    d = leer_metar("GEML 220100Z AUTO /////KT //// R33///// ////// ///// Q////")
    assert d["viento"]["desconocido"] is True
    assert d["visibilidad_m"] is None and d["visibilidad_desconocida"]
    assert techo(d) == (None, False)


def test_ncd_y_nsc_significan_sin_nubes():
    for codigo in ("NCD", "NSC"):
        d = leer_metar(f"GEML 022000Z AUTO 34003KT 7000 {codigo} 11/09 Q1029")
        assert d["sin_nubes"] and techo(d) == (None, True)


def test_visibilidad_minima_direccional():
    d = leer_metar("GEML 040500Z VRB01KT 9999 2500SE FEW002 07/07 Q1020")
    assert d["visibilidad_m"] == 10000
    assert d["vis_minima"] == {"metros": 2500, "direccion": "SE"}


def test_tendencia_no_se_mezcla_con_la_observacion():
    d = leer_metar("GEML 010000Z 27010KT 9999 FEW030 18/05 Q1005 TEMPO 2000 BR")
    assert d["visibilidad_m"] == 10000
    assert d["tiempo"] == []


def test_cizalladura_y_tiempo_reciente():
    d = leer_metar("GEML 040900Z 08020G33KT 9999 BKN011 13/11 Q1005 RERA WS ALL RWY")
    assert d["tiempo_reciente"] == ["RA"]
    assert d["cizalladura"] is True
    assert d["no_reconocido"] == []


def test_temperaturas_negativas():
    d = leer_metar("GEML 010600Z 00000KT 9999 FEW030 M01/M03 Q1030")
    assert d["temperatura"] == -1 and d["rocio"] == -3


def test_descripcion_en_castellano():
    assert describir_tiempo("-RA") == "lluvia débil"
    assert describir_tiempo("VCTS") == "tormenta en las proximidades"
    assert describir_tiempo("BCFG") == "niebla en bancos"
    assert describir_tiempo("+SHRA") == "chubascos de lluvia fuerte"
    assert describir_tiempo("TSRA") == "tormenta con lluvia"
    frases = describir_metar(leer_metar(
        "GEML 191330Z 24020G40KT 140V280 9999 FEW050 20/05 Q1009"))
    assert frases[0] == ("Viento: del 240° a 20 kt, con ráfagas de 40 kt "
                         "(cambiando entre 140° y 280°).")
