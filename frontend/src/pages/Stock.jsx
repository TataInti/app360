// frontend/src/pages/Stock.jsx
import React, { useState, useEffect } from 'react';
import apiService from '../services/api';

function Stock() {
  const [stockItems, setStockItems] = useState([]);
  const [products, setProducts] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    product_id: '',
    location_id: '',
    quantity: '',
    min_quantity: '',
    max_quantity: '',
    batch_number: '',
    expiry_date: '',
    notes: ''
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [stockData, productsData, locationsData] = await Promise.all([
        apiService.getStock(),
        apiService.getProducts(),
        apiService.getLocations()
      ]);
      setStockItems(stockData);
      setProducts(productsData);
      setLocations(locationsData);
    } catch (err) {
      setError('Error al cargar los datos');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const stockData = {
        ...formData,
        quantity: parseInt(formData.quantity),
        min_quantity: parseInt(formData.min_quantity) || 0,
        max_quantity: parseInt(formData.max_quantity) || null
      };
      await apiService.createStock(stockData);
      setFormData({
        product_id: '',
        location_id: '',
        quantity: '',
        min_quantity: '',
        max_quantity: '',
        batch_number: '',
        expiry_date: '',
        notes: ''
      });
      setShowForm(false);
      loadData();
    } catch (err) {
      setError('Error al crear el registro de stock');
      console.error('Error creating stock:', err);
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

  const getLocationName = (locationId) => {
    const location = locations.find(l => l.id === locationId);
    return location ? location.name : 'Ubicación desconocida';
  };

  if (loading) {
    return <div className="loading">Cargando inventario...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="stock-page">
      <div className="page-header">
        <h1>Gestión de Inventario</h1>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? 'Cancelar' : 'Nuevo Registro'}
        </button>
      </div>

      {showForm && (
        <div className="form-container">
          <form onSubmit={handleSubmit} className="stock-form">
            <div className="form-row">
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
              <div className="form-group">
                <label htmlFor="location_id">Ubicación *</label>
                <select
                  id="location_id"
                  name="location_id"
                  value={formData.location_id}
                  onChange={handleInputChange}
                  required
                >
                  <option value="">Seleccionar ubicación</option>
                  {locations.map(location => (
                    <option key={location.id} value={location.id}>
                      {location.name} - {location.city}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="quantity">Cantidad Actual *</label>
                <input
                  type="number"
                  id="quantity"
                  name="quantity"
                  value={formData.quantity}
                  onChange={handleInputChange}
                  min="0"
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="min_quantity">Cantidad Mínima</label>
                <input
                  type="number"
                  id="min_quantity"
                  name="min_quantity"
                  value={formData.min_quantity}
                  onChange={handleInputChange}
                  min="0"
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="max_quantity">Cantidad Máxima</label>
                <input
                  type="number"
                  id="max_quantity"
                  name="max_quantity"
                  value={formData.max_quantity}
                  onChange={handleInputChange}
                  min="0"
                />
              </div>
              <div className="form-group">
                <label htmlFor="batch_number">Lote</label>
                <input
                  type="text"
                  id="batch_number"
                  name="batch_number"
                  value={formData.batch_number}
                  onChange={handleInputChange}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="expiry_date">Fecha de Expiración</label>
                <input
                  type="date"
                  id="expiry_date"
                  name="expiry_date"
                  value={formData.expiry_date}
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
              <button type="submit" className="btn btn-primary">Guardar Registro</button>
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

      <div className="stock-table-container">
        <table className="stock-table">
          <thead>
            <tr>
              <th>Producto</th>
              <th>Ubicación</th>
              <th>Cantidad</th>
              <th>Mínimo</th>
              <th>Máximo</th>
              <th>Lote</th>
              <th>Expiración</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {stockItems.map(item => (
              <tr key={item.id}>
                <td>{getProductName(item.product_id)}</td>
                <td>{getLocationName(item.location_id)}</td>
                <td>{item.quantity}</td>
                <td>{item.min_quantity || '-'}</td>
                <td>{item.max_quantity || '-'}</td>
                <td>{item.batch_number || '-'}</td>
                <td>
                  {item.expiry_date
                    ? new Date(item.expiry_date).toLocaleDateString()
                    : '-'
                  }
                </td>
                <td>
                  <span className={`status ${
                    item.quantity <= item.min_quantity
                      ? 'status-warning'
                      : item.quantity >= item.max_quantity
                        ? 'status-info'
                        : 'status-good'
                  }`}>
                    {item.quantity <= item.min_quantity
                      ? 'Bajo stock'
                      : item.quantity >= item.max_quantity
                        ? 'Sobre stock'
                        : 'Normal'
                    }
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

        {stockItems.length === 0 && (
          <div className="no-data">
            No hay registros de inventario aún.
          </div>
        )}
      </div>
    </div>
  );
}

export default Stock;
