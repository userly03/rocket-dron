"""Relieve del terreno (colinas) — línea de vista física, P4 de la
crítica "científico militar" de esta sesión.

Port EXACTO (verificado bit a bit, no aproximado) del generador de ruido
y ``alturaTerreno()`` de ``frontend/js/render3d.js`` — mismo generador
pseudoaleatorio (mulberry32, con la aritmética de enteros de 32 bits
replicada a mano), mismas semillas, misma grilla, mismo tileado
periódico de la octava de ondulación. El objetivo es que el backend y el
frontend estén de acuerdo sobre DÓNDE hay una colina: si el relieve que
ve el jugador en el mapa 3D fuera distinto del que usa la física para
bloquear línea de vista, sería una fuente de confusión real (un disparo
que "debería" pasar por encima de una colina visible se bloquea, o al
revés). Verificado con un script standalone comparando 552 puntos de
muestra contra la salida real de ``node`` sobre el JS original:
diferencia máxima 0.0 — paridad exacta, no "suficientemente parecido".

Estas constantes NO son configurables por variable de entorno (a
diferencia de casi todo en ``src/config.py``): si alguien las cambiara
solo del lado del backend, el relieve físico y el visual dejarían de
coincidir, que es exactamente lo que este módulo existe para evitar. Si
algún día hace falta cambiar la forma del terreno, hay que cambiar ACÁ Y
en ``frontend/js/render3d.js`` a la vez, a mano.

HALLAZGO IMPORTANTE (verificado numéricamente antes de integrar esto a
ningún disparo real, no asumido): con la amplitud de colinas elegida
esta sesión para el frontend (~13.5m máx, deliberadamente suave para no
tapar la lectura táctica del mapa) y el rango de altitud de vuelo real
de los drones (``DRONE_ALTITUD_MIN/MAX`` = 40-160m), el relieve NUNCA
bloquea línea de vista contra un dron en vuelo normal — medido: 0 de
3000 geometrías aleatorias realistas (cañón/misil/radar contra un dron
a 40-160m) resultaron bloqueadas. El rayo parte del origen del arma
(~8m) y sube hacia el dron mucho más rápido de lo que cualquier colina
de esta amplitud podría seguirle el ritmo, salvo pegado al propio
origen. Para un dron BAJO (0-20m — el caso real: un dron aterrizando por
falla de enlace/jamming, ver ``PerfilLostLink.ATERRIZAR`` en
``src/models/drone.py``, o cualquier objetivo futuro a nivel de suelo),
el mismo experimento da 1928/3000 (64.3%) bloqueadas — el efecto es
real y significativo, no decorativo, pero está CONCENTRADO en el
régimen cerca del suelo, no en el combate aéreo típico. Esto se deja
documentado en vez de "arreglado" (ni la amplitud de las colinas ni el
umbral se tocaron para forzar más bloqueos contra drones en vuelo —
sería ajustar el terreno para conseguir el resultado que uno quiere,
no medir el que da el modelo real).
"""

from __future__ import annotations

from src.config import FIELD_HEIGHT, FIELD_WIDTH

_MASK32 = 0xFFFFFFFF


def _to_int32(x: int) -> int:
    x &= _MASK32
    return x - 0x100000000 if x >= 0x80000000 else x


def _to_uint32(x: int) -> int:
    return x & _MASK32


def _imul(a: int, b: int) -> int:
    """Equivalente a ``Math.imul`` de JS: multiplicación de enteros de
    32 bits con wraparound, resultado con signo (int32)."""
    return _to_int32((_to_uint32(a) * _to_uint32(b)) & _MASK32)


def _mulberry32(seed: int):
    """Mismo PRNG que ``mulberry32`` en render3d.js, mismos bits."""
    state = _to_int32(seed)

    def rng() -> float:
        nonlocal state
        state = _to_int32(state + 0x6D2B79F5)
        t = _imul(state ^ (_to_uint32(state) >> 15), 1 | state)
        t = _to_int32((t + _imul(t ^ (_to_uint32(t) >> 7), 61 | t)) ^ t)
        return _to_uint32(t ^ (_to_uint32(t) >> 14)) / 4294967296.0

    return rng


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _suavizar(t: float) -> float:
    return t * t * (3 - 2 * t)


def _crear_ruido_valor(seed: int, grid_size: int, periodico: bool = False):
    """Mismo ``crearRuidoValor`` que render3d.js: grilla de valores
    pseudoaleatorios interpolados con smoothstep. ``periodico=True``
    fuerza los bordes de la grilla a repetir el lado opuesto (topología
    de toro) — necesario para que la octava de ondulación, que se tilea
    ×3 con ``% 1`` en ``altura_terreno``, no tenga una costura con
    pendiente artificial en los límites del tile (bug real encontrado y
    corregido esta sesión del lado del frontend, ver
    docs/SEGUIMIENTO_SESION.md §9.10 — replicado acá correcto desde el
    principio)."""
    rng = _mulberry32(seed)
    grid = [[rng() for _ in range(grid_size + 1)] for _ in range(grid_size + 1)]
    if periodico:
        for j in range(grid_size + 1):
            grid[grid_size][j] = grid[0][j]
        for i in range(grid_size + 1):
            grid[i][grid_size] = grid[i][0]

    def muestra(u: float, v: float) -> float:
        gx = min(max(u, 0.0), 0.999999) * grid_size
        gy = min(max(v, 0.0), 0.999999) * grid_size
        x0 = int(gx)
        y0 = int(gy)
        tx = _suavizar(gx - x0)
        ty = _suavizar(gy - y0)
        a = _lerp(grid[x0][y0], grid[x0 + 1][y0], tx)
        b = _lerp(grid[x0][y0 + 1], grid[x0 + 1][y0 + 1], tx)
        return _lerp(a, b, ty)

    return muestra


# Semillas, tamaños de grilla y amplitudes — copiados literales de
# render3d.js (ruidoColinas/ruidoOndulacion/ALTURA_COLINAS_M/
# ALTURA_ONDULACION_M). Cualquier cambio acá SIN el mismo cambio en el
# frontend rompe la paridad visual/física que este módulo existe para
# garantizar.
_ruido_colinas = _crear_ruido_valor(11, 6, periodico=False)
_ruido_ondulacion = _crear_ruido_valor(23, 17, periodico=True)
ALTURA_COLINAS_M = 11.0
ALTURA_ONDULACION_M = 2.5


def altura_terreno(wx: float, wy: float) -> float:
    """Altura del terreno (metros) en una coordenada del mundo (wx, wy)
    — mismo resultado, bit a bit, que ``alturaTerreno()`` en
    frontend/js/render3d.js para el mismo (wx, wy). Ver el docstring del
    módulo para el hallazgo sobre cuándo esto efectivamente importa para
    línea de vista."""
    u = wx / FIELD_WIDTH
    v = wy / FIELD_HEIGHT
    u_ond = (u * 3) % 1
    v_ond = (v * 3) % 1
    return _ruido_colinas(u, v) * ALTURA_COLINAS_M + _ruido_ondulacion(u_ond, v_ond) * ALTURA_ONDULACION_M
