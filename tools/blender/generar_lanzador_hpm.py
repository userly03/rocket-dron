"""Genera el vehículo lanzador (cañón HPM + misil, comparten el mismo
emplazamiento — ver HPM_ORIGIN_X/Y/Z en src/config.py) y lo exporta a
.glb para cargarlo en el mapa 3D del frontend (Three.js) con GLTFLoader.

CÓMO CORRERLO
-------------
1. Blender → pestaña "Scripting".
2. "Open" y elegís este archivo (mejor que pegarlo a mano).
3. "Run Script" (▶, o Alt+P con el cursor en el editor).
4. Queda en frontend/models/lanzador_hpm.glb.

DISEÑO — por qué tiene estas piezas y no otras
------------------------------------------------
No es un tanque de combate: es una plataforma de guerra electrónica, así
que cada pieza corresponde a algo que el motor de simulación YA calcula,
no es decoración:

- Chasis rastreado: mismo criterio que sistemas reales de defensa aérea
  de corto alcance montados sobre oruga (Pantsir, Tunguska) — necesita
  moverse con las unidades que protege, no es un emplazamiento fijo de
  torre.
- DOS mástiles, no uno, y es a propósito:
    * "Torreta_HPM" (el emisor) ROTA — mismos `direccion`/`apertura_cono`
      que ya movés en el panel "CAÑÓN HPM" del frontend.
    * "MastilRadar" NO rota — el radar de este proyecto (P2-G) revisita
      TODO el enjambre a la vez, no es un haz direccional, así que no
      tiene sentido que gire con el cañón. Físicamente son dos
      subsistemas independientes y el modelo lo muestra.
- Módulo de generador/refrigeración en la parte trasera: el cañón HPM ya
  modela `temperatura_c` y `energia_maxima_kj` (ver src/config.py) — un
  HPM real disipa mucha energía como calor, necesita ese bulto de
  equipo, no es relleno visual.
- El emisor es un panel PLANO, no una antena parabólica — un HPM real
  suele ser un array en fase (phased array), no un disco.
- Franja naranja en la base del emisor: mismo `--accent-orange` que ya
  usa el resto de la interfaz para "energía HPM" (frontend/css/style.css)
  — coherencia visual con la app, no un color elegido al azar.

JERARQUÍA (pensada para animarse en Three.js)
------------------------------------------------
Chasis
 ├─ Oruga_Izquierda / Oruga_Derecha, Rueda_* (decorativas)
 ├─ Escotilla, FaroIzquierdo/Derecho, Escape, Generador (detalle, decorativas)
 ├─ MastilRadar (fijo)
 │   └─ DiscoRadar
 ├─ LanzadorMisil  ← rotar este nodo según la dirección del MISIL
 │   └─ TuboMisil_0/1/2
 └─ Torreta_HPM  ← rotar este nodo según la dirección del CAÑÓN
     ├─ Mastil
     ├─ EmisorHPM (el panel/array)
     └─ FranjaEmisor (el aro naranja decorativo)

Nota: LanzadorMisil y Torreta_HPM son DOS nodos que giran cada uno por
su cuenta — en el simulador son dos armas independientes (cañón HPM y
misil HPM) que solo comparten el vehículo, no la dirección de disparo.
"""

import math
import os

import bpy

RUTA_SALIDA = "/home/fennec/Documentos/simulador-ew/frontend/models/lanzador_hpm.glb"

# --- Dimensiones reales, en metros. El tamaño final en el mapa se ajusta
# al cargarlo en Three.js (un multiplicador de escala), no achicando o
# agrandando el modelo acá. ---
LARGO_CHASIS = 6.5
ANCHO_CHASIS = 3.2
ALTO_CHASIS = 1.6
RADIO_ORUGA = 0.5
RADIO_RUEDA = 0.55
N_RUEDAS_POR_LADO = 5
LARGO_TORRETA = 2.0
ANCHO_TORRETA = 1.8
ALTO_TORRETA = 1.0
OFFSET_X_TORRETA = 0.5
RADIO_MASTIL = 0.12
ALTO_MASTIL = 2.5
LARGO_EMISOR = 1.7
ALTO_EMISOR = 1.7
ESPESOR_EMISOR = 0.15
ALTO_MASTIL_RADAR = 2.0
RADIO_DISCO_RADAR = 0.45
RADIO_TUBO_MISIL = 0.13
LARGO_TUBO_MISIL = 1.9
ANGULO_ELEVACION_MISIL = math.radians(18)

BISEL_ANCHO = 0.045
BISEL_SEGMENTOS = 3


def limpiar_escena():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def crear_material(nombre, color_rgba, rugosidad=0.6, metalico=0.0):
    """Busca el nodo Principled BSDF por TIPO (``node.type``) y sus
    entradas por IDENTIFIER (``input.identifier``) — nunca por nombre
    visible. Con Blender en español, el nombre que se MUESTRA del nodo
    ("Principled BSDF") y de sus entradas ("Base Color") puede estar
    traducido si "Traducir datos nuevos" está activo en Preferencias; una
    búsqueda por ese nombre en inglés no encuentra nada, PERO
    ``nodes.get(...)`` no lanza error, devuelve ``None`` en silencio — el
    material se queda con el gris [0.8,0.8,0.8] por defecto de Blender
    sin que se note hasta exportar y mirar el .glb con lupa (exactamente
    lo que pasó acá: los 8 materiales de la primera exportación
    "profesional" salieron todos con ese gris). ``type``/``identifier``
    son valores internos estables, nunca se traducen — por eso no falla
    aunque cambie el idioma de la interfaz."""
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
    """Hornea el scale en la geometría — evita que un padre con escala
    no-uniforme deforme a sus hijos al parentarlos."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def parentar(hijo, padre):
    """keep_transform=True calcula la matriz inversa correcta — sin esto
    el hijo "salta" de posición en cuanto se lo parenta."""
    bpy.ops.object.select_all(action="DESELECT")
    hijo.select_set(True)
    padre.select_set(True)
    bpy.context.view_layer.objects.active = padre
    bpy.ops.object.parent_set(type="OBJECT", keep_transform=True)


def afinar_nariz(obj, factor=0.55, umbral=0.99):
    """Achica en Y/Z los vértices del extremo +X — un morro en cuña en
    vez de un bloque perfectamente rectangular. Truco barato de
    hard-surface (mover 4 vértices), no reemplaza escultura real, pero
    ya alcanza para que deje de leerse como "caja" a simple vista."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    max_x = max(v.co.x for v in obj.data.vertices)
    for v in obj.data.vertices:
        v.select = v.co.x > max_x * umbral
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.transform.resize(value=(1, factor, factor), orient_type="LOCAL")
    bpy.ops.object.mode_set(mode="OBJECT")


def agregar_bisel(obj, ancho=BISEL_ANCHO, segmentos=BISEL_SEGMENTOS):
    """El detalle que más cambia el aspecto "básico por script" a algo
    que lee como intencional: bordes filosos = geometría cruda, bordes
    levemente redondeados = objeto diseñado. Se hornea en el export
    (export_apply=True), no hace falta aplicarlo a mano acá."""
    mod = obj.modifiers.new(name="Bisel", type="BEVEL")
    mod.width = ancho
    mod.segments = segmentos
    mod.limit_method = "ANGLE"


def main():
    limpiar_escena()

    mat_chasis = crear_material("Chasis", (0.13, 0.16, 0.14, 1.0))
    mat_pista = crear_material("Pista", (0.05, 0.05, 0.06, 1.0), rugosidad=0.8)
    mat_rueda = crear_material("Rueda", (0.09, 0.09, 0.10, 1.0), rugosidad=0.7)
    mat_torreta = crear_material("Torreta", (0.17, 0.20, 0.18, 1.0))
    mat_hpm = crear_material("EmisorHPM", (0.31, 0.56, 0.77, 1.0), rugosidad=0.35, metalico=0.2)
    mat_naranja = crear_material("AcentoEnergia", (0.85, 0.47, 0.18, 1.0), rugosidad=0.4)
    mat_detalle = crear_material("Detalle", (0.35, 0.37, 0.36, 1.0), rugosidad=0.5)
    mat_radar = crear_material("Radar", (0.55, 0.62, 0.67, 1.0), rugosidad=0.3, metalico=0.3)

    # --- Chasis ---
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, ALTO_CHASIS / 2))
    chasis = bpy.context.active_object
    chasis.name = "Chasis"
    chasis.scale = (LARGO_CHASIS, ANCHO_CHASIS, ALTO_CHASIS)
    chasis.data.materials.append(mat_chasis)
    aplicar_escala(chasis)
    afinar_nariz(chasis)
    agregar_bisel(chasis)

    # --- Orugas (banda exterior, plana y fina — más fácil de controlar
    # que un cilindro completo, y deja lugar a las ruedas asomando) ---
    y_pista = ANCHO_CHASIS / 2 + 0.15
    for lado, y in [("Izquierda", y_pista), ("Derecha", -y_pista)]:
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(0, y, RADIO_RUEDA)
        )
        pista = bpy.context.active_object
        pista.name = f"Oruga_{lado}"
        pista.scale = (LARGO_CHASIS + 0.6, 0.3, RADIO_RUEDA * 1.7)
        pista.data.materials.append(mat_pista)
        aplicar_escala(pista)
        agregar_bisel(pista, ancho=0.02)
        parentar(pista, chasis)

        # Ruedas asomando por debajo de la pista, a lo largo del chasis.
        paso = (LARGO_CHASIS - RADIO_RUEDA) / (N_RUEDAS_POR_LADO - 1)
        x0 = -(LARGO_CHASIS - RADIO_RUEDA) / 2
        for i in range(N_RUEDAS_POR_LADO):
            x = x0 + i * paso
            bpy.ops.mesh.primitive_cylinder_add(
                radius=RADIO_RUEDA, depth=0.28, location=(x, y, RADIO_RUEDA)
            )
            rueda = bpy.context.active_object
            rueda.rotation_euler = (math.radians(90), 0, 0)
            rueda.name = f"Rueda_{lado}_{i}"
            rueda.data.materials.append(mat_rueda)
            parentar(rueda, chasis)

    # --- Torreta (rota con la dirección de tiro) ---
    z_torreta = ALTO_CHASIS + ALTO_TORRETA / 2
    bpy.ops.mesh.primitive_cube_add(size=1, location=(OFFSET_X_TORRETA, 0, z_torreta))
    torreta = bpy.context.active_object
    torreta.name = "Torreta_HPM"
    torreta.scale = (LARGO_TORRETA, ANCHO_TORRETA, ALTO_TORRETA)
    torreta.data.materials.append(mat_torreta)
    aplicar_escala(torreta)
    agregar_bisel(torreta)
    parentar(torreta, chasis)

    z_base_mastil = ALTO_CHASIS + ALTO_TORRETA
    bpy.ops.mesh.primitive_cylinder_add(
        radius=RADIO_MASTIL, depth=ALTO_MASTIL,
        location=(OFFSET_X_TORRETA, 0, z_base_mastil + ALTO_MASTIL / 2),
    )
    mastil = bpy.context.active_object
    mastil.name = "Mastil"
    mastil.data.materials.append(mat_torreta)
    parentar(mastil, torreta)

    # --- Emisor HPM: panel plano (array en fase), no una antena
    # parabólica — apunta hacia +X, mismo eje que usa render3d.js. ---
    z_emisor = z_base_mastil + ALTO_MASTIL
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(OFFSET_X_TORRETA + ESPESOR_EMISOR / 2, 0, z_emisor)
    )
    emisor = bpy.context.active_object
    emisor.name = "EmisorHPM"
    emisor.scale = (ESPESOR_EMISOR, ANCHO_TORRETA * 0.85, LARGO_EMISOR)
    emisor.data.materials.append(mat_hpm)
    aplicar_escala(emisor)
    agregar_bisel(emisor, ancho=0.015)
    parentar(emisor, torreta)

    # Franja de acento naranja en la base del emisor — mismo color que
    # --accent-orange en frontend/css/style.css ("energía HPM").
    bpy.ops.mesh.primitive_torus_add(
        major_radius=ANCHO_TORRETA * 0.44, minor_radius=0.035,
        location=(OFFSET_X_TORRETA + ESPESOR_EMISOR + 0.02, 0, z_emisor),
        rotation=(0, math.radians(90), 0),
    )
    franja = bpy.context.active_object
    franja.name = "FranjaEmisor"
    franja.data.materials.append(mat_naranja)
    parentar(franja, torreta)

    # --- Lanzador de misiles: sistema INDEPENDIENTE del cañón HPM. En el
    # panel "MISIL HPM" del frontend, dirección/guiado son propios del
    # misil, distintos de los del cañón — así que este nodo rota solo,
    # no se parenta a Torreta_HPM. Base giratoria + tubos en ángulo,
    # mismo criterio visual que un lanzador real tipo NASAMS/IRIS-T. ---
    x_lanzador = OFFSET_X_TORRETA
    y_lanzador = ANCHO_TORRETA / 2 + 0.55
    z_base_lanzador = ALTO_CHASIS

    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(x_lanzador, y_lanzador, z_base_lanzador + 0.15)
    )
    base_lanzador = bpy.context.active_object
    base_lanzador.name = "LanzadorMisil"
    base_lanzador.scale = (0.9, 0.9, 0.3)
    base_lanzador.data.materials.append(mat_torreta)
    aplicar_escala(base_lanzador)
    agregar_bisel(base_lanzador, ancho=0.02)
    parentar(base_lanzador, chasis)

    # Cilindro default: eje Z. Rotar en Y por (90° - elevación) apunta
    # el tubo hacia +X (misma convención de dirección que el cañón) con
    # una inclinación hacia arriba.
    for i, dy in enumerate([-0.32, 0.0, 0.32]):
        bpy.ops.mesh.primitive_cylinder_add(
            radius=RADIO_TUBO_MISIL, depth=LARGO_TUBO_MISIL,
            location=(x_lanzador, y_lanzador + dy, z_base_lanzador + 0.35),
        )
        tubo = bpy.context.active_object
        tubo.rotation_euler = (0, math.radians(90) - ANGULO_ELEVACION_MISIL, 0)
        tubo.name = f"TuboMisil_{i}"
        tubo.data.materials.append(mat_detalle)
        parentar(tubo, base_lanzador)

    # --- Mástil de radar: FIJO, no rota con la torreta — el radar de
    # este proyecto revisita todo el enjambre a la vez, no es un haz
    # direccional (ver P2-G / RADAR_REVISITA_S en src/config.py). ---
    x_mastil_radar = -LARGO_CHASIS * 0.25
    bpy.ops.mesh.primitive_cylinder_add(
        radius=RADIO_MASTIL * 0.8, depth=ALTO_MASTIL_RADAR,
        location=(x_mastil_radar, 0, ALTO_CHASIS + ALTO_MASTIL_RADAR / 2),
    )
    mastil_radar = bpy.context.active_object
    mastil_radar.name = "MastilRadar"
    mastil_radar.data.materials.append(mat_torreta)
    parentar(mastil_radar, chasis)

    bpy.ops.mesh.primitive_cylinder_add(
        radius=RADIO_DISCO_RADAR, depth=0.08,
        location=(x_mastil_radar, 0, ALTO_CHASIS + ALTO_MASTIL_RADAR + 0.05),
    )
    disco_radar = bpy.context.active_object
    disco_radar.name = "DiscoRadar"
    disco_radar.data.materials.append(mat_radar)
    parentar(disco_radar, mastil_radar)

    # --- Detalles: escotilla, faros, caño de escape — quiebran la
    # silueta de "caja lisa" sin agregar complejidad de modelado real. ---
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(-0.6, 0, ALTO_CHASIS + 0.08)
    )
    hatch = bpy.context.active_object
    hatch.name = "Escotilla"
    hatch.scale = (0.7, 0.7, 0.16)
    hatch.data.materials.append(mat_detalle)
    aplicar_escala(hatch)
    agregar_bisel(hatch, ancho=0.015)
    parentar(hatch, chasis)

    for lado, y in [("Izquierdo", ANCHO_CHASIS / 2 - 0.15), ("Derecho", -(ANCHO_CHASIS / 2 - 0.15))]:
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.12, depth=0.1,
            location=(LARGO_CHASIS / 2 - 0.05, y, ALTO_CHASIS * 0.55),
        )
        faro = bpy.context.active_object
        faro.rotation_euler = (0, math.radians(90), 0)
        faro.name = f"Faro{lado}"
        faro.data.materials.append(mat_detalle)
        parentar(faro, chasis)

    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.09, depth=0.5,
        location=(-LARGO_CHASIS / 2 + 0.1, ANCHO_CHASIS / 2 - 0.3, ALTO_CHASIS * 0.4),
    )
    escape = bpy.context.active_object
    escape.rotation_euler = (0, math.radians(90), 0)
    escape.name = "Escape"
    escape.data.materials.append(mat_detalle)
    parentar(escape, chasis)

    # --- Módulo de generador/refrigeración (parte trasera): el cañón
    # HPM ya modela energía y temperatura (src/config.py) — este bulto
    # de equipo es lo que las sostiene, no relleno visual. ---
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=(-LARGO_CHASIS * 0.3, 0, ALTO_CHASIS + 0.35)
    )
    generador = bpy.context.active_object
    generador.name = "Generador"
    generador.scale = (1.6, 2.2, 0.7)
    generador.data.materials.append(mat_torreta)
    aplicar_escala(generador)
    agregar_bisel(generador, ancho=0.02)
    parentar(generador, chasis)

    for i in range(4):
        y = -0.75 + i * 0.5
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(-LARGO_CHASIS * 0.3, y, ALTO_CHASIS + 0.71)
        )
        rejilla = bpy.context.active_object
        rejilla.name = f"RejillaGenerador_{i}"
        rejilla.scale = (1.55, 0.06, 0.05)
        rejilla.data.materials.append(mat_detalle)
        aplicar_escala(rejilla)
        parentar(rejilla, generador)

    # --- Exportar (export_apply=True hornea los modificadores de bisel) ---
    os.makedirs(os.path.dirname(RUTA_SALIDA), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=RUTA_SALIDA,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )
    print(f"Lanzador HPM exportado a: {RUTA_SALIDA}")


main()
