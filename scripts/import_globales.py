#!/usr/bin/env python3
"""Carga inicial de 4 archivos globales SabioGo directamente a la base de datos.

Este script bypasa la API web y escribe directo a Postgres con el app context
de Flask. Ideal para la carga histórica inicial (archivos grandes).

Uso:
    python scripts/import_globales.py \\
        --carnes-ventas  /ruta/carnes_ventas_globales.xls \\
        --lacteos-ventas /ruta/lacteos_ventas_globales.xls \\
        --carnes-compras /ruta/carnes_compras_globales.xls \\
        --lacteos-compras /ruta/lacteos_compras_globales.xls \\
        [--no-replace]

Opciones:
    --no-replace    No borra datos previos del origen (modo append)
    --dry-run       Solo valida columnas sin escribir a DB
"""

import argparse
import os
import sys
import hashlib
import re
from pathlib import Path
from typing import Optional

# Agrega la raíz del proyecto al path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Carga variables de entorno desde .env si está disponible
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import pandas as pd

COLS_REQUERIDAS = ['fecha', 'codigo', 'producto']
COLS_SABIOGO_28 = [
    'rubro', 'fecha', 'subrubro', 'codigo', 'modelo', 'producto', 'marca', 'comprobante',
    'nro_comprob', 'cliente', 'condicion_iva', 'vendedor', 'deposito', 'uninegocio',
    'forma_pago', 'kilos', 'cajas', 'dtos', 'neto', 'localidad', 'zona', 'sucursal',
    'iva', 'moniva', 'tipo', 'subtot', 'numlispre', 'lisprec',
]
ORIGEN_CARNES  = 'CARNES'
ORIGEN_LACTEOS = 'LACTEOS'


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def normalize_codigo(value) -> Optional[str]:
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
    if re.fullmatch(r'\d+\.0+', text_value):
        text_value = text_value.split('.', 1)[0]
    return text_value


def read_excel_robust(path: str) -> pd.DataFrame:
    """Lee XLS/XLSX probando header real o fallback por posición para 28 columnas."""
    ext = Path(path).suffix.lower()
    engines = ['xlrd'] if ext == '.xls' else ['openpyxl']
    engines.append(None)

    last_err = None
    for engine in engines:
        for header_row in range(8):
            try:
                kwargs = {'header': header_row}
                if engine is not None:
                    kwargs['engine'] = engine
                df = pd.read_excel(path, **kwargs)
                df.columns = [str(c).lower().strip() for c in df.columns]
                if all(col in df.columns for col in COLS_REQUERIDAS):
                    print(f"  ✓ Header detectado en fila {header_row} (engine={engine})")
                    return df
            except Exception as exc:
                last_err = exc
                continue

    for engine in engines:
        try:
            kwargs = {'header': None}
            if engine is not None:
                kwargs['engine'] = engine
            df = pd.read_excel(path, **kwargs)
            if df.shape[1] == len(COLS_SABIOGO_28):
                df.columns = COLS_SABIOGO_28
                print(f"  ✓ Archivo sin header: se aplicó layout SabioGo de 28 columnas (engine={engine})")
                return df
        except Exception as exc:
            last_err = exc
            continue

    raise ValueError(
        f"No se pudo detectar encabezado en '{Path(path).name}'. "
        f"Columnas esperadas: {COLS_REQUERIDAS}. Último error: {last_err}"
    )


def import_transacciones(df: pd.DataFrame, *, ModelClass, origen: str, filename: str,
                          file_sha256: str, dry_run: bool, db_session) -> dict:
    """Inserta filas del DataFrame en la tabla de staging."""
    from sqlalchemy import inspect as sa_inspect
    valid_cols = {c.key for c in sa_inspect(ModelClass).mapper.column_attrs}

    filas_insertadas = 0
    filas_error = 0

    for i, (_, row) in enumerate(df.iterrows(), 1):
        if dry_run:
            continue
        try:
            data = row.to_dict()
            for key, value in list(data.items()):
                try:
                    if pd.isna(value):
                        data[key] = None
                except Exception:
                    pass
            data = {k: v for k, v in data.items() if k in valid_cols}
            codigo_raw = data.get('codigo')
            data['codigo_raw'] = None if codigo_raw is None else str(codigo_raw)
            data['codigo'] = normalize_codigo(codigo_raw)
            data['origen'] = origen
            data['fuente_archivo'] = filename
            data['hash_archivo'] = file_sha256
            data['estado'] = 'pendiente'

            registro = ModelClass(**data)
            db_session.add(registro)
            filas_insertadas += 1

            if filas_insertadas % 2000 == 0:
                db_session.flush()
                print(f"    … {filas_insertadas} filas insertadas")
        except Exception as exc:
            filas_error += 1
            if filas_error <= 5:
                print(f"  ⚠ Error fila {i}: {exc}")

    if not dry_run:
        db_session.commit()

        # Marcar duplicados
        try:
            dup = ModelClass.validar_duplicados(db_session)
            print(f"  → Duplicados marcados: {dup}")
        except Exception:
            pass

        # Promover a procesado
        promovidos = db_session.query(ModelClass).filter(
            ModelClass.hash_archivo == file_sha256,
            ModelClass.estado == 'pendiente',
        ).update({'estado': 'procesado'}, synchronize_session=False)
        db_session.commit()
        print(f"  → Promovidos a 'procesado': {promovidos}")

    return {'filas_insertadas': filas_insertadas, 'filas_error': filas_error}


def main():
    parser = argparse.ArgumentParser(description='Carga global SabioGo (4 archivos)')
    parser.add_argument('--carnes-ventas',   metavar='PATH', help='Ventas Carnes (.xls/.xlsx)')
    parser.add_argument('--lacteos-ventas',  metavar='PATH', help='Ventas Lácteos (.xls/.xlsx)')
    parser.add_argument('--carnes-compras',  metavar='PATH', help='Compras Carnes (.xls/.xlsx)')
    parser.add_argument('--lacteos-compras', metavar='PATH', help='Compras Lácteos (.xls/.xlsx)')
    parser.add_argument('--no-replace', action='store_true', help='No borrar datos previos del origen')
    parser.add_argument('--dry-run',    action='store_true', help='Solo valida sin escribir a DB')
    args = parser.parse_args()

    archivos = {
        'carnes_ventas':   (args.carnes_ventas,   ORIGEN_CARNES,  'ventas'),
        'lacteos_ventas':  (args.lacteos_ventas,  ORIGEN_LACTEOS, 'ventas'),
        'carnes_compras':  (args.carnes_compras,  ORIGEN_CARNES,  'compras'),
        'lacteos_compras': (args.lacteos_compras, ORIGEN_LACTEOS, 'compras'),
    }
    archivos_activos = {k: v for k, v in archivos.items() if v[0]}

    if not archivos_activos:
        parser.error('Debe especificar al menos un archivo.')

    replace = not args.no_replace
    dry_run = args.dry_run

    print(f"\n{'='*60}")
    print(f"  SabioGo — Carga Global")
    print(f"  replace={replace}  dry_run={dry_run}")
    print(f"{'='*60}\n")

    # Validar que los archivos existen
    for key, (path, _, _) in archivos_activos.items():
        if not os.path.exists(path):
            print(f"✗ Archivo no encontrado: {path}")
            sys.exit(1)
        print(f"✓ {key}: {path}")
    print()

    # Inicializar Flask app
    from app import create_app
    from models import db
    from models.sabiogo import StgSabiogoVentas, StgSabiogoCompras

    MODEL_MAP = {'ventas': StgSabiogoVentas, 'compras': StgSabiogoCompras}

    app = create_app()
    with app.app_context():
        # ── Reemplazo ─────────────────────────────────────────────────────
        if replace and not dry_run:
            print('── Limpiando datos previos ──────────────────────────────')
            for key, (_, origen, tipo) in archivos_activos.items():
                ModelClass = MODEL_MAP[tipo]
                n = db.session.query(ModelClass).filter(
                    ModelClass.origen == origen
                ).delete(synchronize_session=False)
                print(f"  Eliminados {n:,} registros {ModelClass.__tablename__} origen={origen}")
            db.session.commit()
            print()

        # ── Importación ───────────────────────────────────────────────────
        for key, (path, origen, tipo) in archivos_activos.items():
            ModelClass = MODEL_MAP[tipo]
            filename = Path(path).name
            print(f'── {key.upper()} ({filename}) ──────────────────────────')
            try:
                df = read_excel_robust(path)
                print(f"  Filas en archivo: {len(df):,}  |  Columnas: {list(df.columns)[:8]}…")
                if dry_run:
                    print("  [dry-run] No se escribirá en la base de datos.")
                    continue

                file_sha = sha256_file(path)
                stats = import_transacciones(
                    df,
                    ModelClass=ModelClass,
                    origen=origen,
                    filename=filename,
                    file_sha256=file_sha,
                    dry_run=False,
                    db_session=db.session,
                )
                print(f"  ✓ Insertadas: {stats['filas_insertadas']:,}  |  Errores: {stats['filas_error']}")
            except Exception as exc:
                print(f"  ✗ ERROR: {exc}")
            print()

        print('══ Importación finalizada ══════════════════════════════════\n')


if __name__ == '__main__':
    main()
