"""Genera 3 variantes de árbol (bajo/mediano/alto, con algo de
variación real, no clones) y las exporta a un solo .glb — el frontend
elige una al azar por cada posición de árbol en el mapa, para que una
línea de árboles no se vea como el mismo objeto repetido.

CÓMO CORRERLO
-------------
1. Blender → pestaña "Scripting" → "Open" → elegís este archivo.
2. "Run Script" (▶, o Alt+P con el cursor en el editor).
3. Queda en frontend/models/arboles.glb.

DISEÑO
------
Low-poly a propósito, mismo criterio que vehículo/dron: tronco
(cilindro, más angosto arriba) + follaje como un racimo de 2-3
icoesferas de pocas subdivisiones (esa "cara plana" es la estética
low-poly, no un descuido — una esfera lisa se vería genérica, las caras
visibles dan la sensación de "hoja/copa" sin modelar hojas individuales).

Sin material "dañable" — a diferencia del vehículo/dron, un árbol no
tiene estado que cambie durante la simulación, así que los colores son
fijos, no pensados para que Three.js los tiña.
"""

import math
import random

import bpy

RUTA_SALIDA = "/home/fennec/Documentos/simulador-ew/frontend/models/arboles.glb"

BISEL_ANCHO = 0.03
BISEL_SEGMENTOS = 2

# Tres variantes: (nombre, altura_tronco, radio_base_tronco, radio_follaje, n_esferas_follaje)
VARIANTES = [
    ("Arbol_0", 3.2, 0.22, 1.6, 2),
    ("Arbol_1", 4.5, 0.28, 2.1, 3),
    ("Arbol_2", 5.6, 0.32, 2.5, 3),
]


def limpiar_escena():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def crear_material(nombre, color_rgba, rugosidad=0.75, metalico=0.0):
    """Busca el nodo Principled BSDF por TIPO y sus entradas por
    IDENTIFIER, nunca por nombre visible — con Blender en español el
    nombre que se MUESTRA puede estar traducido y una búsqueda por
    nombre en inglés falla en silencio (bug real encontrado la primera
    vez, ver generar_lanzador_hpm.py)."""
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


def crear_arbol(nombre, altura_tronco, radio_base, radio_follaje, n_esferas, rng, mat_tronco, mats_follaje):
    # --- Tronco: cono truncado (más angosto arriba) ---
    bpy.ops.mesh.primitive_cone_add(
        radius1=radio_base, radius2=radio_base * 0.6, depth=altura_tronco,
        location=(0, 0, altura_tronco / 2), vertices=8,
    )
    tronco = bpy.context.active_object
    tronco.name = nombre
    tronco.data.materials.append(mat_tronco)
    agregar_bisel(tronco, ancho=0.03, segmentos=1)

    # --- Follaje: 2-3 icoesferas superpuestas, centradas arriba del
    # tronco, con offsets al azar para que no se vea perfectamente
    # simétrico (un árbol real no lo es). ---
    centro_z = altura_tronco + radio_follaje * 0.5
    for i in range(n_esferas):
        offset_x = rng.uniform(-radio_follaje * 0.3, radio_follaje * 0.3) if i > 0 else 0
        offset_y = rng.uniform(-radio_follaje * 0.3, radio_follaje * 0.3) if i > 0 else 0
        offset_z = rng.uniform(-radio_follaje * 0.15, radio_follaje * 0.25)
        radio_i = radio_follaje * rng.uniform(0.75, 1.0)
        bpy.ops.mesh.primitive_ico_sphere_add(
            radius=radio_i, subdivisions=1,
            location=(offset_x, offset_y, centro_z + offset_z),
        )
        esfera = bpy.context.active_object
        esfera.name = f"{nombre}_Follaje_{i}"
        esfera.data.materials.append(mats_follaje[i % len(mats_follaje)])
        parentar(esfera, tronco)

    aplicar_escala(tronco)
    return tronco


def main():
    limpiar_escena()
    rng = random.Random(2026)

    mat_tronco = crear_material("Tronco", (0.22, 0.15, 0.10, 1.0), rugosidad=0.85)
    # Dos tonos de follaje (no uno solo) para que el racimo de esferas
    # no se lea como una sola forma uniforme — variación barata.
    mats_follaje = [
        crear_material("Follaje1", (0.16, 0.28, 0.12, 1.0), rugosidad=0.8),
        crear_material("Follaje2", (0.20, 0.33, 0.15, 1.0), rugosidad=0.8),
    ]

    for nombre, altura, radio_base, radio_follaje, n_esferas in VARIANTES:
        crear_arbol(nombre, altura, radio_base, radio_follaje, n_esferas, rng, mat_tronco, mats_follaje)

    import os
    os.makedirs(os.path.dirname(RUTA_SALIDA), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=RUTA_SALIDA,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )
    print(f"Árboles exportados a: {RUTA_SALIDA}")


main()
