"""Pruebas de la huella de susceptibilidad aplicada al jammer.

Deuda técnica cerrada (ver CHECKLIST_MEJORAS.md): el jammer era la única arma
inmune a la huella de susceptibilidad de P2-04 (`_en_zona_de_efecto` usaba
`campo_e_v_m` sin pasar `cable_length_m`/`polarization`).

Decisión de modelado, no descuido: solo el mismatch de POLARIZACIÓN aplica al
enlace de control. La resonancia de cableado (`frequency_coupling`) modela el
acoplamiento incidental a un arnés interno no apantallado que no fue diseñado
como antena — el enlace de control, en cambio, sí tiene una antena receptora
deliberada, sintonizada a su propia banda, y no está sujeta al mismo desajuste
de resonancia aleatorio que un cable de alimentación cualquiera.
"""

import pytest

from src.engine.hpm_engine import susceptibility_coupling_factor
from src.models.drone import Drone
from src.models.jammer import Jammer


class TestPolarizacionAfectaAlJammer:
    """El mismatch de polarización SÍ debe cambiar la decisión de interferencia."""

    def _jammer(self, rango_m: float) -> Jammer:
        j = Jammer()
        j.iniciar(direccion=0, potencia=50, apertura_cono=45)
        j.origen_x = j.origen_y = j.origen_z = 0.0
        return j

    def test_polarizacion_optima_interfiere_donde_la_mala_no(self):
        """A r=700 m: pol=1.0 SÍ entra en zona de efecto, pol=0.3 NO.

        Frontera verificada numéricamente contra el cálculo directo del
        campo (ver scratchpad de la sesión): a 700 m con potencia=50,
        apertura=45°, p(pol=1.0)=0.796 ≥ 0.5 pero p(pol=0.3)=0.416 < 0.5.
        """
        j = self._jammer(700.0)
        d_optimo = Drone(0, x=700.0, y=0.0, z=0.0, polarization=1.0, cable_length_m=0.1)
        d_malo = Drone(1, x=700.0, y=0.0, z=0.0, polarization=0.3, cable_length_m=0.1)

        assert j._en_zona_de_efecto(d_optimo) is True
        assert j._en_zona_de_efecto(d_malo) is False

    def test_a_distancia_media_ambos_interfieren(self):
        """A rango corto la polarización no importa: sobra margen para ambos."""
        j = self._jammer(100.0)
        d_optimo = Drone(0, x=100.0, y=0.0, z=0.0, polarization=1.0, cable_length_m=0.1)
        d_malo = Drone(1, x=100.0, y=0.0, z=0.0, polarization=0.3, cable_length_m=0.1)

        assert j._en_zona_de_efecto(d_optimo) is True
        assert j._en_zona_de_efecto(d_malo) is True


class TestResonanciaDeCableadoNoAfectaAlJammer:
    """Decisión deliberada: el jammer es inmune a la resonancia de cableado."""

    def test_longitud_de_cable_no_cambia_la_decision(self):
        """Dos drones con la MISMA polarización pero cableado muy distinto
        deben dar exactamente la misma decisión — la resonancia de cableado
        no entra a la cadena del jammer.
        """
        j = Jammer()
        j.iniciar(direccion=0, potencia=50, apertura_cono=45)
        j.origen_x = j.origen_y = j.origen_z = 0.0

        # Cables muy distintos (uno resonante a 2.45 GHz, otro muy desafinado).
        d_resonante = Drone(0, x=700.0, y=0.0, z=0.0, polarization=0.6, cable_length_m=0.0612)
        d_desafinado = Drone(1, x=700.0, y=0.0, z=0.0, polarization=0.6, cable_length_m=0.02)

        assert j._en_zona_de_efecto(d_resonante) == j._en_zona_de_efecto(d_desafinado)

    def test_susceptibility_coupling_factor_con_cable_none_ignora_resonancia(self):
        """Contraste directo: con cable_length_m=None el factor es √pol puro
        (equivalente a asumir acoplamiento óptimo η=1), sin importar qué tan
        DESAFINADO estaría el cable si se pasara.

        `cable_length_m=None` no es "cable ausente", es "no se evalúa
        resonancia" — por eso el control negativo correcto es un cable
        DESAFINADO (η<1), que debe dar un factor MENOR que omitir el cable
        (que implícitamente asume η=1, el mejor caso).
        """
        sin_cable = susceptibility_coupling_factor(cable_length_m=None, polarization=0.5)
        assert sin_cable == 0.5**0.5

        # Cable muy corto: muy lejos de la resonancia de media onda a
        # 2.45 GHz (λ/2 ≈ 6.12 cm) — η << 1, factor mucho menor.
        con_cable_desafinado = susceptibility_coupling_factor(
            cable_length_m=0.01, polarization=0.5
        )
        assert con_cable_desafinado < sin_cable

        # Cable a la longitud EXACTA de resonancia: η=1, así que pasar el
        # cable_length_m explícito da lo MISMO que omitirlo (confirma que
        # None es matemáticamente "el mejor caso", no un valor arbitrario).
        l_resonante = 299792458.0 / (2 * 2.45e9)
        con_cable_resonante = susceptibility_coupling_factor(
            cable_length_m=l_resonante, polarization=0.5
        )
        assert con_cable_resonante == pytest.approx(sin_cable, abs=1e-9)
