"""Pruebas de historico.py: selección de un parte por hora."""

from datetime import datetime, timezone

from historico import un_parte_por_hora


def utc(h, m=0):
    return datetime(2026, 1, 1, h, m, tzinfo=timezone.utc)


def test_se_prefiere_el_parte_de_la_hora_en_punto():
    obs = [("2026-01-01 10:00", "A"), ("2026-01-01 10:30", "B"), ("2026-01-01 11:00", "C")]
    assert un_parte_por_hora(obs) == {utc(10): "A", utc(11): "C"}


def test_si_falta_la_hora_en_punto_se_usa_el_mas_cercano():
    obs = [("2026-01-01 09:50", "especial"), ("2026-01-01 10:30", "B")]
    assert un_parte_por_hora(obs)[utc(10)] == "especial"


def test_un_parte_de_las_y_media_solo_cuenta_una_vez():
    assert un_parte_por_hora([("2026-01-01 10:30", "B")]) == {utc(10): "B"}
