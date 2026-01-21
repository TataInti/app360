// frontend/src/pages/Locations.jsx
import React, { useState, useEffect } from 'react';
import apiService from '../services/api';

function Locations() {
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    country: 'México',
    phone: '',
    email: '',
    manager_name: '',
    business_unit_id: '',
    is_active: true
  });

  useEffect(() => {
    loadLocations();
  }, []);

  const loadLocations = async () => {
    try {
      setLoading(true);
      const data = await apiService.getLocations();
      setLocations(data);
    } catch (err) {
      setError('Error al cargar las ubicaciones');
      console.error('Error loading locations:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await apiService.createLocation(formData);
      setFormData({
        name: '',
        address: '',
        city: '',
        state: '',
        zip_code: '',
        country: 'México',
        phone: '',
        email: '',
        manager_name: '',
        business_unit_id: '',
        is_active: true
      });
      setShowForm(false);
      loadLocations();
    } catch (err) {
      setError('Error al crear la ubicación');
      console.error('Error creating location:', err);
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  if (loading) {
    return <div className="loading">Cargando ubicaciones...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="locations-page">
      <div className="page-header">
        <h1>Gestión de Ubicaciones</h1>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? 'Cancelar' : 'Nueva Ubicación'}
        </button>
      </div>

      {showForm && (
        <div className="form-container">
          <form onSubmit={handleSubmit} className="location-form">
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="name">Nombre *</label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  value={formData.name}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="manager_name">Gerente</label>
                <input
                  type="text"
                  id="manager_name"
                  name="manager_name"
                  value={formData.manager_name}
                  onChange={handleInputChange}
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="address">Dirección *</label>
              <input
                type="text"
                id="address"
                name="address"
                value={formData.address}
                onChange={handleInputChange}
                required
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="city">Ciudad *</label>
                <input
                  type="text"
                  id="city"
                  name="city"
                  value={formData.city}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="state">Estado</label>
                <input
                  type="text"
                  id="state"
                  name="state"
                  value={formData.state}
                  onChange={handleInputChange}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="zip_code">Código Postal</label>
                <input
                  type="text"
                  id="zip_code"
                  name="zip_code"
                  value={formData.zip_code}
                  onChange={handleInputChange}
                />
              </div>
              <div className="form-group">
                <label htmlFor="country">País</label>
                <input
                  type="text"
                  id="country"
                  name="country"
                  value={formData.country}
                  onChange={handleInputChange}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="phone">Teléfono</label>
                <input
                  type="tel"
                  id="phone"
                  name="phone"
                  value={formData.phone}
                  onChange={handleInputChange}
                />
              </div>
              <div className="form-group">
                <label htmlFor="email">Email</label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={formData.email}
                  onChange={handleInputChange}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="is_active"
                  checked={formData.is_active}
                  onChange={handleInputChange}
                />
                Ubicación activa
              </label>
            </div>

            <div className="form-actions">
              <button type="submit" className="btn btn-primary">Guardar Ubicación</button>
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

      <div className="locations-table-container">
        <table className="locations-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Dirección</th>
              <th>Ciudad</th>
              <th>Estado</th>
              <th>Teléfono</th>
              <th>Gerente</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {locations.map(location => (
              <tr key={location.id}>
                <td>{location.name}</td>
                <td>{location.address}</td>
                <td>{location.city}</td>
                <td>{location.state}</td>
                <td>{location.phone || '-'}</td>
                <td>{location.manager_name || '-'}</td>
                <td>
                  <span className={`status ${location.is_active ? 'status-active' : 'status-inactive'}`}>
                    {location.is_active ? 'Activa' : 'Inactiva'}
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

        {locations.length === 0 && (
          <div className="no-data">
            No hay ubicaciones registradas aún.
          </div>
        )}
      </div>
    </div>
  );
}

export default Locations;
