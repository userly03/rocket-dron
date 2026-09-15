"""Genera la casa rural atacable (ver src/models/structure.py —
Estructura, salud propia, 4 en el layout por defecto) y la exporta a
.glb.

CÓMO CORRERLO
-------------
1. Blender → pestaña "Scripting" → "Open" → elegís este archivo.
2. "Run Script" (▶, o Alt+P con el cursor en el editor).
3. Queda en frontend/models/edificio.glb.

DISEÑO
------
Casa rural chica y humilde a propósito (paredes claras, techo oscuro,
sin lujo) — coincide con el estilo de referencia visual acordado
(pueblo rural disperso, no un edificio militar/industrial). Techo a dos
aguas de VERDAD (dos paneles inclinados que se encuentran en una
cumbrera), no una caja con textura de techo — la geometría real
importa para que se vea como casa y no como galpón desde cualquier
ángulo de cámara.

La "salud" de la Estructura no cambia el modelo en sí (eso es un
problema de Three.js — tintar/oscurecer con el daño, o directamente
cambiar de modelo a uno de escombros cuando `destruida=true` — no de
Blender). Este script genera la casa INTACTA únicamente.
"""

import math
import os

import bpy

RUTA_SALIDA = "/home/fennec/Documentos/simulador-ew/frontend/models/edificio.glb"

# --- Dimensiones reales, en metros ---
LARGO_CASA = 6.0
ANCHO_CASA = 5.0
ALTO_PARED = 2.6
OVERHANG_LATERAL = 0.4
OVERHANG_EXTREMO = 0.4
ALTURA_CUMBRERA = 1.6
ESPESOR_TECHO = 0.12
RADIO_CHIMENEA = 0.22
ALTO_CHIMENEA = 0.9

BISEL_ANCHO = 0.02
BISEL_SEGMENTOS = 2


def limpiar_escena():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def crear_material(nombre, color_rgba, rugosidad=0.75, metalico=0.0):
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

    mat_pared = crear_material("Pared", (0.75, 0.70, 0.60, 1.0), rugosidad=0.9)
    mat_techo = crear_material("Techo", (0.20, 0.16, 0.14, 1.0), rugosidad=0.7)
    mat_madera = crear_material("Madera", (0.30, 0.20, 0.12, 1.0), rugosidad=0.8)
    mat_oscuro = crear_material("Hueco", (0.04, 0.04, 0.05, 1.0), rugosidad=0.5)

    # --- Paredes ---
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, ALTO_PARED / 2))
    casa = bpy.context.active_object
    casa.name = "Edificio"
    casa.scale = (LARGO_CASA, ANCHO_CASA, ALTO_PARED)
    casa.data.materials.append(mat_pared)
    aplicar_escala(casa)
    agregar_bisel(casa, ancho=0.015)

    # --- Techo a dos aguas: dos paneles inclinados que se encuentran en
    # la cumbrera (y=0). Geometría derivada a mano (no "a ojo"):
    # cada panel es una caja centrada en el punto MEDIO entre la
    # cumbrera y el alero, con el ancho real = hipotenusa (no el ancho
    # horizontal), rotada alrededor de X el ángulo real de la pendiente
    # — ver el comentario en docs/SEGUIMIENTO_SESION.md con la derivación
    # completa si hace falta tocar esto. ---
    medio_span = ANCHO_CASA / 2 + OVERHANG_LATERAL
    largo_hipotenusa = math.hypot(medio_span, ALTURA_CUMBRERA)
    angulo = math.atan2(ALTURA_CUMBRERA, medio_span)
    cumbrera_z = ALTO_PARED + ALTURA_CUMBRERA
    alero_z = ALTO_PARED
    medio_z = (cumbrera_z + alero_z) / 2
    largo_techo = LARGO_CASA + 2 * OVERHANG_EXTREMO

    for lado, signo in [("Izquierdo", 1), ("Derecho", -1)]:
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(0, signo * medio_span / 2, medio_z)
        )
        panel = bpy.context.active_object
        panel.name = f"Techo_{lado}"
        panel.scale = (largo_techo, largo_hipotenusa, ESPESOR_TECHO)
        panel.rotation_euler = (-signo * angulo, 0, 0)
        panel.data.materials.append(mat_techo)
        aplicar_escala(panel)
        agregar_bisel(panel, ancho=0.015)
        parentar(panel, casa)

    # --- Chimenea: sale del faldón izquierdo, cerca de un extremo ---
    x_chimenea = LARGO_CASA * 0.3
    y_chimenea = medio_span * 0.35
    # Altura del techo en ese punto (interpolación lineal alero->cumbrera)
    t = y_chimenea / medio_span
    z_techo_ahi = alero_z + (cumbrera_z - alero_z) * (1 - t)
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(x_chimenea, y_chimenea, z_techo_ahi + ALTO_CHIMENEA / 2)
    )
    chimenea = bpy.context.active_object
    chimenea.name = "Chimenea"
    chimenea.scale = (RADIO_CHIMENEA * 2, RADIO_CHIMENEA * 2, ALTO_CHIMENEA)
    chimenea.data.materials.append(mat_pared)
    aplicar_escala(chimenea)
    agregar_bisel(chimenea, ancho=0.02)
    parentar(chimenea, casa)

    # --- Puerta (pared +X) ---
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(LARGO_CASA / 2 + 0.02, -ANCHO_CASA * 0.2, 1.0)
    )
    puerta = bpy.context.active_object
    puerta.name = "Puerta"
    puerta.scale = (0.06, 0.9, 2.0)
    puerta.data.materials.append(mat_madera)
    aplicar_escala(puerta)
    parentar(puerta, casa)

    # --- Ventanas (paredes ±Y) ---
    for lado, signo in [("Izquierda", 1), ("Derecha", -1)]:
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(-LARGO_CASA * 0.15, signo * (ANCHO_CASA / 2 + 0.02), 1.5)
        )
        ventana = bpy.context.active_object
        ventana.name = f"Ventana_{lado}"
        ventana.scale = (0.9, 0.06, 0.8)
        ventana.data.materials.append(mat_oscuro)
        aplicar_escala(ventana)
        parentar(ventana, casa)

    os.makedirs(os.path.dirname(RUTA_SALIDA), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=RUTA_SALIDA,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )
    print(f"Edificio exportado a: {RUTA_SALIDA}")


main()
