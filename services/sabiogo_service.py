"""Servicio de análisis de rentabilidad SabioGo."""

from repositories.sabiogo_repository import SabiogoRepository
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional


class SabiogoService:
    """Servicio para análisis de rentabilidad basado en datos SabioGo."""
    
    def __init__(self):
        self.repository = SabiogoRepository()
    
    def get_rentabilidad_producto(
        self,
        product_id: int,
        fecha_inicio: date,
        fecha_fin: date
    ) -> Dict:
        """
        Calcula la rentabilidad completa de un producto en un período.
        
        Args:
            product_id: ID del producto
            fecha_inicio: Fecha inicial del período
            fecha_fin: Fecha final del período
            
        Returns:
            Dict con rentabilidad detallada
        """
        # Obtener ventas y compras
        ventas = self.repository.get_ventas_por_producto(product_id, fecha_inicio, fecha_fin)
        compras = self.repository.get_compras_por_producto(product_id, fecha_inicio, fecha_fin)
        
        ingresos = ventas['ingresos_totales']
        costos = compras['costos_totales']
        margen_bruto = ingresos - costos
        margen_porcentual = (margen_bruto / ingresos * 100) if ingresos > 0 else 0
        
        return {
            'product_id': product_id,
            'periodo': {
                'inicio': fecha_inicio.isoformat(),
                'fin': fecha_fin.isoformat()
            },
            'ventas': {
                'ingresos_totales': ingresos,
                'kilos_totales': ventas['kilos_totales'],
                'cajas_totales': ventas['cajas_totales'],
                'num_transacciones': ventas['num_transacciones']
            },
            'compras': {
                'costos_totales': costos,
                'kilos_totales': compras['kilos_totales'],
                'costo_promedio': compras['costo_promedio'],
                'num_transacciones': compras['num_transacciones']
            },
            'rentabilidad': {
                'margen_bruto': margen_bruto,
                'margen_porcentual': margen_porcentual,
                'roi': (margen_bruto / costos * 100) if costos > 0 else 0
            }
        }
    
    def get_rentabilidad_por_categoria(
        self,
        categoria: str,
        fecha_inicio: date,
        fecha_fin: date
    ) -> List[Dict]:
        """
        Obtiene rentabilidad de todos los productos de una categoría.
        
        Returns:
            Lista de productos con su rentabilidad
        """
        return self.repository.get_rentabilidad_por_categoria(
            categoria,
            fecha_inicio,
            fecha_fin
        )
    
    def get_top_productos_margen(
        self,
        limit: int = 10,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None
    ) -> List[Dict]:
        """
        Obtiene los productos con mayor margen.
        
        Args:
            limit: Número de productos a retornar
            fecha_inicio: Fecha inicial (por defecto: hace 30 días)
            fecha_fin: Fecha final (por defecto: hoy)
            
        Returns:
            Lista de productos ordenados por margen descendente
        """
        if not fecha_fin:
            fecha_fin = date.today()
        if not fecha_inicio:
            fecha_inicio = fecha_fin - timedelta(days=30)
        
        return self.repository.get_top_productos_por_margen(
            limit,
            fecha_inicio,
            fecha_fin
        )
    
    def get_rentabilidad_por_sucursal(
        self,
        location_id: int,
        fecha_inicio: date,
        fecha_fin: date
    ) -> Dict:
        """
        Obtiene rentabilidad de una sucursal.
        """
        return self.repository.get_rentabilidad_por_sucursal(
            location_id,
            fecha_inicio,
            fecha_fin
        )
    
    def get_rentabilidad_resumen(
        self,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None
    ) -> Dict:
        """
        Obtiene resumen global de rentabilidad.
        
        Args:
            fecha_inicio: Fecha inicial (por defecto: hace 30 días)
            fecha_fin: Fecha final (por defecto: hoy)
            
        Returns:
            Dict con resumen de rentabilidad global
        """
        if not fecha_fin:
            fecha_fin = date.today()
        if not fecha_inicio:
            fecha_inicio = fecha_fin - timedelta(days=30)
        
        return self.repository.get_resumen_rentabilidad(fecha_inicio, fecha_fin)
    
    def registrar_carga(
        self,
        archivo_nombre: str,
        tipo_carga: str,
        hash_archivo: str,
        filas_insertadas: int,
        filas_duplicadas: int = 0,
        filas_sin_mapeo: int = 0,
        filas_error: int = 0,
        usuario_id: Optional[int] = None,
        observaciones: Optional[str] = None
    ):
        """Registra un log de carga de datos."""
        return self.repository.registrar_log_carga(
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
