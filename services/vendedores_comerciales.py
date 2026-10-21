"""Catálogo y resolución explícita de identidades comerciales."""

from sqlalchemy import or_

from models import db
from models.comercial import ComercialVendedor, ComercialVendedorAlias


EQUIVALENCIAS_COMERCIALES = (
    ("Benjamín Kalja", ("KALJA BENJAMIN", "BENJAMIN KALJA")),
    ("Walter Medina", ("MEDINA WALTER", "WALTER")),
)


def colapsar_espacios(nombre: str | None) -> str:
    """Colapsa cualquier secuencia de espacios, sin cambiar mayúsculas."""
    return " ".join((nombre or "").split())


def normalizar_nombre_origen(nombre: str | None) -> str:
    """Devuelve la clave exacta de comparación de un nombre de origen."""
    return colapsar_espacios(nombre).upper()


def resolver_nombre_vendedor(nombre_origen: str | None) -> str:
    """Resuelve solo alias explícitos; de otro modo conserva el texto colapsado."""
    nombre_visible_sin_alias = colapsar_espacios(nombre_origen)
    clave = normalizar_nombre_origen(nombre_origen)
    if not clave:
        return nombre_visible_sin_alias

    alias = (
        db.session.query(ComercialVendedorAlias)
        .filter_by(nombre_normalizado=clave)
        .one_or_none()
    )
    if alias is None:
        return nombre_visible_sin_alias
    return alias.vendedor.nombre_visible


def seed_vendedores_comerciales(session=None) -> None:
    """Carga el catálogo y sus alias explícitos de forma idempotente."""
    session = session or db.session

    for nombre_visible, nombres_origen in EQUIVALENCIAS_COMERCIALES:
        vendedor = (
            session.query(ComercialVendedor)
            .filter_by(nombre_visible=nombre_visible)
            .one_or_none()
        )
        if vendedor is None:
            vendedor = ComercialVendedor(nombre_visible=nombre_visible, activo=True)
            session.add(vendedor)
            session.flush()

        for nombre_origen in nombres_origen:
            clave = normalizar_nombre_origen(nombre_origen)
            alias_existente = (
                session.query(ComercialVendedorAlias.id)
                .filter(
                    or_(
                        ComercialVendedorAlias.nombre_origen == nombre_origen,
                        ComercialVendedorAlias.nombre_normalizado == clave,
                    )
                )
                .first()
            )
            if alias_existente is not None:
                continue

            session.add(
                ComercialVendedorAlias(
                    vendedor_id=vendedor.id,
                    nombre_origen=nombre_origen,
                    nombre_normalizado=clave,
                )
            )

    session.flush()
