# Bitacora SabioGo -> App360 (staging, carga y enlaces)

## Contexto
- SabioGo sigue como facturador legal. App360 complementa analitica y tesoreria.
- Importamos diarios los XLS de SabioGo: `ventas_globales.xls` y `compras_globales.xls`.
- Staging en PostgreSQL (VPS) sin constraint de unicidad, para permitir multiples lineas por comprobante.

## Linea de tiempo (VPS 2026-02-11)
1) Activar venv y generar migracion:
   - `source venv/bin/activate`
   - `alembic revision -m "add_sabiogo_staging"` → archivo: `migrations/versions/2671935051de_add_sabiogo_staging.py`
   - Se definieron tablas `stg_sabiogo_ventas` y `stg_sabiogo_compras` (ver estructura abajo).
2) Aplicar migracion con contexto Flask:
   - `FLASK_APP=app.py flask db upgrade`
3) Instalar dependencia para XLS:
   - `pip install "xlrd>=2.0.1"`
4) Cargar XLS a staging:
   - URI: `postgresql://app360user:2uxlzMbbQcxaqjsbKSY=@localhost:5432/app360`
   - Script pandas → to_sql con chunksize 200.
   - Se quitaron constraints únicas de staging para permitir duplicados: `ALTER TABLE stg_sabiogo_ventas DROP CONSTRAINT uq_stg_sabiogo_ventas_nro_tipo_fecha;` y análogo para compras.
5) Resultado de carga:
   - `stg_sabiogo_ventas`: 7,342 filas.
   - `stg_sabiogo_compras`: 493 filas.

## Estructura staging (ambas tablas)
- Clave: `id` bigint autoincrement.
- Campos fuente (28): rubro, fecha (timestamp), subrubro, codigo, modelo, producto, marca, comprobante, nro_comprob, cliente, condicion_iva, vendedor, deposito, uninegocio, forma_pago, kilos (float), cajas (float), dtos (float), neto (float), localidad, zona, sucursal, iva (float), moniva (float), tipo, subtot (float), numlispre (int), lisprec.
- Metadatos: fuente_archivo, fecha_import (default now), hash_archivo (null), estado (default 'cargado'), created_at, updated_at.
- Indices: fecha, codigo, vendedor, sucursal. (Se removio la unica por nro_comprob+tipo+fecha.)

## Tablas de negocio relevantes (resumen)
- Ventas:
  - `ventas`: fecha, cliente_id, producto_id, cantidad, precio_contrato/efectivo. FKs: clients, products. Indices: fecha, cliente, producto.
  - `sales`: lead_id, product_id, location_id, quantity, unit_price, status. FKs: leads, products, locations.
- Compras:
  - `purchase_orders`: product_id, quantity, unit_price, total_amount, order_date, expected_delivery_date, status, location_id, comprobante_numero, monto_total, instrumento_id?, tesoreria_movimiento_id?.
  - `purchase_order_items`: order_id, product_id, quantity.
  - `purchase_receipts`: purchase_order_id, product_id, location_id, quantity_received, received_at.
- Tesoreria:
  - `movimientos_caja`: tipo, monto, instrumento_id, arqueo_id?, usuario_id, referencia, cliente_proveedor.
  - `arqueos_caja`: fecha, turno, usuario_id, destino_id?, saldos y diferencias; constraint unica (fecha, turno).
  - `instrumentos_pago`, `destinos_arqueo` catálogos.
  - `cuenta_corriente_friar`, `pagos_friar`, `logs_cuenta_corriente_friar`, `logs_arqueo`.

## Mapeos y enlaces propuestos
- Producto: `stg.codigo` → `products.id` (crear tabla `sabiogo_product_map`).
- Cliente: `stg.cliente` texto → `clients.id` (opcional `sabiogo_client_map` con condicion_iva/localidad/zona).
- Sucursal/Deposito/Uninegocio: mapear a `locations` o dimension canal (`sabiogo_location_map`).
- Tesoreria:
  - Ventas contado → conciliacion con `movimientos_caja` (tipo ingreso) y `arqueos_caja`.
  - Compras/egresos → `movimientos_caja` (tipo egreso) y pagos Friar (`pagos_friar` → `cuenta_corriente_friar`).
  - Consignados: usar campo `tipo` en stg para cruces con pagos Friar.

## Riesgos y decisiones
- Constraint unica removida en staging: deduplicar en vistas/facts (agrupando por nro_comprob, fecha, tipo, codigo, subtot) antes de analitica.
- Sensibilidad de datos: no subir dumps al repo; usar backups fuera de git.
- Performance: indices actuales cubren fecha/codigo/vendedor/sucursal; agregar `nro_comprob` y `tipo` si se consultan mucho.

## Pasos siguientes recomendados
1) Crear tablas de mapeo (`sabiogo_product_map`, `sabiogo_client_map`, `sabiogo_location_map`).
2) Crear vistas/facts:
   - `vw_fact_ventas_sabiogo`, `vw_fact_compras_sabiogo` (join a mapas; cast numericos; dedup).
   - Vistas de conciliacion tesoreria: `vw_concilia_ventas_caja`, `vw_concilia_compras_pagos`.
   - `vw_margen` (margen por producto/canal/vendedor/sucursal).
3) Automatizar ingesta diaria + refresh de vistas materializadas si se usan.
4) Ajustar dashboards para leer de vistas (no de staging crudo).
