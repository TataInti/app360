"""Repository para operaciones de análisis SabioGo."""

from models import db
from models.sabiogo import (
    StgSabiogoVentas,
    StgSabiogoCompras,
    SabiogoProductMap,
    SabiogoClientMap,
    SabiogoLocationMap,
    LogSabiogoCarga
)
from sqlalchemy import func, text
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple


class SabiogoRepository:
    """Repository para consultas de análisis de rentabilidad SabioGo."""
    
    def get_ventas_por_producto(
        self, 
        product_id: int, 
        fecha_inicio: date, 
        fecha_fin: date
    ) -> Dict:
        """
        Obtiene ventas totales de un producto en un período.
        
        Returns:
            Dict con ingresos_totales, unidades_vendidas, kilos_totales
        """
        # Query que une staging con mapeos
        result = db.session.query(
            func.sum(StgSabiogoVentas.subtot).label('ingresos_totales'),
            func.sum(StgSabiogoVentas.kilos).label('kilos_totales'),
            func.sum(StgSabiogoVentas.cajas).label('cajas_totales'),
            func.count(StgSabiogoVentas.id).label('num_transacciones')
        ).join(
            SabiogoProductMap,
            StgSabiogoVentas.codigo == SabiogoProductMap.codigo
        ).filter(
            SabiogoProductMap.product_id == product_id,
            SabiogoProductMap.activo == True,
            StgSabiogoVentas.estado == 'procesado',
            StgSabiogoVentas.fecha >= fecha_inicio,
            StgSabiogoVentas.fecha <= fecha_fin
        ).first()
        
        return {
            'ingresos_totales': float(result.ingresos_totales or 0),
            'kilos_totales': float(result.kilos_totales or 0),
            'cajas_totales': float(result.cajas_totales or 0),
            'num_transacciones': result.num_transacciones or 0
        }
    
    def get_compras_por_producto(
        self,
        product_id: int,
        fecha_inicio: date,
        fecha_fin: date
    ) -> Dict:
        """
        Obtiene compras totales de un producto en un período (costo promedio ponderado).
        
        Returns:
            Dict con costos_totales, unidades_compradas, costo_promedio
        """
        result = db.session.query(
            func.sum(StgSabiogoCompras.subtot).label('costos_totales'),
            func.sum(StgSabiogoCompras.kilos).label('kilos_totales'),
            func.sum(StgSabiogoCompras.cajas).label('cajas_totales'),
            func.count(StgSabiogoCompras.id).label('num_transacciones')
        ).join(
            SabiogoProductMap,
            StgSabiogoCompras.codigo == SabiogoProductMap.codigo
        ).filter(
            SabiogoProductMap.product_id == product_id,
            SabiogoProductMap.activo == True,
            StgSabiogoCompras.estado == 'procesado',
            StgSabiogoCompras.fecha >= fecha_inicio,
            StgSabiogoCompras.fecha <= fecha_fin
        ).first()
        
        costos_totales = float(result.costos_totales or 0)
        kilos_totales = float(result.kilos_totales or 0)
        
        return {
            'costos_totales': costos_totales,
            'kilos_totales': kilos_totales,
            'cajas_totales': float(result.cajas_totales or 0),
            'costo_promedio': costos_totales / kilos_totales if kilos_totales > 0 else 0,
            'num_transacciones': result.num_transacciones or 0
        }
    
    def get_rentabilidad_por_categoria(
        self,
        categoria: str,
        fecha_inicio: date,
        fecha_fin: date
    ) -> List[Dict]:
        """
        Obtiene rentabilidad de todos los productos de una categoría.
        """
        # Usar vista materializada si existe, sino query directo
        query = text("""
            SELECT 
                p.id as product_id,
                p.name as producto,
                p.sku,
                COALESCE(SUM(v.subtot), 0) as ingresos,
                COALESCE(SUM(c.subtot), 0) as costos,
                COALESCE(SUM(v.subtot), 0) - COALESCE(SUM(c.subtot), 0) as margen_bruto
            FROM products p
            LEFT JOIN sabiogo_product_map pm ON p.id = pm.product_id AND pm.activo = true
            LEFT JOIN stg_sabiogo_ventas v ON pm.codigo = v.codigo 
                AND v.estado = 'procesado' 
                AND v.fecha BETWEEN :fecha_inicio AND :fecha_fin
            LEFT JOIN stg_sabiogo_compras c ON pm.codigo = c.codigo 
                AND c.estado = 'procesado' 
                AND c.fecha BETWEEN :fecha_inicio AND :fecha_fin
            WHERE p.category = :categoria
            GROUP BY p.id, p.name, p.sku
            HAVING COALESCE(SUM(v.subtot), 0) > 0 OR COALESCE(SUM(c.subtot), 0) > 0
            ORDER BY margen_bruto DESC
        """)
        
        result = db.session.execute(
            query,
            {
                'categoria': categoria,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin
            }
        )
        
        return [
            {
                'product_id': row.product_id,
                'producto': row.producto,
                'sku': row.sku,
                'ingresos': float(row.ingresos),
                'costos': float(row.costos),
                'margen_bruto': float(row.margen_bruto),
                'margen_porcentual': (float(row.margen_bruto) / float(row.ingresos) * 100) if float(row.ingresos) > 0 else 0
            }
            for row in result
        ]
    
    def get_top_productos_por_margen(
        self,
        limit: int,
        fecha_inicio: date,
        fecha_fin: date
    ) -> List[Dict]:
        """
        Obtiene los productos con mayor margen en el período.
        """
        query = text("""
            SELECT 
                p.id as product_id,
                p.name as producto,
                p.sku,
                p.category,
                COALESCE(SUM(v.subtot), 0) as ingresos,
                COALESCE(SUM(c.subtot), 0) as costos,
                COALESCE(SUM(v.subtot), 0) - COALESCE(SUM(c.subtot), 0) as margen_bruto,
                COALESCE(SUM(v.kilos), 0) as kilos_vendidos
            FROM products p
            INNER JOIN sabiogo_product_map pm ON p.id = pm.product_id AND pm.activo = true
            LEFT JOIN stg_sabiogo_ventas v ON pm.codigo = v.codigo 
                AND v.estado = 'procesado' 
                AND v.fecha BETWEEN :fecha_inicio AND :fecha_fin
            LEFT JOIN stg_sabiogo_compras c ON pm.codigo = c.codigo 
                AND c.estado = 'procesado' 
                AND c.fecha BETWEEN :fecha_inicio AND :fecha_fin
            GROUP BY p.id, p.name, p.sku, p.category
            HAVING COALESCE(SUM(v.subtot), 0) > 0
            ORDER BY margen_bruto DESC
            LIMIT :limit
        """)
        
        result = db.session.execute(
            query,
            {
                'limit': limit,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin
            }
        )
        
        return [
            {
                'product_id': row.product_id,
                'producto': row.producto,
                'sku': row.sku,
                'category': row.category,
                'ingresos': float(row.ingresos),
                'costos': float(row.costos),
                'margen_bruto': float(row.margen_bruto),
                'margen_porcentual': (float(row.margen_bruto) / float(row.ingresos) * 100) if float(row.ingresos) > 0 else 0,
                'kilos_vendidos': float(row.kilos_vendidos)
            }
            for row in result
        ]
    
    def get_rentabilidad_por_sucursal(
        self,
        location_id: int,
        fecha_inicio: date,
        fecha_fin: date
    ) -> Dict:
        """
        Obtiene rentabilidad total de una sucursal.
        """
        query = text("""
            SELECT 
                COALESCE(SUM(v.subtot), 0) as ingresos,
                COALESCE(SUM(v.kilos), 0) as kilos_vendidos,
                COUNT(DISTINCT pm.product_id) as productos_diferentes
            FROM stg_sabiogo_ventas v
            INNER JOIN sabiogo_location_map lm ON v.sucursal = lm.sucursal
            LEFT JOIN sabiogo_product_map pm ON v.codigo = pm.codigo AND pm.activo = true
            WHERE lm.location_id = :location_id
                AND lm.activo = true
                AND v.estado = 'procesado'
                AND v.fecha BETWEEN :fecha_inicio AND :fecha_fin
        """)
        
        result = db.session.execute(
            query,
            {
                'location_id': location_id,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin
            }
        ).first()
        
        return {
            'ingresos': float(result.ingresos) if result else 0,
            'kilos_vendidos': float(result.kilos_vendidos) if result else 0,
            'productos_diferentes': result.productos_diferentes if result else 0
        }
    
    def get_resumen_rentabilidad(
        self,
        fecha_inicio: date,
        fecha_fin: date
    ) -> Dict:
        """
        Obtiene resumen global de rentabilidad.
        """
        query = text("""
            WITH totales AS (
                SELECT
                    (SELECT COALESCE(SUM(v.subtot), 0)
                     FROM stg_sabiogo_ventas v
                     WHERE v.estado = 'procesado'
                       AND v.fecha BETWEEN :fecha_inicio AND :fecha_fin) AS total_ingresos,
                    (SELECT COALESCE(SUM(c.subtot), 0)
                     FROM stg_sabiogo_compras c
                     WHERE c.estado = 'procesado'
                       AND c.fecha BETWEEN :fecha_inicio AND :fecha_fin) AS total_costos
            ),
            mapeados AS (
                SELECT
                    COALESCE(SUM(v.subtot), 0) AS ingresos_mapeados,
                    COALESCE(SUM(c.subtot), 0) AS costos_mapeados,
                    COUNT(DISTINCT pm.product_id) AS productos_activos_mapeados
                FROM sabiogo_product_map pm
                LEFT JOIN stg_sabiogo_ventas v ON pm.codigo = v.codigo
                    AND v.estado = 'procesado'
                    AND v.fecha BETWEEN :fecha_inicio AND :fecha_fin
                LEFT JOIN stg_sabiogo_compras c ON pm.codigo = c.codigo
                    AND c.estado = 'procesado'
                    AND c.fecha BETWEEN :fecha_inicio AND :fecha_fin
                WHERE pm.activo = true
                  AND pm.product_id IS NOT NULL
            )
            SELECT
                t.total_ingresos,
                t.total_costos,
                m.ingresos_mapeados,
                m.costos_mapeados,
                m.productos_activos_mapeados
            FROM totales t
            CROSS JOIN mapeados m
        """)
        
        result = db.session.execute(
            query,
            {
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin
            }
        ).first()
        
        total_ingresos = float(result.total_ingresos) if result else 0
        total_costos = float(result.total_costos) if result else 0
        ingresos_mapeados = float(getattr(result, 'ingresos_mapeados', 0) or 0) if result else 0
        costos_mapeados = float(getattr(result, 'costos_mapeados', 0) or 0) if result else 0
        productos_activos_mapeados = int(getattr(result, 'productos_activos_mapeados', 0) or 0) if result else 0
        
        return {
            'total_ingresos': total_ingresos,
            'total_costos': total_costos,
            'margen_bruto': total_ingresos - total_costos,
            'margen_porcentual': ((total_ingresos - total_costos) / total_ingresos * 100) if total_ingresos > 0 else 0,
            # Compatibilidad: este campo se usa en BI como métrica de productos con mapeo.
            'productos_activos': productos_activos_mapeados,
            # Métricas adicionales (no rompen contratos existentes)
            'ingresos_mapeados': ingresos_mapeados,
            'costos_mapeados': costos_mapeados,
            'productos_activos_mapeados': productos_activos_mapeados,
        }
    
    def registrar_log_carga(
        self,
        archivo_nombre: str,
        tipo_carga: str,
        hash_archivo: str,
        filas_insertadas: int,
        filas_duplicadas: int,
        filas_sin_mapeo: int,
        filas_error: int,
        usuario_id: Optional[int] = None,
        observaciones: Optional[str] = None
    ) -> LogSabiogoCarga:
        """Registra un log de carga de datos."""
        log = LogSabiogoCarga(
            archivo_nombre=archivo_nombre,
            tipo_carga=tipo_carga,
            hash_archivo=hash_archivo,
            filas_insertadas=filas_insertadas,
            filas_duplicadas=filas_duplicadas,
            filas_sin_mapeo=filas_sin_mapeo,
            filas_error=filas_error,
            usuario_id=usuario_id,
            observaciones=observaciones
        )
        db.session.add(log)
        db.session.commit()
        return log
