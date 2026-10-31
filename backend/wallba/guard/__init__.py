"""Guardia de archivos de un proyecto frente al agente instrumentado.

El bloqueo preventivo solo ocurre si la operación pasa por el hook o el shim.
Un cambio visto por el monitor queda como detección, con origen no determinado.
"""
