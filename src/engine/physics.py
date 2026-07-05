"""Cálculos de física: movimiento y colisiones."""

from __future__ import annotations

import numpy as np

from src.utils.helpers import degrees_to_radians


def update_position(
    x: float,
    y: float,
    velocidad: float,
    angulo: float,
    dt: float,
) -> tuple[float, float]:
    """Calcula nueva posición a partir de velocidad y ángulo."""
    rad = degrees_to_radians(angulo)
    dx = velocidad * np.cos(rad) * dt
    dy = velocidad * np.sin(rad) * dt
    return float(x + dx), float(y + dy)


def check_boundary_collision(
    x: float,
    y: float,
    width: float,
    height: float,
    margin: float = 0.0,
) -> tuple[float, float, bool, bool]:
    """
    Refleja posición dentro de los límites del campo.

    Returns:
        Tupla (x, y, colisionó_eje_x, colisionó_eje_y).
    """
    new_x, new_y = x, y
    collided_x = False
    collided_y = False

    if new_x < margin:
        new_x = margin
        collided_x = True
    elif new_x > width - margin:
        new_x = width - margin
        collided_x = True

    if new_y < margin:
        new_y = margin
        collided_y = True
    elif new_y > height - margin:
        new_y = height - margin
        collided_y = True

    return new_x, new_y, collided_x, collided_y


def reflect_angle(angulo: float, hit_vertical: bool, hit_horizontal: bool) -> float:
    """Invierte componentes de dirección tras colisión con borde."""
    new_angle = angulo
    if hit_vertical:
        new_angle = (180 - new_angle) % 360
    if hit_horizontal:
        new_angle = (360 - new_angle) % 360
    return float(new_angle)
