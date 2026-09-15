"""Genera el modelo del dron del enjambre y lo exporta a .glb para
cargarlo en el mapa 3D del frontend (Three.js), reemplazando el cono
genérico actual (ver ``makeDroneGeometry`` en render3d.js).

CÓMO CORRERLO
-------------
1. Blender → pestaña "Scripting" → "Open" → elegís este archivo.
2. "Run Script" (▶, o Alt+P con el cursor en el editor).
3. Queda en frontend/models/dron.glb.

DISEÑO — por qué es así
--------------------------
El enjambre que modela este proyecto son **drones FPV baratos**, no UAVs
militares (ver docs/PROYECTO_Y_CAPACIDADES.md: "drones FPV baratos sobre
el VRAEM, no cazas rusos" — es el escenario de amenaza real que el
simulador está calibrando). Eso descarta un diseño prolijo/caro: acá va
un cuadricóptero simple tipo carrera/FPV — marco en X expuesto, cámara
angulada hacia abajo (vuelo "buzo" típico FPV), antena de video, sin
carenado ni acabado de fábrica. Es justo lo que hace que el problema del
proyecto sea difícil: son baratos, chicos y hay muchos, no una amenaza
sofisticada.

COLOR — cómo se integra con el estado del dron
--------------------------------------------------
El simulador pinta cada dron según su ESTADO (activo=verde, dañado,
neutralizado, etc. — ver la leyenda del mapa), no por diseño real. Para
que eso siga funcionando con un modelo de verdad, el material del CUERPO
("Cuerpo", brazos incluidos) queda en un gris neutro pensado para que
Three.js lo tiña por estado (mismo criterio que ya usa el cono actual).
Hélices, motores, cámara y antena quedan en materiales FIJOS oscuros —
esas piezas no deberían cambiar de color con el estado, sería ilegible.

JERARQUÍA (pensada para animar hélices más adelante)
---------------------------------------------------------
Cuerpo
 ├─ Camara (angulada hacia abajo/adelante)
 ├─ Antena
 ├─ Brazo_0/1/2/3 (en X)
 └─ Motor_0/1/2/3
     └─ Helice_0/1/2/3  ← nodo a rotar si en algún momento se anima el giro
"""

import math
import os

import bpy

RUTA_SALIDA = "/home/fennec/Documentos/simulador-ew/frontend/models/dron.glb"

# --- Dimensiones, en metros de ESCENA (no reales — el placeholder actual
# ya es un cono exagerado de radio 4 / altura 12 para que se vea a la
# distancia de combate; este modelo apunta a esa misma escala, no al
# tamaño real de un FPV de carreras, que sería ridículamente chico acá). ---
LARGO_CUERPO = 3.2
ANCHO_CUERPO = 2.0
ALTO_CUERPO = 1.1
ENVERGADURA = 11.0  # punta a punta de brazos opuestos, en diagonal
RADIO_BRAZO = 0.16
RADIO_MOTOR = 0.35
ALTO_MOTOR = 0.6
RADIO_HELICE = 2.6
GROSOR_HELICE = 0.08
RADIO_CAMARA = 0.62
LARGO_ANTENA = 1.8

BISEL_ANCHO = 0.03
BISEL_SEGMENTOS = 2


def limpiar_escena():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def crear_material(nombre, color_rgba, rugosidad=0.6, metalico=0.0):
    """Busca el nodo Principled BSDF por TIPO y sus entradas por
    IDENTIFIER, nunca por nombre visible — con Blender en español el
    nombre que se MUESTRA puede estar traducido y una búsqueda por
    nombre en inglés falla en silencio (ver el mismo comentario, más
    largo, en generar_lanzador_hpm.py — ahí se encontró este bug la
    primera vez)."""
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

    # "Cuerpo" queda gris neutro A PROPÓSITO — Three.js lo tiñe según el
    # estado del dron (activo/dañado/neutralizado/...), no es el color
    # final. Las demás piezas son fijas, no se tiñen nunca.
    mat_cuerpo = crear_material("Cuerpo", (0.55, 0.56, 0.57, 1.0), rugosidad=0.55)
    mat_oscuro = crear_material("Oscuro", (0.05, 0.05, 0.06, 1.0), rugosidad=0.4)
    mat_helice = crear_material("Helice", (0.08, 0.08, 0.09, 1.0), rugosidad=0.3, metalico=0.1)
    mat_lente = crear_material("Lente", (0.02, 0.02, 0.03, 1.0), rugosidad=0.1, metalico=0.6)

    # --- Cuerpo central ---
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    cuerpo = bpy.context.active_object
    cuerpo.name = "Cuerpo"
    cuerpo.scale = (LARGO_CUERPO, ANCHO_CUERPO, ALTO_CUERPO)
    cuerpo.data.materials.append(mat_cuerpo)
    aplicar_escala(cuerpo)
    agregar_bisel(cuerpo)

    # --- Cámara FPV: angulada hacia abajo/adelante (vuelo "buzo" típico
    # de carreras FPV, no vuelo nivelado tipo dron de fotografía) ---
    bpy.ops.mesh.primitive_cylinder_add(
        radius=RADIO_CAMARA, depth=0.5,
        location=(LARGO_CUERPO / 2 + 0.15, 0, -0.2),
    )
    camara = bpy.context.active_object
    camara.name = "Camara"
    camara.rotation_euler = (0, math.radians(70), 0)
    camara.data.materials.append(mat_lente)
    agregar_bisel(camara, ancho=0.04, segmentos=2)
    parentar(camara, cuerpo)

    # --- Antena de video (varilla flexible hacia atrás/arriba) ---
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.04, depth=LARGO_ANTENA,
        location=(-LARGO_CUERPO / 2 - 0.1, 0.2, 0.5),
    )
    antena = bpy.context.active_object
    antena.name = "Antena"
    antena.rotation_euler = (math.radians(20), math.radians(25), 0)
    antena.data.materials.append(mat_oscuro)
    parentar(antena, cuerpo)

    # --- Brazos en X + motor + hélice en cada punta ---
    radio_brazo_horizontal = ENVERGADURA / 2
    for i in range(4):
        angulo = math.radians(45 + i * 90)  # X-config: 45°,135°,225°,315°
        dx = radio_brazo_horizontal * math.cos(angulo)
        dy = radio_brazo_horizontal * math.sin(angulo)

        # Brazo: cilindro por defecto con eje Z; lo acostamos con Y=90°
        # y lo giramos en Z al ángulo del brazo para que apunte a la
        # punta correspondiente.
        bpy.ops.mesh.primitive_cylinder_add(
            radius=RADIO_BRAZO, depth=radio_brazo_horizontal,
            location=(dx / 2, dy / 2, 0),
        )
        brazo = bpy.context.active_object
        brazo.rotation_euler = (0, math.radians(90), angulo)
        brazo.name = f"Brazo_{i}"
        brazo.data.materials.append(mat_oscuro)
        agregar_bisel(brazo, ancho=0.02)
        parentar(brazo, cuerpo)

        bpy.ops.mesh.primitive_cylinder_add(
            radius=RADIO_MOTOR, depth=ALTO_MOTOR, location=(dx, dy, ALTO_MOTOR / 2)
        )
        motor = bpy.context.active_object
        motor.name = f"Motor_{i}"
        motor.data.materials.append(mat_oscuro)
        agregar_bisel(motor, ancho=0.03)
        parentar(motor, cuerpo)

        # Hélice: dos aspas finas cruzadas — técnica barata, no una pala
        # real, pero se lee como hélice a la distancia de este mapa.
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(dx, dy, ALTO_MOTOR + 0.06)
        )
        aspa1 = bpy.context.active_object
        aspa1.name = f"Aspa_{i}_a"
        aspa1.scale = (RADIO_HELICE, RADIO_HELICE * 0.12, GROSOR_HELICE)
        aspa1.data.materials.append(mat_helice)
        aplicar_escala(aspa1)
        agregar_bisel(aspa1, ancho=0.02, segmentos=1)

        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(dx, dy, ALTO_MOTOR + 0.06)
        )
        aspa2 = bpy.context.active_object
        aspa2.name = f"Aspa_{i}_b"
        aspa2.rotation_euler = (0, 0, math.radians(90))
        aspa2.scale = (RADIO_HELICE, RADIO_HELICE * 0.12, GROSOR_HELICE)
        aspa2.data.materials.append(mat_helice)
        aplicar_escala(aspa2)
        agregar_bisel(aspa2, ancho=0.02, segmentos=1)

        # Las dos aspas se agrupan en un Empty para que "Helice_i" sea
        # UN solo nodo (más fácil de rotar en Three.js si algún día se
        # anima el giro) en vez de dos objetos sueltos con el mismo rol.
        helice = bpy.data.objects.new(f"Helice_{i}", None)
        bpy.context.collection.objects.link(helice)
        helice.location = (dx, dy, ALTO_MOTOR + 0.06)
        parentar(aspa1, helice)
        parentar(aspa2, helice)
        parentar(helice, motor)

    # --- Exportar ---
    os.makedirs(os.path.dirname(RUTA_SALIDA), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=RUTA_SALIDA,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )
    print(f"Dron exportado a: {RUTA_SALIDA}")


main()
