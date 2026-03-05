"""Importador batch SabioGo (6 archivos + manifest) desde filesystem.

Objetivo:
- Separar extracción (PowerShell) de ingesta (App360) con contrato estable.
- Validar hashes/estructura antes de tocar DB.
- Procesar idempotente por batch_id.

Formato esperado:
- batch_dir contiene `manifest.json` y los archivos referenciados.
- Los XLS pueden ser .xls/.xlsx.

Este módulo NO implementa automatización; solo la ingesta server-side.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from sqlalchemy import func

from models import db
from models.core.product import Product
from models.sabiogo import (
    LogSabiogoBatch,
    LogSabiogoCarga,
    SabiogoProductMap,
    StgSabiogoCompras,
    StgSabiogoVentas,
)


ORIGEN_LEGACY = "LEGACY"
ORIGEN_CARNES = "CARNES"
ORIGEN_LACTEOS = "LACTEOS"

TIPO_PRODUCTOS = "PRODUCTOS"
TIPO_VENTAS = "VENTAS"
TIPO_COMPRAS = "COMPRAS"


def sha256_file(path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def infer_origen_from_filename(filename: str) -> Optional[str]:
    if not filename:
        return None
    name = filename.lower()
    if re.search(r"\b(carne|carnes|vyp\s*carnes)\b", name):
        return ORIGEN_CARNES
    if re.search(r"\b(lacteo|lácteo|lacteos|lácteos|vyp\s*lacteos)\b", name):
        return ORIGEN_LACTEOS
    return None


def infer_tipo_from_filename(filename: str) -> Optional[str]:
    if not filename:
        return None
    name = filename.lower()
    if "producto" in name or "articulo" in name or "artículos" in name or "articulos" in name:
        return TIPO_PRODUCTOS
    if "venta" in name or "ventas" in name:
        return TIPO_VENTAS
    if "compra" in name or "compras" in name or "costo" in name or "costos" in name:
        return TIPO_COMPRAS
    return None


def normalize_codigo(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    text_value = str(value).strip()
    if not text_value:
        return None

    if re.fullmatch(r"\d+\.0+", text_value):
        text_value = text_value.split(".", 1)[0]

    return text_value


@dataclass(frozen=True)
class ManifestFile:
    name: str
    sha256: str
    tipo: str
    origen: str


@dataclass(frozen=True)
class Manifest:
    batch_id: str
    fecha_datos: Optional[date]
    schema_version: int
    files: List[ManifestFile]


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


def load_manifest(batch_dir: str) -> Tuple[Manifest, str, str]:
    manifest_path = os.path.join(batch_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"No se encontró manifest.json en {batch_dir}")

    manifest_sha = sha256_file(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    batch_id = str(data.get("batch_id") or "").strip()
    if not batch_id:
        raise ValueError("manifest.json: falta batch_id")

    schema_version = int(data.get("schema_version") or 1)

    fecha_datos = _parse_date(data.get("fecha_datos"))

    files_data = data.get("files") or []
    if not isinstance(files_data, list) or not files_data:
        raise ValueError("manifest.json: files debe ser lista no vacía")

    files: List[ManifestFile] = []
    for item in files_data:
        name = str(item.get("name") or "").strip()
        sha = str(item.get("sha256") or "").strip().lower()
        tipo = str(item.get("tipo") or infer_tipo_from_filename(name) or "").strip().upper()
        origen = str(item.get("origen") or infer_origen_from_filename(name) or ORIGEN_LEGACY).strip().upper()

        if not name or not sha or not tipo:
            raise ValueError(f"manifest.json: item inválido: {item}")
        if tipo not in {TIPO_PRODUCTOS, TIPO_VENTAS, TIPO_COMPRAS}:
            raise ValueError(f"manifest.json: tipo inválido {tipo} para {name}")

        files.append(ManifestFile(name=name, sha256=sha, tipo=tipo, origen=origen))

    return Manifest(batch_id=batch_id, fecha_datos=fecha_datos, schema_version=schema_version, files=files), manifest_path, manifest_sha


def validate_files(batch_dir: str, manifest: Manifest) -> None:
    for f in manifest.files:
        path = os.path.join(batch_dir, f.name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Falta archivo {f.name} en batch {manifest.batch_id}")
        sha = sha256_file(path)
        if sha.lower() != f.sha256.lower():
            raise ValueError(f"Hash sha256 no coincide para {f.name}")


def _read_excel(path: str) -> pd.DataFrame:
    # Nota: no forzamos dtype global porque puede variar; normalizamos campos claves luego.
    return pd.read_excel(path)


def import_productos_xls(path: str, *, origen: str, filename: str, file_sha256: str) -> Dict[str, int]:
    df = _read_excel(path)

    if "codigo" not in df.columns:
        raise ValueError(f"{filename}: falta columna 'codigo'")
    if "producto" not in df.columns:
        raise ValueError(f"{filename}: falta columna 'producto'")

    creados = 0
    actualizados = 0
    mapeos_creados = 0
    mapeos_actualizados = 0

    for _, row in df.iterrows():
        raw = row.get("codigo")
        codigo = normalize_codigo(raw)
        if not codigo:
            continue

        producto_desc = row.get("producto")
        marca = row.get("marca") if "marca" in df.columns else None
        modelo = row.get("modelo") if "modelo" in df.columns else None

        product = Product.query.filter_by(sku=codigo).first()
        if not product:
            product = Product(
                sku=codigo,
                name=str(producto_desc)[:200] if producto_desc else codigo,
                category=origen,
            )
            db.session.add(product)
            db.session.flush()
            creados += 1
        else:
            # No pisar manualmente nombres; solo completar si está vacío.
            if (not getattr(product, "name", None)) and producto_desc:
                product.name = str(producto_desc)[:200]
                actualizados += 1

        mapeo = SabiogoProductMap.query.filter_by(origen=origen, codigo=codigo).first()
        if not mapeo:
            mapeo = SabiogoProductMap(origen=origen, codigo=codigo)
            db.session.add(mapeo)
            mapeos_creados += 1
        else:
            mapeos_actualizados += 1

        mapeo.product_id = product.id
        mapeo.activo = True
        mapeo.producto_descripcion = str(producto_desc)[:200] if producto_desc else None
        mapeo.marca = str(marca)[:100] if marca is not None else None
        mapeo.modelo = str(modelo)[:100] if modelo is not None else None

    db.session.commit()

    # Log file-level (compatibilidad)
    log = LogSabiogoCarga(
        archivo_nombre=filename,
        tipo_carga="productos",
        hash_archivo=file_sha256,
        filas_insertadas=int(len(df.index)),
        filas_duplicadas=0,
        filas_sin_mapeo=0,
        filas_error=0,
        observaciones=f"origen={origen}",
    )
    db.session.add(log)
    db.session.commit()

    return {
        "productos_creados": creados,
        "productos_actualizados": actualizados,
        "mapeos_creados": mapeos_creados,
        "mapeos_actualizados": mapeos_actualizados,
    }


def _import_transacciones(df: pd.DataFrame, *, tipo: str, origen: str, filename: str, file_sha256: str) -> Dict[str, int]:
    columnas_requeridas = ["fecha", "codigo", "producto"]
    if not all(col in df.columns for col in columnas_requeridas):
        raise ValueError(f"{filename}: faltan columnas requeridas {columnas_requeridas}")

    ModelClass = StgSabiogoVentas if tipo == TIPO_VENTAS else StgSabiogoCompras

    filas_insertadas = 0
    filas_error = 0

    for _, row in df.iterrows():
        try:
            data = row.to_dict()
            for key, value in list(data.items()):
                if pd.isna(value):
                    data[key] = None

            codigo_raw = data.get("codigo")
            data["codigo_raw"] = None if codigo_raw is None else str(codigo_raw)
            data["codigo"] = normalize_codigo(codigo_raw)
            data["origen"] = origen

            data["fuente_archivo"] = filename
            data["hash_archivo"] = file_sha256
            data["estado"] = "pendiente"

            registro = ModelClass(**data)
            db.session.add(registro)
            filas_insertadas += 1
        except Exception:
            filas_error += 1

    db.session.commit()

    # Duplicados (reusa método existente)
    try:
        duplicados = ModelClass.validar_duplicados(db.session)
    except Exception:
        duplicados = 0

    filas_procesadas = (
        db.session.query(ModelClass)
        .filter(ModelClass.hash_archivo == file_sha256, ModelClass.estado == "pendiente")
        .update({"estado": "procesado"}, synchronize_session=False)
    )
    db.session.commit()

    # Sin mapeo (por origen)
    subq = (
        db.session.query(SabiogoProductMap.codigo)
        .filter(
            (SabiogoProductMap.origen == origen) | (SabiogoProductMap.origen.is_(None)),
            SabiogoProductMap.activo == True,
            SabiogoProductMap.product_id.isnot(None),
        )
    )

    sin_mapeo = (
        db.session.query(ModelClass)
        .filter(ModelClass.hash_archivo == file_sha256)
        .filter((ModelClass.origen == origen) | (ModelClass.origen.is_(None)))
        .filter(ModelClass.codigo.notin_(subq))
        .count()
    )

    # Log
    log = LogSabiogoCarga(
        archivo_nombre=filename,
        tipo_carga="ventas" if tipo == TIPO_VENTAS else "compras",
        hash_archivo=file_sha256,
        filas_insertadas=filas_insertadas,
        filas_duplicadas=duplicados,
        filas_sin_mapeo=sin_mapeo,
        filas_error=filas_error,
        observaciones=f"origen={origen}",
    )
    db.session.add(log)
    db.session.commit()

    return {
        "filas_insertadas": filas_insertadas,
        "filas_duplicadas": int(duplicados or 0),
        "filas_procesadas": int(filas_procesadas or 0),
        "filas_sin_mapeo": int(sin_mapeo or 0),
        "filas_error": filas_error,
    }


def import_transacciones_xls(path: str, *, tipo: str, origen: str, filename: str, file_sha256: str) -> Dict[str, int]:
    df = _read_excel(path)
    return _import_transacciones(df, tipo=tipo, origen=origen, filename=filename, file_sha256=file_sha256)


def process_batch(batch_dir: str) -> Dict[str, Any]:
    manifest, manifest_path, manifest_sha = load_manifest(batch_dir)
    validate_files(batch_dir, manifest)

    existing = LogSabiogoBatch.query.filter_by(batch_id=manifest.batch_id).first()
    if existing and existing.status == "success":
        return {"batch_id": manifest.batch_id, "status": "already_processed"}

    batch = existing or LogSabiogoBatch(batch_id=manifest.batch_id)
    batch.fecha_datos = manifest.fecha_datos
    batch.status = "processing"
    batch.manifest_path = manifest_path
    batch.manifest_sha256 = manifest_sha
    db.session.add(batch)
    db.session.commit()

    stats: Dict[str, Any] = {"files": []}

    try:
        for f in manifest.files:
            path = os.path.join(batch_dir, f.name)
            file_sha = sha256_file(path)

            if f.tipo == TIPO_PRODUCTOS:
                file_stats = import_productos_xls(path, origen=f.origen, filename=f.name, file_sha256=file_sha)
            elif f.tipo == TIPO_VENTAS:
                file_stats = import_transacciones_xls(path, tipo=TIPO_VENTAS, origen=f.origen, filename=f.name, file_sha256=file_sha)
            else:
                file_stats = import_transacciones_xls(path, tipo=TIPO_COMPRAS, origen=f.origen, filename=f.name, file_sha256=file_sha)

            stats["files"].append({"name": f.name, "tipo": f.tipo, "origen": f.origen, "stats": file_stats})

        batch.status = "success"
        batch.error = None
        batch.stats_json = json.dumps(stats, ensure_ascii=False)
        db.session.commit()
        return {"batch_id": manifest.batch_id, "status": "success", "stats": stats}

    except Exception as e:
        db.session.rollback()
        batch.status = "failed"
        batch.error = str(e)
        batch.stats_json = json.dumps(stats, ensure_ascii=False)
        db.session.add(batch)
        db.session.commit()
        raise
