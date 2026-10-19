"""Códigos de empresa usados por los módulos operativos y analíticos.

No representan ``BusinessUnit``: son el alcance comercial/financiero de cada
registro. Los valores ``NULL`` que ya existen en la base se reservan para el
histórico global sin atribución.
"""

from __future__ import annotations


EMPRESA_TODAS = "TODAS"
EMPRESAS_VALIDAS = ("CARNES", "LACTEOS")
EMPRESA_LABELS = {
    "CARNES": "Carnes",
    "LACTEOS": "Lácteos",
}


def normalizar_empresa(
    value,
    *,
    allow_todas: bool = False,
    allow_none: bool = False,
) -> str | None:
    """Normaliza y valida un alcance de empresa.

    ``None`` y texto vacío sólo se aceptan cuando ``allow_none`` es verdadero;
    en ese caso devuelven ``None`` para que los listados incluyan el histórico
    global. ``TODAS`` sólo se acepta explícitamente para filtros agregados.
    """
    if value is None:
        if allow_none:
            return None
        raise ValueError("Empresa requerida: elegí CARNES o LACTEOS.")

    empresa = str(value).strip().upper()
    if not empresa:
        if allow_none:
            return None
        raise ValueError("Empresa requerida: elegí CARNES o LACTEOS.")

    if allow_todas and empresa == EMPRESA_TODAS:
        return EMPRESA_TODAS
    if empresa in EMPRESAS_VALIDAS:
        return empresa
    if empresa == EMPRESA_TODAS:
        raise ValueError("Empresa debe ser CARNES o LACTEOS.")
    raise ValueError("Empresa inválida. Usá CARNES o LACTEOS.")


def empresa_es_especifica(value) -> bool:
    """Indica si ``value`` es una empresa concreta, validando su formato."""
    empresa = normalizar_empresa(value, allow_todas=True, allow_none=True)
    return empresa in EMPRESAS_VALIDAS


def etiqueta_empresa(value) -> str:
    """Etiqueta legible para serializaciones y exportaciones."""
    return EMPRESA_LABELS.get(value, "Histórico global")
