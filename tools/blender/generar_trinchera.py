"""Genera un segmento de trinchera (parapetos de sacos de arena + piso
removido) y lo exporta a .glb.

CÓMO CORRERLO
-------------
1. Blender → pestaña "Scripting" → "Open" → elegís este archivo.
2. "Run Script" (▶, o Alt+P con el cursor en el editor).
3. Queda en frontend/models/trinchera.glb.

DISEÑO — por qué es así
--------------------------
El suelo del mapa 3D (frontend/js/render3d.js, buildGround) es un plano
liso, sin relieve — no hay terreno "cavado" de verdad en la escena.
Modelar una zanja real (una hendidura por debajo del nivel 0) no se
vería contra un piso plano sin ADEMÁS deformar el terreno, que es un
cambio de alcance mayor (relieve real del mapa) no pedido todavía.

Por eso esto representa la trinchera como se vería en la práctica de
todos modos: dos parapetos de sacos de arena apilados, con una franja de
tierra removida (más oscura, al nivel del piso) entre medio — es lo que
un jugador mirando desde arriba/costado realmente percibe como
"trinchera", sin necesitar cavar el mesh del suelo.

Puramente decorativo por ahora (no está conectado a ninguna física —
línea de vista/cobertura del vehículo es un ítem futuro, no parte de
esta fase), a diferencia del vehículo/dron/edificio.

Cada saco es una caja individual con tamaño/posición con algo de
variación al azar — una fila de cajas idénticas se lee como "una sola
pieza repetida", sacos con variación se leen como apilados a mano.
"""

import os
import random

import bpy

RUTA_SALIDA = "/home/fennec/Documentos/simulador-ew/frontend/models/trinchera.glb"

# --- Dimensiones reales, en metros ---
LARGO_TRINCHERA = 12.0
ANCHO_ZANJA = 1.6  # separación entre los dos parapetos (el "pasillo")
LARGO_SACO = 0.5
ANCHO_SACO = 0.32
ALTO_SACO = 0.22
FILAS_SACOS = 2  # apilados en altura

BISEL_ANCHO = 0.025
BISEL_SEGMENTOS = 2


def limpiar_escena():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def crear_material(nombre, color_rgba, rugosidad=0.85, metalico=0.0):
    """Busca el nodo Principled BSDF por TIPO y sus entradas por
    IDENTIFIER, nunca por nombre visible — ver generar_lanzador_hpm.py
    para el bug real que esto evita con Blender en español."""
    mat = bpy.data.materials.new(name=nombre)
    mat.use_nodes = True
    principled = next(
        (n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None
    )
    if principled is None:
        raise RuntimeError(f"No se encontró el nodo Principled BSDF en '{nombre}'")

    def set_input(identificador, valor):
        for inp in principled.inputs:
            if inp.identifier == identificador:
                inp.default_value = valor
                return
        raise RuntimeError(f"No se encontró la entrada '{identificador}' en '{nombre}'")

    set_input("Base Color", color_rgba)
    set_input("Roughness", rugosidad)
    set_input("Metallic", metalico)
    return mat


def aplicar_escala(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def parentar(hijo, padre):
    bpy.ops.object.select_all(action="DESELECT")
    hijo.select_set(True)
    padre.select_set(True)
    bpy.context.view_layer.objects.active = padre
    bpy.ops.object.parent_set(type="OBJECT", keep_transform=True)


def agregar_bisel(obj, ancho=BISEL_ANCHO, segmentos=BISEL_SEGMENTOS):
    mod = obj.modifiers.new(name="Bisel", type="BEVEL")
    mod.width = ancho
    mod.segments = segmentos
    mod.limit_method = "ANGLE"


def main():
    limpiar_escena()
    rng = random.Random(2026)

    mat_saco = crear_material("Saco", (0.42, 0.36, 0.24, 1.0), rugosidad=0.9)
    mat_tierra = crear_material("TierraRemovida", (0.14, 0.10, 0.07, 1.0), rugosidad=1.0)

    # --- Franja de tierra removida — un plano fino a nivel del piso,
    # más oscuro que el pasto/tierra del mapa, entre los dos parapetos. ---
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(0, 0, 0.02)
    )
    trinchera = bpy.context.active_object
    trinchera.name = "Trinchera"
    trinchera.scale = (LARGO_TRINCHERA, ANCHO_ZANJA, 0.04)
    trinchera.data.materials.append(mat_tierra)
    aplicar_escala(trinchera)

    # --- Dos parapetos de sacos, uno a cada lado del pasillo ---
    n_sacos_por_fila = max(2, int(LARGO_TRINCHERA / LARGO_SACO))
    paso = LARGO_TRINCHERA / n_sacos_por_fila
    x0 = -LARGO_TRINCHERA / 2 + paso / 2

    for lado, signo in [("Izquierdo", 1), ("Derecho", -1)]:
        y_pared = signo * (ANCHO_ZANJA / 2 + ANCHO_SACO / 2)
        for fila in range(FILAS_SACOS):
            z_saco = 0.02 + ALTO_SACO * (fila + 0.5)
            # Cada fila se desplaza medio saco (aparejado, como una
            # pared de ladrillos) — más creíble que columnas alineadas.
            offset_fila = (paso / 2) if fila % 2 == 1 else 0.0
            for i in range(n_sacos_por_fila):
                x_saco = x0 + i * paso + offset_fila
                if x_saco > LARGO_TRINCHERA / 2 - LARGO_SACO / 4:
                    continue
                # Variación al azar en tamaño/posición — sacos apilados
                # a mano, no una fila de clones perfectos.
                jitter_x = rng.uniform(-0.03, 0.03)
                jitter_y = rng.uniform(-0.02, 0.02)
                jitter_z = rng.uniform(-0.01, 0.01)
                escala_variacion = rng.uniform(0.9, 1.08)

                bpy.ops.mesh.primitive_cube_add(
                    size=1,
                    location=(x_saco + jitter_x, y_pared + jitter_y, z_saco + jitter_z),
                )
                saco = bpy.context.active_object
                saco.name = f"Saco_{lado}_{fila}_{i}"
                saco.rotation_euler = (0, 0, rng.uniform(-0.06, 0.06))
                saco.scale = (
                    LARGO_SACO * escala_variacion,
                    ANCHO_SACO * escala_variacion,
                    ALTO_SACO * escala_variacion,
                )
                saco.data.materials.append(mat_saco)
                aplicar_escala(saco)
                agregar_bisel(saco, ancho=0.035, segmentos=2)
                parentar(saco, trinchera)

    os.makedirs(os.path.dirname(RUTA_SALIDA), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=RUTA_SALIDA,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )
    print(f"Trinchera exportada a: {RUTA_SALIDA}")


main()
