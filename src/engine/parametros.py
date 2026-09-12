"""Distribuciones de parámetros para el Monte Carlo del modelo (P1-B).

POR QUÉ EXISTE ESTE MÓDULO
==========================
Antes de P1-B, el "Monte Carlo" de ``src/engine/experiments.py`` variaba **solo
la realización del enjambre** (posiciones, cableado, blindaje, altitud): la
configuración del modelo vivía en constantes de módulo de ``src/config.py`` y
era idéntica en todas las réplicas. Consecuencia: el intervalo de confianza que
reportaba describía el muestreo geométrico del enjambre, **no la incertidumbre
epistémica del modelo** (ver docs/AUDITORIA_CHECKLIST.md §1.1).

El paper de referencia (arXiv:2602.08477, Tabla 2) hace otra cosa: 10.000
tiradas variando **ocho parámetros del modelo**. Y su conclusión de
incertidumbre es que la polarización y la orientación del cable **dominan** la
varianza (coeficiente de variación ≈ 39 % a 30 m) — justo dos de los que el
simulador tenía fijos o con distribución distinta.

Este módulo implementa esas ocho distribuciones como objetos de primera clase,
muestreables con un ``numpy.random.Generator`` inyectado (nunca el global: ver
src/utils/reproducibilidad.py y el aislamiento de P0-B).

QUÉ SE CORRIGIÓ RESPECTO AL MODELO VIEJO
========================================
1. **Error de apuntado**: no existía. El paper lo modela ``Rayleigh(σ = 1°)``.
   Con un haz de ~14° de ancho no es despreciable.
2. **Polarización**: el simulador sorteaba ``Uniforme[0.3, 1.0]`` directamente
   como factor de potencia. El paper sortea el **ángulo** ``φ ~ U[0, π]`` y
   deriva ``η_pol = cos²φ`` (con piso 0.1). No es lo mismo: ``cos²`` de un
   ángulo uniforme tiene masa concentrada cerca de 0 y de 1 (distribución tipo
   arcoseno), mientras ``Uniforme[0.3, 1]`` es plana. El modelo viejo
   **subestimaba la varianza** del resultado, y precisamente en la variable que
   el paper señala como dominante.
3. **Longitud de cable**: el simulador usaba ``U[2, 15] cm``; el paper
   ``U[5, 25] cm``. Importa porque la resonancia está en λ₀/2 = 6.12 cm.
4. **Ganancia de antena**: el simulador la derivaba de la apertura del cono con
   ``G ≈ 26000/θ²`` (20.63 dBi a 15°, un −6.4 % sistemático en campo respecto
   al plato real del paper). Con ``diametro_plato_m`` y
   ``eficiencia_apertura`` variables se puede usar la fórmula de plato
   ``G = η(πD/λ)²``, que da 21.16 dBi contra los 21.2 dBi publicados — el
   sesgo baja a −0.5 %. Ver ``hpm_engine.antenna_gain_from_dish``.

COMPATIBILIDAD
==============
``EspecificacionMC.nominal()`` devuelve una especificación donde **todas** las
distribuciones son constantes con el valor por defecto de ``src/config.py``. Un
experimento con esa especificación se comporta exactamente como antes de P1-B,
así que la calibración y la suite existente no se mueven. La variación de
parámetros es opt-in, vía ``EspecificacionMC.del_paper()`` o construyéndola a
mano.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src import config as config_mod


# ═══════════════════════════════════════════════════════════════════════════
# Distribuciones
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Distribucion:
    """Base de las distribuciones muestreables.

    Cada subclase implementa ``muestrear(gen)`` y ``to_dict()``. El
    ``to_dict()`` no es decorativo: entra al manifiesto de corrida
    (``reproducibilidad.build_manifest``), de modo que una corrida quede
    documentada por las DISTRIBUCIONES que la produjeron y no solo por los
    escalares — que es lo que pide el criterio de aceptación de P1-B.
    """

    def muestrear(self, gen: np.random.Generator) -> float:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @property
    def es_constante(self) -> bool:
        return False


@dataclass(frozen=True)
class Constante(Distribucion):
    """Valor fijo. Sirve para apagar la variación de un parámetro concreto."""

    valor: float

    def muestrear(self, gen: np.random.Generator) -> float:
        return float(self.valor)

    def to_dict(self) -> dict[str, Any]:
        return {"tipo": "constante", "valor": float(self.valor)}

    @property
    def es_constante(self) -> bool:
        return True


@dataclass(frozen=True)
class Normal(Distribucion):
    """Normal(μ, σ). Se puede acotar por abajo para magnitudes físicas.

    ``minimo`` existe porque una potencia o un diámetro negativos no son
    físicos: con σ/μ chico (el caso del paper: 5 % y 0.83 %) el recorte casi
    nunca actúa, pero dejarlo sin acotar permitiría que una cola extrema
    produzca un valor absurdo que el resto del motor propagaría en silencio.
    """

    mu: float
    sigma: float
    minimo: float | None = 0.0

    def muestrear(self, gen: np.random.Generator) -> float:
        v = float(gen.normal(self.mu, self.sigma))
        if self.minimo is not None:
            v = max(self.minimo, v)
        return v

    def to_dict(self) -> dict[str, Any]:
        return {
            "tipo": "normal",
            "mu": float(self.mu),
            "sigma": float(self.sigma),
            "minimo": self.minimo,
        }


@dataclass(frozen=True)
class Uniforme(Distribucion):
    """Uniforme[lo, hi)."""

    lo: float
    hi: float

    def muestrear(self, gen: np.random.Generator) -> float:
        return float(gen.uniform(self.lo, self.hi))

    def to_dict(self) -> dict[str, Any]:
        return {"tipo": "uniforme", "lo": float(self.lo), "hi": float(self.hi)}


@dataclass(frozen=True)
class Rayleigh(Distribucion):
    """Rayleigh(σ). Es la distribución del MÓDULO de un error 2D gaussiano.

    Por eso es la correcta para el error de apuntado: el desapunte tiene dos
    componentes (azimut y elevación) aproximadamente gaussianas e
    independientes, y lo que importa para la atenuación del haz es la magnitud
    del desvío angular total, no su signo. El paper usa ``Rayleigh(σ = 1.0°)``
    (Tabla 2).
    """

    sigma: float

    def muestrear(self, gen: np.random.Generator) -> float:
        return float(gen.rayleigh(self.sigma))

    def to_dict(self) -> dict[str, Any]:
        return {"tipo": "rayleigh", "sigma": float(self.sigma)}


@dataclass(frozen=True)
class NormalRelativa(Distribucion):
    """Normal centrada en ``nominal`` con σ = ``fraccion`` · nominal.

    La forma en la que el paper especifica la incertidumbre de los umbrales por
    subsistema: "Normal(±15 % del nominal)". Se interpreta ese ±15 % como UNA
    desviación estándar, no como un intervalo de confianza — es la lectura
    literal de la notación de la Tabla 2, y queda declarada acá porque la otra
    lectura (±15 % ≈ 2σ) daría la mitad de varianza.
    """

    nominal: float
    fraccion: float = 0.15

    def muestrear(self, gen: np.random.Generator) -> float:
        return max(0.0, float(gen.normal(self.nominal, abs(self.fraccion * self.nominal))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tipo": "normal_relativa",
            "nominal": float(self.nominal),
            "fraccion": float(self.fraccion),
        }


# ═══════════════════════════════════════════════════════════════════════════
# Muestra y especificación
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MuestraParametros:
    """Una realización concreta de los parámetros del modelo."""

    potencia_kw: float
    diametro_plato_m: float
    eficiencia_apertura: float
    error_apuntado_deg: float
    angulo_polarizacion_rad: float
    longitud_cable_m: float
    # Umbrales por subsistema muestreados: {nombre: (E50, sigma_E)}.
    umbrales_subsistemas: dict[str, tuple[float, float]] = field(default_factory=dict)

    @property
    def eta_polarizacion(self) -> float:
        """η_pol = cos²φ, acotado por abajo a ``DRONE_POLARIZATION_MIN_ETA``.

        El piso no es cosmético: con ``φ`` uniforme en [0, π] la densidad de
        ``cos²φ`` diverge en 0, así que sin piso una fracción no despreciable
        de blancos quedaría con acoplamiento numéricamente nulo — un blanco
        perfectamente cruzado en polarización sigue acoplando algo por
        despolarización del entorno y por la geometría 3D real del cableado.
        El paper también lo acota (a 0.1).
        """
        eta = math.cos(self.angulo_polarizacion_rad) ** 2
        return max(config_mod.DRONE_POLARIZATION_MIN_ETA, eta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "potencia_kw": round(self.potencia_kw, 6),
            "diametro_plato_m": round(self.diametro_plato_m, 6),
            "eficiencia_apertura": round(self.eficiencia_apertura, 6),
            "error_apuntado_deg": round(self.error_apuntado_deg, 6),
            "angulo_polarizacion_rad": round(self.angulo_polarizacion_rad, 6),
            "eta_polarizacion": round(self.eta_polarizacion, 6),
            "longitud_cable_m": round(self.longitud_cable_m, 6),
            "umbrales_subsistemas": {
                k: [round(v[0], 4), round(v[1], 4)]
                for k, v in self.umbrales_subsistemas.items()
            },
        }


@dataclass(frozen=True)
class EspecificacionMC:
    """Las ocho distribuciones del Monte Carlo de parámetros.

    Se corresponden una a una con la Tabla 2 de arXiv:2602.08477 (ver
    docs/REFERENCIA_PAPER_2602.08477.md §3).
    """

    potencia_kw: Distribucion
    diametro_plato_m: Distribucion
    eficiencia_apertura: Distribucion
    error_apuntado_deg: Distribucion
    angulo_polarizacion_rad: Distribucion
    longitud_cable_m: Distribucion
    # Un par de distribuciones (E50, σ_E) por subsistema.
    umbrales_subsistemas: dict[str, tuple[Distribucion, Distribucion]] = field(
        default_factory=dict
    )

    # ── Constructores ────────────────────────────────────────────────────

    @classmethod
    def nominal(cls) -> EspecificacionMC:
        """Todo constante en el valor por defecto de ``src/config.py``.

        Un experimento con esta especificación reproduce exactamente el
        comportamiento previo a P1-B. Es el default, para que la variación de
        parámetros sea una decisión explícita y no una sorpresa.
        """
        return cls(
            potencia_kw=Constante(config_mod.HPM_DEFAULT_POWER),
            diametro_plato_m=Constante(config_mod.HPM_DISH_DIAMETER_M),
            eficiencia_apertura=Constante(config_mod.HPM_APERTURE_EFFICIENCY),
            error_apuntado_deg=Constante(0.0),
            # π/2 ⇒ cos² = 0 ⇒ η recortado al piso. Para el caso nominal
            # interesa el acoplamiento ÓPTIMO (φ=0 ⇒ η=1), que es el que
            # corresponde al modelo calibrado sin huella de susceptibilidad.
            angulo_polarizacion_rad=Constante(0.0),
            longitud_cable_m=Constante(
                (config_mod.DRONE_CABLE_LENGTH_MIN_M + config_mod.DRONE_CABLE_LENGTH_MAX_M) / 2
            ),
            umbrales_subsistemas={
                nombre: (Constante(e50), Constante(sigma))
                for nombre, (e50, sigma) in config_mod.HPM_SUBSISTEMAS.items()
            },
        )

    @classmethod
    def del_paper(cls) -> EspecificacionMC:
        """Las ocho distribuciones exactas de la Tabla 2 de arXiv:2602.08477.

        Es la especificación contra la que se valida el modelo: un MC con ésta
        debe reproducir 51.4 % @ 20 m y 13.1 % @ 40 m (Tabla de §7 de la
        referencia) y un CV ≈ 39 % a 30 m.
        """
        return cls(
            # "Normal(μ=25 kW, σ=1.25 kW)" — el σ es el 5 % de μ.
            potencia_kw=Normal(25.0, 1.25),
            diametro_plato_m=Normal(0.60, 0.005),
            eficiencia_apertura=Uniforme(0.50, 0.60),
            error_apuntado_deg=Rayleigh(1.0),
            angulo_polarizacion_rad=Uniforme(0.0, math.pi),
            longitud_cable_m=Uniforme(0.05, 0.25),
            umbrales_subsistemas={
                nombre: (NormalRelativa(e50, 0.15), NormalRelativa(sigma, 0.15))
                for nombre, (e50, sigma) in config_mod.HPM_SUBSISTEMAS.items()
            },
        )

    # ── Muestreo ─────────────────────────────────────────────────────────

    def muestrear(self, gen: np.random.Generator) -> MuestraParametros:
        return MuestraParametros(
            potencia_kw=self.potencia_kw.muestrear(gen),
            diametro_plato_m=self.diametro_plato_m.muestrear(gen),
            eficiencia_apertura=self.eficiencia_apertura.muestrear(gen),
            error_apuntado_deg=self.error_apuntado_deg.muestrear(gen),
            angulo_polarizacion_rad=self.angulo_polarizacion_rad.muestrear(gen),
            longitud_cable_m=self.longitud_cable_m.muestrear(gen),
            umbrales_subsistemas={
                nombre: (d_e50.muestrear(gen), d_sigma.muestrear(gen))
                for nombre, (d_e50, d_sigma) in self.umbrales_subsistemas.items()
            },
        )

    @property
    def todo_constante(self) -> bool:
        """True si ninguna distribución varía — o sea, es el caso nominal."""
        escalares = (
            self.potencia_kw, self.diametro_plato_m, self.eficiencia_apertura,
            self.error_apuntado_deg, self.angulo_polarizacion_rad, self.longitud_cable_m,
        )
        if not all(d.es_constante for d in escalares):
            return False
        return all(
            d_e50.es_constante and d_sigma.es_constante
            for d_e50, d_sigma in self.umbrales_subsistemas.values()
        )

    def to_dict(self) -> dict[str, Any]:
        """Snapshot para el manifiesto de corrida."""
        return {
            "potencia_kw": self.potencia_kw.to_dict(),
            "diametro_plato_m": self.diametro_plato_m.to_dict(),
            "eficiencia_apertura": self.eficiencia_apertura.to_dict(),
            "error_apuntado_deg": self.error_apuntado_deg.to_dict(),
            "angulo_polarizacion_rad": self.angulo_polarizacion_rad.to_dict(),
            "longitud_cable_m": self.longitud_cable_m.to_dict(),
            "umbrales_subsistemas": {
                nombre: {"e50": d_e50.to_dict(), "sigma_e": d_sigma.to_dict()}
                for nombre, (d_e50, d_sigma) in self.umbrales_subsistemas.items()
            },
            "todo_constante": self.todo_constante,
        }
