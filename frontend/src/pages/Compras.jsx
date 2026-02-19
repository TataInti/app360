// frontend/src/pages/Compras.jsx
import React, { useMemo, useState, useEffect } from 'react';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
} from 'chart.js';
import apiService from '../services/api';

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const PERIODS = [
  { key: '7', label: '7d' },
  { key: '15', label: '15d' },
  { key: '30', label: '30d' },
  { key: 'ytd', label: 'YTD' },
];

function money(v) {
  const n = Number(v || 0);
  return (
    '$' +
    (Number.isFinite(n) ? n : 0).toLocaleString('es-AR', {
      maximumFractionDigits: 0,
    })
  );
}

function Compras() {
  const [purchases, setPurchases] = useState([]);
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [overview, setOverview] = useState(null);
  const [period, setPeriod] = useState('30');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    supplier_id: '',
    product_id: '',
    quantity: '',
    unit_price: '',
    total_amount: '',
    order_date: new Date().toISOString().split('T')[0],
    expected_delivery_date: '',
    status: 'pendiente',
    notes: ''
  });

  useEffect(() => {
    loadData();
  }, [period]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [purchasesData, productsData, overviewData] = await Promise.all([
        apiService.getPurchases(),
        apiService.getProducts(),
        apiService.getComprasOverview(period),
      ]);
      setPurchases(purchasesData?.items || []);
      setProducts(productsData?.items || []);
      setOverview(overviewData || null);
      // For now, we'll use a simple supplier list - in a real app this would come from API
      setSuppliers([
        { id: 1, name: 'Proveedor A' },
        { id: 2, name: 'Proveedor B' },
        { id: 3, name: 'Proveedor C' }
      ]);
    } catch (err) {
      setError('Error al cargar compras. Verifica que el backend esté arriba y que el endpoint /api/compras no esté en error.');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  const calculateTotal = () => {
    const quantity = parseFloat(formData.quantity) || 0;
    const unitPrice = parseFloat(formData.unit_price) || 0;
    return (quantity * unitPrice).toFixed(2);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const purchaseData = {
        ...formData,
        quantity: parseInt(formData.quantity),
        unit_price: parseFloat(formData.unit_price),
        total_amount: parseFloat(calculateTotal())
      };
      await apiService.createPurchase(purchaseData);
      setFormData({
        supplier_id: '',
        product_id: '',
        quantity: '',
        unit_price: '',
        total_amount: '',
        order_date: new Date().toISOString().split('T')[0],
        expected_delivery_date: '',
        status: 'pendiente',
        notes: ''
      });
      setShowForm(false);
      loadData();
    } catch (err) {
      setError('Error al crear la orden de compra. Si ves 401, iniciá sesión para obtener token JWT.');
      console.error('Error creating purchase:', err);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const getProductName = (productId) => {
    const product = products.find(p => p.id === productId);
    return product ? product.name : 'Producto desconocido';
  };

  const getSupplierName = (supplierId) => {
    const supplier = suppliers.find(s => s.id === supplierId);
    return supplier ? supplier.name : 'Proveedor desconocido';
  };

  const estadoChart = useMemo(() => {
    const series = overview?.series?.orders_por_estado || {};
    const labels = Object.keys(series);
    const values = Object.values(series);
    return {
      data: {
        labels,
        datasets: [
          {
            label: 'Órdenes',
            data: values,
            backgroundColor: 'rgba(59, 130, 246, 0.25)',
            borderColor: 'rgba(59, 130, 246, 1)',
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    };
  }, [overview]);

  if (loading) {
    return <div className="loading">Cargando órdenes de compra...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="compras-page">
      <div className="page-header">
        <h1>Gestión de Compras</h1>
        <div className="btn-group" role="group" aria-label="Período" style={{ marginLeft: 12 }}>
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              className={`btn ${period === p.key ? 'btn-primary' : 'btn-outline-primary'}`}
              onClick={() => setPeriod(p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? 'Cancelar' : 'Nueva Orden'}
        </button>
      </div>

      {overview && (
        <>
          <div className="text-muted small" style={{ marginTop: 8 }}>
            Período: {overview.desde || '-'} → {overview.hasta || '-'}
          </div>

          <div className="row mt-3">
            <div className="col-md-4">
              <div className="card text-center">
                <h6 style={{ marginTop: 12 }}>Órdenes</h6>
                <p className="display-6">{overview.kpis?.orders_total || 0}</p>
              </div>
            </div>
            <div className="col-md-4">
              <div className="card text-center">
                <h6 style={{ marginTop: 12 }}>Monto total</h6>
                <p className="display-6">{money(overview.kpis?.monto_total)}</p>
              </div>
            </div>
            <div className="col-md-4">
              <div className="card text-center">
                <h6 style={{ marginTop: 12 }}>Ticket promedio</h6>
                <p className="display-6">{money(overview.kpis?.ticket_promedio)}</p>
              </div>
            </div>
          </div>

          <div className="card" style={{ maxWidth: 800, height: 300, marginTop: 16 }}>
            <div style={{ padding: 12, fontWeight: 600 }}>Órdenes por estado</div>
            <div style={{ height: 230, padding: 12 }}>
              <Bar data={estadoChart.data} options={estadoChart.options} />
            </div>
          </div>
        </>
      )}

      {showForm && (
        <div className="form-container">
          <form onSubmit={handleSubmit} className="purchase-form">
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="supplier_id">Proveedor *</label>
                <select
                  id="supplier_id"
                  name="supplier_id"
                  value={formData.supplier_id}
                  onChange={handleInputChange}
                  required
                >
                  <option value="">Seleccionar proveedor</option>
                  {suppliers.map(supplier => (
                    <option key={supplier.id} value={supplier.id}>
                      {supplier.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="product_id">Producto *</label>
                <select
                  id="product_id"
                  name="product_id"
                  value={formData.product_id}
                  onChange={handleInputChange}
                  required
                >
                  <option value="">Seleccionar producto</option>
                  {products.map(product => (
                    <option key={product.id} value={product.id}>
                      {product.name} (SKU: {product.sku || 'N/A'})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="quantity">Cantidad *</label>
                <input
                  type="number"
                  id="quantity"
                  name="quantity"
                  value={formData.quantity}
                  onChange={handleInputChange}
                  min="1"
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="unit_price">Precio Unitario *</label>
                <input
                  type="number"
                  id="unit_price"
                  name="unit_price"
                  value={formData.unit_price}
                  onChange={handleInputChange}
                  step="0.01"
                  min="0"
                  required
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="total_amount">Total</label>
                <input
                  type="text"
                  id="total_amount"
                  value={`$${calculateTotal()}`}
                  readOnly
                />
              </div>
              <div className="form-group">
                <label htmlFor="status">Estado</label>
                <select
                  id="status"
                  name="status"
                  value={formData.status}
                  onChange={handleInputChange}
                >
                  <option value="pendiente">Pendiente</option>
                  <option value="aprobada">Aprobada</option>
                  <option value="ordenada">Ordenada</option>
                  <option value="recibida">Recibida</option>
                  <option value="cancelada">Cancelada</option>
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="order_date">Fecha de Orden *</label>
                <input
                  type="date"
                  id="order_date"
                  name="order_date"
                  value={formData.order_date}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="expected_delivery_date">Fecha Esperada de Entrega</label>
                <input
                  type="date"
                  id="expected_delivery_date"
                  name="expected_delivery_date"
                  value={formData.expected_delivery_date}
                  onChange={handleInputChange}
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="notes">Notas</label>
              <textarea
                id="notes"
                name="notes"
                value={formData.notes}
                onChange={handleInputChange}
                rows="3"
              />
            </div>

            <div className="form-actions">
              <button type="submit" className="btn btn-primary">Guardar Orden</button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowForm(false)}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="purchases-table-container">
        <table className="purchases-table">
          <thead>
            <tr>
              <th>Proveedor</th>
              <th>Producto</th>
              <th>Cantidad</th>
              <th>Precio Unit.</th>
              <th>Total</th>
              <th>Fecha Orden</th>
              <th>Fecha Esperada</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {purchases.map(purchase => (
              <tr key={purchase.id}>
                <td>{purchase.supplier || getSupplierName(purchase.supplier_id)}</td>
                <td>{getProductName(purchase.product_id)}</td>
                <td>{purchase.quantity}</td>
                <td>${purchase.unit_price?.toFixed(2) || '0.00'}</td>
                <td>${purchase.total_amount?.toFixed(2) || '0.00'}</td>
                <td>
                  {purchase.order_date
                    ? new Date(purchase.order_date).toLocaleDateString()
                    : '-'
                  }
                </td>
                <td>
                  {purchase.expected_delivery_date
                    ? new Date(purchase.expected_delivery_date).toLocaleDateString()
                    : '-'
                  }
                </td>
                <td>
                  <span className={`status status-${purchase.status}`}>
                    {purchase.status}
                  </span>
                </td>
                <td>
                  <button className="btn btn-sm btn-edit">Editar</button>
                  <button className="btn btn-sm btn-delete">Eliminar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {purchases.length === 0 && (
          <div className="no-data">
            No hay órdenes de compra registradas aún.
          </div>
        )}
      </div>
    </div>
  );
}

export default Compras;
