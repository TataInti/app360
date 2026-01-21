// frontend/src/pages/Leads.jsx
import React, { useState, useEffect } from 'react';
import apiService from '../services/api';

function Leads() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    email: '',
    source: '',
    status: 'nuevo',
    stage: 'nuevo',
    business_unit_id: '',
    product_id: '',
    location_id: '',
    owner_name: '',
    campaign_id: ''
  });
  const [formErrors, setFormErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    loadLeads();
  }, []);

  const loadLeads = async () => {
    try {
      setLoading(true);
      const data = await apiService.getLeads();
      setLeads(data);
    } catch (err) {
      setError('Error al cargar los leads');
      console.error('Error loading leads:', err);
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

    if (formData.email && !/\S+@\S+\.\S+/.test(formData.email)) {
      errors.email = 'El email no tiene un formato válido';
    }

    if (formData.phone && !/^\+?[\d\s\-\(\)]+$/.test(formData.phone)) {
      errors.phone = 'El teléfono contiene caracteres inválidos';
    }

    if (!formData.source) {
      errors.source = 'Debe seleccionar una fuente';
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
      await apiService.createLead(formData);
      setFormData({
        name: '',
        phone: '',
        email: '',
        source: '',
        status: 'nuevo',
        stage: 'nuevo',
        business_unit_id: '',
        product_id: '',
        location_id: '',
        owner_name: '',
        campaign_id: ''
      });
      setFormErrors({});
      setShowForm(false);
      loadLeads();
    } catch (err) {
      setError('Error al crear el lead');
      console.error('Error creating lead:', err);
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
    return <div className="loading">Cargando leads...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="leads-page">
      <div className="page-header">
        <h1>Gestión de Leads</h1>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? 'Cancelar' : 'Nuevo Lead'}
        </button>
      </div>

      {showForm && (
        <div className="form-container">
          <form onSubmit={handleSubmit} className="lead-form">
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
                <label htmlFor="phone">Teléfono</label>
                <input
                  type="tel"
                  id="phone"
                  name="phone"
                  value={formData.phone}
                  onChange={handleInputChange}
                  className={formErrors.phone ? 'error' : ''}
                />
                {formErrors.phone && <span className="error-message">{formErrors.phone}</span>}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="email">Email</label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  className={formErrors.email ? 'error' : ''}
                />
                {formErrors.email && <span className="error-message">{formErrors.email}</span>}
              </div>
              <div className="form-group">
                <label htmlFor="source">Fuente</label>
                <select
                  id="source"
                  name="source"
                  value={formData.source}
                  onChange={handleInputChange}
                  className={formErrors.source ? 'error' : ''}
                >
                  <option value="">Seleccionar fuente</option>
                  <option value="Meta">Meta</option>
                  <option value="Google">Google</option>
                  <option value="Orgánico">Orgánico</option>
                  <option value="Referido">Referido</option>
                  <option value="Otro">Otro</option>
                </select>
                {formErrors.source && <span className="error-message">{formErrors.source}</span>}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="status">Estado</label>
                <select
                  id="status"
                  name="status"
                  value={formData.status}
                  onChange={handleInputChange}
                >
                  <option value="nuevo">Nuevo</option>
                  <option value="contactado">Contactado</option>
                  <option value="propuesta">Propuesta</option>
                  <option value="ganado">Ganado</option>
                  <option value="perdido">Perdido</option>
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="stage">Etapa</label>
                <select
                  id="stage"
                  name="stage"
                  value={formData.stage}
                  onChange={handleInputChange}
                >
                  <option value="nuevo">Nuevo</option>
                  <option value="calificado">Calificado</option>
                  <option value="propuesta">Propuesta</option>
                  <option value="negociacion">Negociación</option>
                  <option value="cerrado">Cerrado</option>
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label htmlFor="owner_name">Propietario</label>
                <input
                  type="text"
                  id="owner_name"
                  name="owner_name"
                  value={formData.owner_name}
                  onChange={handleInputChange}
                  placeholder="Nombre del responsable"
                />
              </div>
            </div>

            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Guardando...' : 'Guardar Lead'}
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

      <div className="leads-table-container">
        <table className="leads-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Contacto</th>
              <th>Fuente</th>
              <th>Estado</th>
              <th>Etapa</th>
              <th>Propietario</th>
              <th>Último Contacto</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {leads.map(lead => (
              <tr key={lead.id}>
                <td>{lead.name}</td>
                <td>
                  {lead.phone && <div>{lead.phone}</div>}
                  {lead.email && <div>{lead.email}</div>}
                </td>
                <td>{lead.source}</td>
                <td>
                  <span className={`status status-${lead.status}`}>
                    {lead.status}
                  </span>
                </td>
                <td>
                  <span className={`stage stage-${lead.stage}`}>
                    {lead.stage}
                  </span>
                </td>
                <td>{lead.owner_name || '-'}</td>
                <td>
                  {lead.last_contacted_at
                    ? new Date(lead.last_contacted_at).toLocaleDateString()
                    : '-'
                  }
                </td>
                <td>
                  <button className="btn btn-sm btn-edit">Editar</button>
                  <button className="btn btn-sm btn-delete">Eliminar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {leads.length === 0 && (
          <div className="no-data">
            No hay leads registrados aún.
          </div>
        )}
      </div>
    </div>
  );
}

export default Leads;
