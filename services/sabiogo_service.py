"""Servicio de análisis de rentabilidad SabioGo."""

from repositories.sabiogo_repository import SabiogoRepository
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import unicodedata

from models import db
from models.hr.employee import Employee
from models.hr.goal import Goal
from models.sabiogo import StgSabiogoVentas
from sqlalchemy import text


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
        observaciones: Optional[str] = None,
        auto_commit: bool = True,
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
            observaciones=observaciones,
            auto_commit=auto_commit,
        )

    def refresh_facts(self) -> Dict:
        """Promueve staging y refresca las vistas materializadas SabioGo."""
        try:
            promoted_ventas = db.session.execute(text("""
                UPDATE stg_sabiogo_ventas
                SET estado = 'procesado'
                WHERE estado IN ('cargado', 'pendiente')
            """)).rowcount
            promoted_compras = db.session.execute(text("""
                UPDATE stg_sabiogo_compras
                SET estado = 'procesado'
                WHERE estado IN ('cargado', 'pendiente')
            """)).rowcount
            db.session.commit()

            try:
                with db.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
                    conn.execute(text('REFRESH MATERIALIZED VIEW CONCURRENTLY fact_ventas_sabiogo'))
                    conn.execute(text('REFRESH MATERIALIZED VIEW CONCURRENTLY fact_costos_sabiogo'))
            except Exception:
                db.session.execute(text('REFRESH MATERIALIZED VIEW fact_ventas_sabiogo'))
                db.session.execute(text('REFRESH MATERIALIZED VIEW fact_costos_sabiogo'))
                db.session.commit()

            return {
                'mensaje': 'Vistas materializadas actualizadas',
                'staging_promovidos': {
                    'ventas': int(promoted_ventas or 0),
                    'compras': int(promoted_compras or 0),
                },
            }
        except Exception:
            db.session.rollback()
            raise

    def get_resumen_pre_fac(self, fecha_corte: Optional[date] = None) -> Dict:
        """Retorna métrica global Pre/Fac acumulada al corte."""
        if not fecha_corte:
            fecha_corte = date.today()
        return self.repository.get_resumen_pre_fac_global(fecha_corte)

    def get_detalle_ventas_pre(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        vendedor: Optional[str] = None,
        cliente: Optional[str] = None,
        producto: Optional[str] = None,
        limit: int = 500,
    ) -> Dict:
        """Retorna detalle comercial basado exclusivamente en PRE."""
        return self.repository.get_detalle_ventas_pre(
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            vendedor=vendedor,
            cliente=cliente,
            producto=producto,
            limit=limit,
        )

    @staticmethod
    def _normalizar_texto(value: Optional[str]) -> str:
        if not value:
            return ""
        base = unicodedata.normalize("NFKD", value)
        ascii_text = "".join(ch for ch in base if not unicodedata.combining(ch))
        return " ".join(ascii_text.lower().strip().split())

    def sincronizar_objetivos_pre(self, periodo: Optional[str] = None) -> Dict:
        """
        Actualiza Goal.current_value según ventas PRE por vendedor y período.
        Mantiene target_value manual.
        """
        if not periodo:
            periodo = datetime.now().strftime("%Y-%m")

        try:
            anio, mes = periodo.split("-")
            fecha_inicio = date(int(anio), int(mes), 1)
        except Exception:
            raise ValueError("Formato de periodo inválido. Use YYYY-MM")

        if fecha_inicio.month == 12:
            fecha_fin = date(fecha_inicio.year + 1, 1, 1) - timedelta(days=1)
        else:
            fecha_fin = date(fecha_inicio.year, fecha_inicio.month + 1, 1) - timedelta(days=1)

        ventas_por_vendedor = db.session.query(
            StgSabiogoVentas.vendedor,
            db.func.coalesce(db.func.sum(StgSabiogoVentas.subtot), 0).label("monto_pre"),
        ).filter(
            StgSabiogoVentas.estado == "procesado",
            db.func.coalesce(db.func.upper(db.func.trim(StgSabiogoVentas.comprobante)), "") == "PRE",
            StgSabiogoVentas.fecha >= fecha_inicio,
            StgSabiogoVentas.fecha <= fecha_fin,
            StgSabiogoVentas.vendedor.isnot(None),
        ).group_by(
            StgSabiogoVentas.vendedor,
        ).all()

        empleados = Employee.query.filter(Employee.is_active == True).all()
        empleados_por_nombre = {
            self._normalizar_texto(emp.full_name): emp
            for emp in empleados
            if emp.full_name
        }

        montos_por_employee_id: Dict[int, float] = {}
        vendedores_sin_mapeo: List[str] = []

        for row in ventas_por_vendedor:
            vendedor_raw = (row.vendedor or "").strip()
            vendedor_norm = self._normalizar_texto(vendedor_raw)
            monto = float(row.monto_pre or 0)

            empleado = empleados_por_nombre.get(vendedor_norm)

            if not empleado and vendedor_norm:
                for emp in empleados:
                    full_name = self._normalizar_texto(emp.full_name)
                    if vendedor_norm in full_name or full_name in vendedor_norm:
                        empleado = emp
                        break

            if not empleado:
                if vendedor_raw:
                    vendedores_sin_mapeo.append(vendedor_raw)
                continue

            montos_por_employee_id[empleado.id] = montos_por_employee_id.get(empleado.id, 0.0) + monto

        objetivos = Goal.query.filter(Goal.period == periodo).all()
        objetivos_actualizados = 0

        for objetivo in objetivos:
            nuevo_valor = float(montos_por_employee_id.get(objetivo.employee_id, 0.0))
            objetivo.current_value = nuevo_valor
            objetivos_actualizados += 1

        db.session.commit()

        return {
            "periodo": periodo,
            "objetivos_actualizados": objetivos_actualizados,
            "vendedores_en_pre": len(ventas_por_vendedor),
            "vendedores_sin_mapeo": sorted(set(vendedores_sin_mapeo)),
        }
