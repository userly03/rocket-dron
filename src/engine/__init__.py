"""Motor de simulación: física, modelo HPM y bucle principal.

No reexporta símbolos a nivel de paquete a propósito: importar aquí
``src.engine.simulation`` (que a su vez depende de ``src.models``) crea un
ciclo de imports frágil y dependiente del orden con ``src/models/__init__.py``.
Importa siempre desde el submódulo concreto, p. ej.:
``from src.engine.simulation import SimulationEngine``.
"""
