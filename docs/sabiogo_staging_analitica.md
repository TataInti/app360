# Integracion SabioGo -> App360 (staging, analitica y tesoreria)

## Estado actual en VPS

- Tablas de staging cargadas desde SabioGo:
  - `stg_sabiogo_ventas`: 7,342 filas (xlsx `ventas_globales.xls`).
  - `stg_sabiogo_compras`: 493 filas (xlsx `compras_globales.xls`).
- Se removieron las constraints de unicidad para permitir multiples lineas con igual `(nro_comprob, tipo, fecha)` en staging.
- Dependencias instaladas en venv: `xlrd` para lectura de `.xls`.

## Estructura de tablas relevantes (produccion)

### Staging SabioGo
- `stg_sabiogo_ventas` y `stg_sabiogo_compras`
  - Clave: `id` (bigint). Indices en `fecha`, `codigo`, `vendedor`, `sucursal`.
  - 28 campos fuente: rubro, fecha (ts), subrubro, codigo, modelo, producto, marca, comprobante, nro_comprob, cliente, condicion_iva, vendedor, deposito, uninegocio, forma_pago, kilos, cajas, dtos, neto, localidad, zona, sucursal, iva, moniva, tipo, subtot, numlispre (int), lisprec, + metadatos (fuente_archivo, fecha_import, hash_archivo, estado, created_at, updated_at).

### Ventas y pipeline comercial
- `ventas`: agregada a nivel producto/cliente/fecha con cantidades y precios contrato/efectivo.
  - FK: `cliente_id -> clients`, `producto_id -> products`.
  - Indices: fecha, cliente, producto.
- `sales`: ventas asociadas a leads (pipeline) con precio unitario y cantidad.
  - FK: `lead_id -> leads`, `product_id -> products`, `location_id -> locations`.
  - Indices: pkey y fks.

### Compras / Abastecimiento
- `purchase_orders`: ordenes con `product_id`, `quantity`, `unit_price`, `total_amount`, fechas (order/expected), `status`, `location_id`, `comprobante_numero`, `monto_total`, opcionales `instrumento_id`, `tesoreria_movimiento_id`.
  - FK: `product_id -> products`, `location_id -> locations`, `instrumento_id -> instrumentos_pago`, `tesoreria_movimiento_id -> movimientos_caja`.
  - Indices: order_date, expected_delivery_date, status, location.
- `purchase_order_items`: items adicionales por orden (order_id, product_id, quantity).
- `purchase_receipts`: recepciones por orden/producto/location con `received_at` y cantidad.

### Tesoreria
- `movimientos_caja`: movimientos de dinero con `tipo` (ingreso/egreso), `monto`, `instrumento_id`, `arqueo_id`, `usuario_id`, `cliente_proveedor`, `referencia`.
  - FK: `instrumento_id -> instrumentos_pago`, `arqueo_id -> arqueos_caja`, `usuario_id -> users`.
  - Indices: fecha_hora, tipo, instrumento.
- `arqueos_caja`: cierres de caja (fecha, turno, usuario, destino opcional, saldos, diferencia, observaciones).
  - FK: `usuario_id`, `destino_id -> destinos_arqueo`, `editado_por_id -> users`.
  - Constraint unica (fecha, turno).
- `instrumentos_pago`: catalogo de medios de pago (nombre unico, activo).
- `destinos_arqueo`: destinos de dinero (nombre unico, activo).
- `cuenta_corriente_friar`: saldo y observaciones por proveedor Friar, con auditoria (`editado_por_id`).
- `pagos_friar`: pagos aplicados a cuenta corriente Friar (fecha, monto, instrumento, descripcion, referencia, usuario opcional).
- Logs de auditoria:
  - `logs_cuenta_corriente_friar` (campos_anteriores/nuevos json, justificacion, usuario, fecha_edicion).
  - `logs_arqueo` (campos_anteriores/nuevos json, justificacion, usuario, fecha_edicion).

## Relaciones clave para analitica y visualizacion

1) **Staging SabioGo -> Productos/Clientes/Sucursales**
   - `codigo` (stg) debe mapearse a `products.id` (requiere tabla de mapeo o normalizar `codigo` en products).
   - `cliente` en stg es texto; para analitica se sugiere dimension `dim_cliente_sabiogo` o mapeo a `clients` si existe matching por nombre/condicion_iva.
   - `sucursal`/`deposito`/`uninegocio` deberian mapearse a `locations` o a una dimension de canal/ubicacion; hoy `ventas` y `sales` usan `locations` en algunos flujos.

2) **Costos**
   - `stg_sabiogo_compras.neto` + `iva`/`moniva` permiten costo total por linea; para margen se debe alinear con el mismo `codigo`/`producto` de ventas.
   - Si las compras incluyen consignacion (`tipo`) separar costos consumidos vs consignados.

3) **Ingresos**
   - `stg_sabiogo_ventas.subtot` y `neto` por linea; `kilos` y `cajas` habilitan analisis por volumen.
   - `forma_pago` y `tipo` util para reconciliar con tesoreria (efectivo, cta cte, consignado).

4) **Tesoreria linkage**
   - `purchase_orders.tesoreria_movimiento_id` ya enlaza ordenes con `movimientos_caja` (egresos por compra).
   - Pagos Friar: `pagos_friar` enlazado a `cuenta_corriente_friar` e `instrumentos_pago`; usar para conciliacion con costos consignados de SabioGo.
   - `movimientos_caja` registra `cliente_proveedor` texto; puede cruzarse con `cliente`/`proveedor` de stg para identificar matching manual.

5) **Indices y volumen**
   - Staging ya indexa `fecha`, `codigo`, `vendedor`, `sucursal`. Para analitica diaria, crear vistas materializadas sobre joins con `products`, `locations`, `clients`.

## Sugerencia de modelo analitico (capas)

- **Capa staging (ya creada):** `stg_sabiogo_ventas`, `stg_sabiogo_compras`.
- **Capa de conformado (dimensiones/puentes):**
  - `dim_producto`: mapear `codigo` SabioGo -> `products.id`, almacenar marca/modelo/lisprec actual.
  - `dim_cliente_sabiogo`: normalizar `cliente`, `condicion_iva`, `zona`, `localidad`.
  - `dim_sucursal_canal`: derivar de `sucursal`/`deposito`/`uninegocio` hacia `locations`/canal.
- **Capa fact:**
  - `fact_ventas_sabiogo`: granuralidad linea de comprobante, con claves a dims y metricas (kilos, cajas, neto, subtot, iva, moniva, dtos, lista_precios, forma_pago, tipo, fecha).
  - `fact_costos_sabiogo`: similar para compras/costos.
- **Capa tesoreria:** vistas de conciliacion:
  - `vw_concilia_ventas_caja`: cruza `fact_ventas_sabiogo` (por forma_pago/sucursal/fecha) con `movimientos_caja` (ingresos) y `arqueos_caja`.
  - `vw_concilia_compras_pagos`: cruza `fact_costos_sabiogo` con `movimientos_caja` (egresos) y `pagos_friar`/`cuenta_corriente_friar`.
  - `vw_margen`: `fact_ventas_sabiogo` vs `fact_costos_sabiogo` por `producto`/`sucursal`/`canal`/`vendedor`.

## Ajustes recomendados en visualizacion/analitica

1) **Mapeos obligatorios**
   - Crear tabla `sabiogo_product_map (codigo text primary key, product_id int, marca, modelo, activo, updated_at)`.
   - Opcional: `sabiogo_client_map (cliente text, client_id int, condicion_iva, zona, localidad)`.
   - `sabiogo_location_map` para `sucursal`/`deposito` -> `locations.id` + canal.

2) **Vistas de consumo**
   - `vw_fact_ventas_sabiogo` y `vw_fact_compras_sabiogo` con joins a mapas y campos derivados (margen, precio_promedio, costo_promedio por kilo/caja).
   - `vw_kpis_tesoreria` para dashboard: ingresos/egresos diarios, diferencia arqueo, cobertura de pagos vs consignacion Friar.

3) **Conciliacion con tesoreria**
   - Reglas por `forma_pago`/`tipo`: eg. `Contado` -> `movimientos_caja` tipo ingreso; `Cta.Cte` -> debe impactar en cuentas por cobrar (no modelado aún) o en arqueo como pendiente.
   - Para costos consignados (`tipo` = CONSIGNADO/NO CONSIGNADOS) reconciliar con `pagos_friar` y `cuenta_corriente_friar`.

4) **Calidad de datos**
   - Deduplicacion: dado que se quitó la constraint unica en staging, usar vistas que agrupen por `(nro_comprob, tipo, fecha, codigo, subtot)` para evitar doble conteo.
   - Validar `fecha` no nula; cast de float a numeric en vistas.

5) **Performance**
   - Considerar indices adicionales en staging si se usan filtros por `nro_comprob`, `tipo`, `forma_pago`.
   - Para BI, materializar vistas diarias con `refresh` tras la importacion diaria.

## Pasos siguientes

1) Mantener staging sin constraint; crear vistas/facts que agrupen y deduzcan duplicados.
2) Crear tablas de mapeo (producto/cliente/sucursal) y scripts de carga inicial desde catalogos actuales (`products`, `locations`, `clients`).
3) Construir vistas de analitica (ventas, costos, margen, conciliacion tesoreria) apoyadas en los mapas.
4) Ajustar dashboards para leer de vistas nuevas (no directo de staging) y exponer KPIs: margen por linea/canal, cobertura consignacion/pagos, diferencia arqueo vs ventas contado.
5) Automatizar ingesta diaria (UI + cron) y `refresh` de vistas materializadas si se usan.
