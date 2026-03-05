#!/usr/bin/env python3
"""
Script para carga inicial de mapeos SabioGo.
Extrae códigos únicos desde stg_sabiogo_ventas y stg_sabiogo_compras,
intenta matching con productos existentes y genera reporte de códigos sin mapear.

Uso: python scripts/setup_sabiogo_mapeos.py
"""

import os
import sys
import csv
from datetime import datetime

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from models import db
from models.sabiogo import (
    StgSabiogoVentas, 
    StgSabiogoCompras,
    SabiogoProductMap,
    SabiogoClientMap,
    SabiogoLocationMap
)
from models.core.product import Product
from models.crm.client import Client
from models.core.location import Location
from sqlalchemy import func, distinct


ORIGEN_LEGACY = 'LEGACY'


def extraer_codigos_productos():
    """Extrae códigos únicos de productos desde staging."""
    print("📦 Extrayendo códigos de productos desde staging...")
    
    # Códigos desde ventas
    codigos_ventas = db.session.query(
        StgSabiogoVentas.origen,
        distinct(StgSabiogoVentas.codigo),
        StgSabiogoVentas.producto,
        StgSabiogoVentas.marca,
        StgSabiogoVentas.modelo
    ).filter(
        StgSabiogoVentas.codigo.isnot(None),
        StgSabiogoVentas.codigo != ''
    ).all()
    
    # Códigos desde compras
    codigos_compras = db.session.query(
        StgSabiogoCompras.origen,
        distinct(StgSabiogoCompras.codigo),
        StgSabiogoCompras.producto,
        StgSabiogoCompras.marca,
        StgSabiogoCompras.modelo
    ).filter(
        StgSabiogoCompras.codigo.isnot(None),
        StgSabiogoCompras.codigo != ''
    ).all()
    
    # Combinar y deduplicar
    codigos_dict = {}
    for origen, codigo, producto, marca, modelo in codigos_ventas + codigos_compras:
        origen = origen or ORIGEN_LEGACY
        key = (origen, codigo)
        if key not in codigos_dict:
            codigos_dict[key] = {
                'producto': producto,
                'marca': marca,
                'modelo': modelo
            }
    
    print(f"✅ Encontrados {len(codigos_dict)} códigos únicos")
    return codigos_dict


def mapear_productos(codigos_dict):
    """Intenta mapear códigos con productos existentes usando SKU."""
    print("🔗 Mapeando productos con base existente...")
    
    mapeados = 0
    sin_mapear = 0
    sin_mapear_detalle = []
    
    for (origen, codigo), info in codigos_dict.items():
        # Verificar si ya existe el mapeo
        existing = SabiogoProductMap.query.filter_by(origen=origen, codigo=codigo).first()
        if existing:
            continue
        
        # Intentar matching por SKU
        product = Product.query.filter_by(sku=codigo).first()
        
        mapeo = SabiogoProductMap(
            origen=origen,
            codigo=codigo,
            product_id=product.id if product else None,
            marca=info['marca'],
            modelo=info['modelo'],
            producto_descripcion=info['producto'],
            activo=True if product else False
        )
        
        db.session.add(mapeo)
        
        if product:
            mapeados += 1
        else:
            sin_mapear += 1
            sin_mapear_detalle.append({
                'codigo': codigo,
                'producto': info['producto'],
                'marca': info['marca'],
                'modelo': info['modelo']
            })
    
    db.session.commit()
    
    print(f"✅ Mapeados automáticamente: {mapeados}")
    print(f"⚠️  Sin mapear: {sin_mapear}")
    
    return sin_mapear_detalle


def extraer_clientes():
    """Extrae clientes únicos desde staging."""
    print("👥 Extrayendo clientes desde staging...")
    
    clientes = db.session.query(
        StgSabiogoVentas.cliente,
        StgSabiogoVentas.condicion_iva,
        StgSabiogoVentas.zona,
        StgSabiogoVentas.localidad
    ).filter(
        StgSabiogoVentas.cliente.isnot(None),
        StgSabiogoVentas.cliente != ''
    ).group_by(
        StgSabiogoVentas.cliente,
        StgSabiogoVentas.condicion_iva,
        StgSabiogoVentas.zona,
        StgSabiogoVentas.localidad
    ).all()
    
    print(f"✅ Encontrados {len(clientes)} clientes únicos")
    return clientes


def mapear_clientes(clientes):
    """Intenta mapear clientes con base existente."""
    print("🔗 Mapeando clientes con base existente...")
    
    mapeados = 0
    sin_mapear = 0
    sin_mapear_detalle = []
    
    for cliente, condicion_iva, zona, localidad in clientes:
        # Verificar si ya existe el mapeo
        existing = SabiogoClientMap.query.filter_by(
            cliente=cliente,
            condicion_iva=condicion_iva
        ).first()
        if existing:
            continue
        
        # Intentar matching por nombre (aproximado)
        client = Client.query.filter(
            func.lower(Client.name).like(f"%{cliente.lower()}%")
        ).first()
        
        mapeo = SabiogoClientMap(
            cliente=cliente,
            condicion_iva=condicion_iva,
            client_id=client.id if client else None,
            zona=zona,
            localidad=localidad,
            activo=True if client else False
        )
        
        db.session.add(mapeo)
        
        if client:
            mapeados += 1
        else:
            sin_mapear += 1
            sin_mapear_detalle.append({
                'cliente': cliente,
                'condicion_iva': condicion_iva,
                'zona': zona,
                'localidad': localidad
            })
    
    db.session.commit()
    
    print(f"✅ Mapeados automáticamente: {mapeados}")
    print(f"⚠️  Sin mapear: {sin_mapear}")
    
    return sin_mapear_detalle


def extraer_sucursales():
    """Extrae sucursales únicas desde staging."""
    print("🏢 Extrayendo sucursales desde staging...")
    
    # Desde ventas
    sucursales_ventas = db.session.query(
        StgSabiogoVentas.sucursal,
        StgSabiogoVentas.deposito,
        StgSabiogoVentas.uninegocio
    ).filter(
        StgSabiogoVentas.sucursal.isnot(None),
        StgSabiogoVentas.sucursal != ''
    ).group_by(
        StgSabiogoVentas.sucursal,
        StgSabiogoVentas.deposito,
        StgSabiogoVentas.uninegocio
    ).all()
    
    # Desde compras
    sucursales_compras = db.session.query(
        StgSabiogoCompras.sucursal,
        StgSabiogoCompras.deposito,
        StgSabiogoCompras.uninegocio
    ).filter(
        StgSabiogoCompras.sucursal.isnot(None),
        StgSabiogoCompras.sucursal != ''
    ).group_by(
        StgSabiogoCompras.sucursal,
        StgSabiogoCompras.deposito,
        StgSabiogoCompras.uninegocio
    ).all()
    
    # Combinar y deduplicar
    sucursales_set = set(sucursales_ventas + sucursales_compras)
    
    print(f"✅ Encontradas {len(sucursales_set)} sucursales únicas")
    return list(sucursales_set)


def mapear_sucursales(sucursales):
    """Intenta mapear sucursales con ubicaciones existentes."""
    print("🔗 Mapeando sucursales con ubicaciones existentes...")
    
    mapeados = 0
    sin_mapear = 0
    sin_mapear_detalle = []
    
    for sucursal, deposito, uninegocio in sucursales:
        # Verificar si ya existe el mapeo
        existing = SabiogoLocationMap.query.filter_by(
            sucursal=sucursal,
            deposito=deposito
        ).first()
        if existing:
            continue
        
        # Intentar matching por nombre
        location = Location.query.filter(
            func.lower(Location.name).like(f"%{sucursal.lower()}%")
        ).first()
        
        mapeo = SabiogoLocationMap(
            sucursal=sucursal,
            deposito=deposito,
            uninegocio=uninegocio,
            location_id=location.id if location else None,
            activo=True if location else False
        )
        
        db.session.add(mapeo)
        
        if location:
            mapeados += 1
        else:
            sin_mapear += 1
            sin_mapear_detalle.append({
                'sucursal': sucursal,
                'deposito': deposito,
                'uninegocio': uninegocio
            })
    
    db.session.commit()
    
    print(f"✅ Mapeados automáticamente: {mapeados}")
    print(f"⚠️  Sin mapear: {sin_mapear}")
    
    return sin_mapear_detalle


def generar_reporte(productos_sin_mapear, clientes_sin_mapear, sucursales_sin_mapear):
    """Genera reporte CSV con elementos sin mapear."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sabiogo_sin_mapear_{timestamp}.csv"
    
    print(f"📝 Generando reporte: {filename}")
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        # Productos
        if productos_sin_mapear:
            writer = csv.DictWriter(csvfile, fieldnames=['tipo', 'codigo', 'producto', 'marca', 'modelo'])
            writer.writeheader()
            for item in productos_sin_mapear:
                writer.writerow({
                    'tipo': 'PRODUCTO',
                    'codigo': item['codigo'],
                    'producto': item['producto'],
                    'marca': item['marca'],
                    'modelo': item['modelo']
                })
        
        # Clientes
        if clientes_sin_mapear:
            writer = csv.DictWriter(csvfile, fieldnames=['tipo', 'cliente', 'condicion_iva', 'zona', 'localidad'])
            if not productos_sin_mapear:
                writer.writeheader()
            for item in clientes_sin_mapear:
                writer.writerow({
                    'tipo': 'CLIENTE',
                    'cliente': item['cliente'],
                    'condicion_iva': item['condicion_iva'],
                    'zona': item['zona'],
                    'localidad': item['localidad']
                })
        
        # Sucursales
        if sucursales_sin_mapear:
            writer = csv.DictWriter(csvfile, fieldnames=['tipo', 'sucursal', 'deposito', 'uninegocio'])
            if not productos_sin_mapear and not clientes_sin_mapear:
                writer.writeheader()
            for item in sucursales_sin_mapear:
                writer.writerow({
                    'tipo': 'SUCURSAL',
                    'sucursal': item['sucursal'],
                    'deposito': item['deposito'],
                    'uninegocio': item['uninegocio']
                })
    
    print(f"✅ Reporte generado: {filename}")


def main():
    """Función principal."""
    print("🚀 Iniciando carga de mapeos SabioGo...\n")
    
    app = create_app()
    
    with app.app_context():
        try:
            # Productos
            codigos = extraer_codigos_productos()
            productos_sin_mapear = mapear_productos(codigos)
            print()
            
            # Clientes
            clientes = extraer_clientes()
            clientes_sin_mapear = mapear_clientes(clientes)
            print()
            
            # Sucursales
            sucursales = extraer_sucursales()
            sucursales_sin_mapear = mapear_sucursales(sucursales)
            print()
            
            # Generar reporte
            if productos_sin_mapear or clientes_sin_mapear or sucursales_sin_mapear:
                generar_reporte(productos_sin_mapear, clientes_sin_mapear, sucursales_sin_mapear)
            
            print("\n🎉 Proceso completado exitosamente!")
            print("\n📊 Resumen:")
            print(f"  • Productos sin mapear: {len(productos_sin_mapear)}")
            print(f"  • Clientes sin mapear: {len(clientes_sin_mapear)}")
            print(f"  • Sucursales sin mapear: {len(sucursales_sin_mapear)}")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
