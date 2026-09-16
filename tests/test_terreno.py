"""Relieve del terreno (src/engine/terreno.py) — P4 de la crítica
"científico militar" de esta sesión.

Lo único que importa verificar acá es la PARIDAD con el frontend
(frontend/js/render3d.js): mismo generador, mismas semillas, mismo
resultado bit a bit para el mismo (x, y) — si backend y frontend alguna
vez dan un valor distinto para el mismo punto, el relieve que el
jugador VE deja de coincidir con el que la física USA para línea de
vista, que es exactamente el problema que este módulo existe para
evitar (ver el docstring de terreno.py).

Los valores de referencia de abajo se generaron UNA vez ejecutando el
JS original con ``node`` (no a mano, no estimados) y se congelan acá
como test de regresión — así no hace falta tener ``node`` instalado
para correr la suite, pero un cambio futuro que rompa la paridad sí se
detecta.
"""

from __future__ import annotations

import pytest

from src.engine.terreno import ALTURA_COLINAS_M, ALTURA_ONDULACION_M, altura_terreno

# (x, y, altura_esperada) — generados con node sobre frontend/js/render3d.js
# el 2026-09-16 (ver docs/SEGUIMIENTO_SESION.md §9.14), no re-derivados a mano.
PUNTOS_DE_REFERENCIA_JS = [
    (0, 0, 5.85926419775933),
    (500, 500, 6.278232142853085),
    (1000, 1000, 5.70165485165758),
    (100, 900, 6.81784287299853),
    (947.8653606090633, 394.8234964231735, 5.05579785951728),
    (250.7, 733.2, 7.523116387812511),
]


class TestParidadConElFrontend:
    @pytest.mark.parametrize("x,y,esperado", PUNTOS_DE_REFERENCIA_JS)
    def test_coincide_bit_a_bit_con_la_salida_real_de_node(self, x, y, esperado):
        obtenido = altura_terreno(x, y)
        assert obtenido == pytest.approx(esperado, abs=1e-9), (
            f"altura_terreno({x},{y}) = {obtenido!r}, "
            f"frontend (node) da {esperado!r} — la paridad backend/frontend se rompió"
        )


class TestPropiedadesBasicas:
    def test_es_determinista_reproducible(self):
        """Mismo (x,y) -> mismo resultado siempre — el terreno no es
        aleatorio en cada llamada, es una función fija del punto."""
        a = altura_terreno(321.5, 678.2)
        b = altura_terreno(321.5, 678.2)
        assert a == b

    def test_altura_dentro_de_la_amplitud_declarada(self):
        """La suma de las dos octavas de ruido (cada una en [0,1]) nunca
        puede superar ALTURA_COLINAS_M + ALTURA_ONDULACION_M, ni bajar
        de 0 — cota estructural, no una medición."""
        maximo_posible = ALTURA_COLINAS_M + ALTURA_ONDULACION_M
        for x in range(0, 1001, 97):
            for y in range(0, 1001, 131):
                h = altura_terreno(x, y)
                assert 0.0 <= h <= maximo_posible

    def test_sin_costura_en_los_limites_del_tile_de_ondulacion(self):
        """Bug real encontrado y corregido del lado del frontend esta
        sesión (docs/SEGUIMIENTO_SESION.md §9.10): la octava de
        ondulación se tilea ×3 con `% 1`, y sin una grilla PERIÓDICA
        (ver crear_ruido_valor) el límite de cada tile (x = 1000/3,
        2000/3, y lo mismo en y) tenía una pendiente ~10x más empinada
        que la típica — replicado correcto acá desde el principio, este
        test lo deja como contrato explícito para que no reaparezca."""
        import math

        def gradiente(x0, y0, x1, y1):
            return abs(altura_terreno(x1, y1) - altura_terreno(x0, y0)) / math.hypot(x1 - x0, y1 - y0)

        # gradiente típico, lejos de cualquier costura
        tipico = gradiente(700.0, 500.0, 704.0, 500.0)
        # gradiente justo en la costura del tile (x = 1000/3)
        seam_x = 1000.0 / 3.0
        en_costura = gradiente(seam_x - 0.5, 500.0, seam_x + 0.5, 500.0)
        assert en_costura < tipico * 3, (
            f"gradiente en la costura ({en_costura:.4f}) mucho más empinado que "
            f"el típico ({tipico:.4f}) — la grilla de ondulación dejó de ser periódica"
        )
