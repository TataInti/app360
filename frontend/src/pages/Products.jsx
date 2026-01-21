// frontend/src/pages/Products.jsx
import React, { useState, useEffect } from 'react';
import apiService from '../services/api';

function Products() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    price: '',
    category: '',
    sku: '',
    stock_quantity: '',
    min_stock_level: '',
    business_unit_id: '',
    location_id: ''
  });
  const [formErrors, setFormErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    loadProducts();
  }, []);

  const loadProducts = async () => {
    try {
      setLoading(true);
      const data = await apiService.getProducts();
      setProducts(data);
    } catch (err) {
      setError('Error al cargar los productos');
      console.error('Error loading products:', err);
    } finally {
      setLoading(false);
    }
  };

  const validateForm = () => {
    const errors = {};

    if (!formData.name.trim()) {
      errors.name = 'El nombre es obligatorio';
    } else if (formData.name.trim().length < 2) {
      errors.name = 'El nombre debe tener al menos 2 caracteres';
    }

    if (!formData.price || isNaN(formData.price) || parseFloat(formData.price) < 0) {
      errors.price = 'El precio debe ser un número positivo';
    }

    if (!formData.category) {
      errors.category = 'Debe seleccionar una categoría';
    }

    if (formData.sku && formData.sku.length < 3) {
      errors.sku = 'El SKU debe tener al menos 3 caracteres';
    }

    if (formData.stock_quantity && (isNaN(formData.stock_quantity) || parseInt(formData.stock_quantity) < 0)) {
      errors.stock_quantity = 'La cantidad debe ser un número entero positivo';
    }

    if (formData.min_stock_level && (isNaN(formData.min_stock_level) || parseInt(formData.min_stock_level) < 0)) {
      errors.min_stock_level = 'El nivel mínimo debe ser un número entero positivo';
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);
    try {
      const productData = {
        ...formData,
        price: parseFloat(formData.price),
        stock_quantity: parseInt(formData.stock_quantity) || 0,
        min_stock_level: parseInt(formData.min_stock_level) || 0
      };
      await apiService.createProduct(productData);
      setFormData({
        name: '',
        description: '',
        price: '',
        category: '',
        sku: '',
        stock_quantity: '',
        min_stock_level: '',
        business_unit_id: '',
        location_id: ''
      });
      setFormErrors({});
      setShowForm(false);
      loadProducts();
    } catch (err) {
      setError('Error al crear el producto');
      console.error('Error creating product:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));

    // Clear error when user starts typing
    if (formErrors[name]) {
      setFormErrors(prev => ({
        ...prev,
        [name]: ''
      }));
    }
  };

  if (loading) {
    return <div className="loading">Cargando productos...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="products-page">
      <div className="page-header">
        <h1>Gestión de Productos</h1>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? 'Cancelar' : 'Nuevo Producto'}
        </button>
      </div>

      {showForm && (
        <div className="form-container">
          <form onSubmit={handleSubmit} className="product-form">
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="name">Nombre *</label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  value={formData.name}
                  onChange={handleInputChange}
                  className={formErrors.name ? 'error' : ''}
                  required
                />
                {formErrors.name && <span className="error-message">{formErrors.name}</span>}
              </div>
              <div className="form-group">
                <label htmlFor="sku">SKU</label>
                <input
                  type="text"
                  id="sku"
                  name="sku"
                  value={formData.sku}
                  onChange={handleInputChange}
                  className={formErrors.sku ? 'error' : ''}
                />
                {formErrors.sku && <span className="error-message">{formErrors.sku}</span>}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="price">Precio *</label>
                <input
                  type="number"
                  id="price"
                  name="price"
                  value={formData.price}
                  onChange={handleInputChange}
                  step="0.01"
                  min="0"
                  className={formErrors.price ? 'error' : ''}
                  required
                />
                {formErrors.price && <span className="error-message">{formErrors.price}</span>}
              </div>
              <div className="form-group">
                <label htmlFor="category">Categoría</label>
                <select
                  id="category"
                  name="category"
                  value={formData.category}
                  onChange={handleInputChange}
                  className={formErrors.category ? 'error' : ''}
                >
                  <option value="">Seleccionar categoría</option>
                  <option value="Materiales">Materiales</option>
                  <option value="Herramientas">Herramientas</option>
                  <option value="Equipos">Equipos</option>
                  <option value="Servicios">Servicios</option>
                  <option value="Otro">Otro</option>
                </select>
                {formErrors.category && <span className="error-message">{formErrors.category}</span>}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="stock_quantity">Stock Actual</label>
                <input
                  type="number"
                  id="stock_quantity"
                  name="stock_quantity"
                  value={formData.stock_quantity}
                  onChange={handleInputChange}
                  min="0"
                  className={formErrors.stock_quantity ? 'error' : ''}
                />
                {formErrors.stock_quantity && <span className="error-message">{formErrors.stock_quantity}</span>}
              </div>
              <div className="form-group">
                <label htmlFor="min_stock_level">Stock Mínimo</label>
                <input
                  type="number"
                  id="min_stock_level"
                  name="min_stock_level"
                  value={formData.min_stock_level}
                  onChange={handleInputChange}
                  min="0"
                  className={formErrors.min_stock_level ? 'error' : ''}
                />
                {formErrors.min_stock_level && <span className="error-message">{formErrors.min_stock_level}</span>}
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="description">Descripción</label>
              <textarea
                id="description"
                name="description"
                value={formData.description}
                onChange={handleInputChange}
                rows="3"
              />
            </div>

            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Guardando...' : 'Guardar Producto'}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowForm(false)}
                disabled={isSubmitting}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="products-table-container">
        <table className="products-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>SKU</th>
              <th>Categoría</th>
              <th>Precio</th>
              <th>Stock</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {products.map(product => (
              <tr key={product.id}>
                <td>{product.name}</td>
                <td>{product.sku || '-'}</td>
                <td>{product.category || '-'}</td>
                <td>${product.price?.toFixed(2) || '0.00'}</td>
                <td>
                  <span className={product.stock_quantity <= product.min_stock_level ? 'stock-low' : 'stock-good'}>
                    {product.stock_quantity || 0}
                  </span>
                </td>
                <td>
                  <span className={`status ${product.stock_quantity > product.min_stock_level ? 'status-active' : 'status-warning'}`}>
                    {product.stock_quantity > product.min_stock_level ? 'Disponible' : 'Bajo stock'}
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

        {products.length === 0 && (
          <div className="no-data">
            No hay productos registrados aún.
          </div>
        )}
      </div>
    </div>
  );
}

export default Products;
