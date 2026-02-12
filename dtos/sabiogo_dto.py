"""Data Transfer Objects para análisis de rentabilidad SabioGo."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Dict, Any


@dataclass
class RentabilidadProductoDTO:
    """DTO para rentabilidad de un producto."""
    
    product_id: int
    sku: Optional[str]
    name: str
    periodo_inicio: date
    periodo_fin: date
    
    # Ventas
    ingresos_totales: float
    kilos_vendidos: float
    cajas_vendidas: float
    transacciones_venta: int
    
    # Compras
    costos_totales: float
    kilos_comprados: float
    costo_promedio_kg: float
    transacciones_compra: int
    
    # Rentabilidad
    margen_bruto: float
    margen_porcentual: float
    roi: float
    
    @classmethod
    def from_service_result(cls, data: Dict[str, Any], product_name: str, product_sku: Optional[str] = None):
        """Crea DTO desde resultado del servicio."""
        periodo = data.get('periodo', {})
        ventas = data.get('ventas', {})
        compras = data.get('compras', {})
        rentabilidad = data.get('rentabilidad', {})
        
        return cls(
            product_id=data.get('product_id'),
            sku=product_sku,
            name=product_name,
            periodo_inicio=date.fromisoformat(periodo.get('inicio')) if isinstance(periodo.get('inicio'), str) else periodo.get('inicio'),
            periodo_fin=date.fromisoformat(periodo.get('fin')) if isinstance(periodo.get('fin'), str) else periodo.get('fin'),
            ingresos_totales=ventas.get('ingresos_totales', 0),
            kilos_vendidos=ventas.get('kilos_totales', 0),
            cajas_vendidas=ventas.get('cajas_totales', 0),
            transacciones_venta=ventas.get('num_transacciones', 0),
            costos_totales=compras.get('costos_totales', 0),
            kilos_comprados=compras.get('kilos_totales', 0),
            costo_promedio_kg=compras.get('costo_promedio', 0),
            transacciones_compra=compras.get('num_transacciones', 0),
            margen_bruto=rentabilidad.get('margen_bruto', 0),
            margen_porcentual=rentabilidad.get('margen_porcentual', 0),
            roi=rentabilidad.get('roi', 0)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte DTO a diccionario."""
        return {
            'product_id': self.product_id,
            'sku': self.sku,
            'name': self.name,
            'periodo': {
                'inicio': self.periodo_inicio.isoformat(),
                'fin': self.periodo_fin.isoformat()
            },
            'ventas': {
                'ingresos_totales': self.ingresos_totales,
                'kilos_vendidos': self.kilos_vendidos,
                'cajas_vendidas': self.cajas_vendidas,
                'transacciones': self.transacciones_venta
            },
            'compras': {
                'costos_totales': self.costos_totales,
                'kilos_comprados': self.kilos_comprados,
                'costo_promedio_kg': self.costo_promedio_kg,
                'transacciones': self.transacciones_compra
            },
            'rentabilidad': {
                'margen_bruto': self.margen_bruto,
                'margen_porcentual': self.margen_porcentual,
                'roi': self.roi
            }
        }


@dataclass
class RentabilidadResumenDTO:
    """DTO para resumen global de rentabilidad."""
    
    periodo_inicio: date
    periodo_fin: date
    total_ingresos: float
    total_costos: float
    margen_bruto: float
    margen_porcentual: float
    productos_activos: int
    
    @classmethod
    def from_service_result(cls, data: Dict[str, Any], periodo_inicio: date, periodo_fin: date):
        """Crea DTO desde resultado del servicio."""
        return cls(
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            total_ingresos=data.get('total_ingresos', 0),
            total_costos=data.get('total_costos', 0),
            margen_bruto=data.get('margen_bruto', 0),
            margen_porcentual=data.get('margen_porcentual', 0),
            productos_activos=data.get('productos_activos', 0)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte DTO a diccionario."""
        return {
            'periodo': {
                'inicio': self.periodo_inicio.isoformat(),
                'fin': self.periodo_fin.isoformat()
            },
            'total_ingresos': self.total_ingresos,
            'total_costos': self.total_costos,
            'margen_bruto': self.margen_bruto,
            'margen_porcentual': self.margen_porcentual,
            'productos_activos': self.productos_activos
        }


@dataclass
class ProductoTopMargenDTO:
    """DTO para productos en el top de márgenes."""
    
    product_id: int
    sku: Optional[str]
    producto: str
    category: Optional[str]
    ingresos: float
    costos: float
    margen_bruto: float
    margen_porcentual: float
    kilos_vendidos: float
    
    @classmethod
    def from_query_result(cls, row: Dict[str, Any]):
        """Crea DTO desde resultado de query."""
        return cls(
            product_id=row.get('product_id'),
            sku=row.get('sku'),
            producto=row.get('producto'),
            category=row.get('category'),
            ingresos=row.get('ingresos', 0),
            costos=row.get('costos', 0),
            margen_bruto=row.get('margen_bruto', 0),
            margen_porcentual=row.get('margen_porcentual', 0),
            kilos_vendidos=row.get('kilos_vendidos', 0)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte DTO a diccionario."""
        return {
            'product_id': self.product_id,
            'sku': self.sku,
            'producto': self.producto,
            'category': self.category,
            'ingresos': self.ingresos,
            'costos': self.costos,
            'margen_bruto': self.margen_bruto,
            'margen_porcentual': self.margen_porcentual,
            'kilos_vendidos': self.kilos_vendidos
        }


@dataclass
class RentabilidadCategoriaDTO:
    """DTO para rentabilidad por categoría."""
    
    categoria: str
    productos: list = field(default_factory=list)
    total_ingresos: float = 0
    total_costos: float = 0
    margen_bruto: float = 0
    margen_porcentual: float = 0
    
    def agregar_producto(self, producto_data: Dict[str, Any]):
        """Agrega un producto y actualiza totales."""
        self.productos.append(producto_data)
        self.total_ingresos += producto_data.get('ingresos', 0)
        self.total_costos += producto_data.get('costos', 0)
        self.margen_bruto = self.total_ingresos - self.total_costos
        self.margen_porcentual = (
            (self.margen_bruto / self.total_ingresos * 100) 
            if self.total_ingresos > 0 else 0
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte DTO a diccionario."""
        return {
            'categoria': self.categoria,
            'productos': self.productos,
            'resumen': {
                'total_ingresos': self.total_ingresos,
                'total_costos': self.total_costos,
                'margen_bruto': self.margen_bruto,
                'margen_porcentual': self.margen_porcentual,
                'numero_productos': len(self.productos)
            }
        }
