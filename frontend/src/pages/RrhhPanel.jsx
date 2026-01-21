// frontend/src/pages/RrhhPanel.jsx
import React, { useState, useEffect } from 'react';
import apiService from '../services/api';

function RrhhPanel() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [activeTab, setActiveTab] = useState('empleados');
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    position: '',
    department: '',
    hire_date: '',
    salary: '',
    location_id: '',
    is_active: true
  });

  useEffect(() => {
    if (activeTab === 'empleados') {
      loadEmployees();
    }
  }, [activeTab]);

  const loadEmployees = async () => {
    try {
      setLoading(true);
      const data = await apiService.getEmployees();
      setEmployees(data);
    } catch (err) {
      setError('Error al cargar los empleados');
      console.error('Error loading employees:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const employeeData = {
        ...formData,
        salary: parseFloat(formData.salary) || null
      };
      await apiService.createEmployee(employeeData);
      setFormData({
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        position: '',
        department: '',
        hire_date: '',
        salary: '',
        location_id: '',
        is_active: true
      });
      setShowForm(false);
      loadEmployees();
    } catch (err) {
      setError('Error al crear el empleado');
      console.error('Error creating employee:', err);
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
    return <div className="loading">Cargando datos de RRHH...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="rrhh-panel">
      <div className="page-header">
        <h1>Panel de Recursos Humanos</h1>
      </div>

      <div className="tabs">
        <button
          className={`tab ${activeTab === 'empleados' ? 'active' : ''}`}
          onClick={() => setActiveTab('empleados')}
        >
          Empleados
        </button>
        <button
          className={`tab ${activeTab === 'asistencia' ? 'active' : ''}`}
          onClick={() => setActiveTab('asistencia')}
        >
          Asistencia
        </button>
        <button
          className={`tab ${activeTab === 'ausentismo' ? 'active' : ''}`}
          onClick={() => setActiveTab('ausentismo')}
        >
          Ausentismo
        </button>
        <button
          className={`tab ${activeTab === 'clima' ? 'active' : ''}`}
          onClick={() => setActiveTab('clima')}
        >
          Clima Laboral
        </button>
        <button
          className={`tab ${activeTab === 'objetivos' ? 'active' : ''}`}
          onClick={() => setActiveTab('objetivos')}
        >
          Objetivos
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'empleados' && (
          <div className="empleados-section">
            <div className="section-header">
              <h2>Gestión de Empleados</h2>
              <button
                className="btn btn-primary"
                onClick={() => setShowForm(!showForm)}
              >
                {showForm ? 'Cancelar' : 'Nuevo Empleado'}
              </button>
            </div>

            {showForm && (
              <div className="form-container">
                <form onSubmit={handleSubmit} className="employee-form">
                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="first_name">Nombre *</label>
                      <input
                        type="text"
                        id="first_name"
                        name="first_name"
                        value={formData.first_name}
                        onChange={handleInputChange}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="last_name">Apellido *</label>
                      <input
                        type="text"
                        id="last_name"
                        name="last_name"
                        value={formData.last_name}
                        onChange={handleInputChange}
                        required
                      />
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="email">Email *</label>
                      <input
                        type="email"
                        id="email"
                        name="email"
                        value={formData.email}
                        onChange={handleInputChange}
                        required
                      />
                    </div>
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
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="position">Puesto</label>
                      <input
                        type="text"
                        id="position"
                        name="position"
                        value={formData.position}
                        onChange={handleInputChange}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="department">Departamento</label>
                      <select
                        id="department"
                        name="department"
                        value={formData.department}
                        onChange={handleInputChange}
                      >
                        <option value="">Seleccionar departamento</option>
                        <option value="Ventas">Ventas</option>
                        <option value="Compras">Compras</option>
                        <option value="RRHH">RRHH</option>
                        <option value="Operaciones">Operaciones</option>
                        <option value="Administración">Administración</option>
                        <option value="Otro">Otro</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label htmlFor="hire_date">Fecha de Contratación</label>
                      <input
                        type="date"
                        id="hire_date"
                        name="hire_date"
                        value={formData.hire_date}
                        onChange={handleInputChange}
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="salary">Salario</label>
                      <input
                        type="number"
                        id="salary"
                        name="salary"
                        value={formData.salary}
                        onChange={handleInputChange}
                        step="0.01"
                        min="0"
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
                      Empleado activo
                    </label>
                  </div>

                  <div className="form-actions">
                    <button type="submit" className="btn btn-primary">Guardar Empleado</button>
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

            <div className="employees-table-container">
              <table className="employees-table">
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>Email</th>
                    <th>Teléfono</th>
                    <th>Puesto</th>
                    <th>Departamento</th>
                    <th>Fecha Contratación</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.map(employee => (
                    <tr key={employee.id}>
                      <td>{`${employee.first_name} ${employee.last_name}`}</td>
                      <td>{employee.email}</td>
                      <td>{employee.phone || '-'}</td>
                      <td>{employee.position || '-'}</td>
                      <td>{employee.department || '-'}</td>
                      <td>
                        {employee.hire_date
                          ? new Date(employee.hire_date).toLocaleDateString()
                          : '-'
                        }
                      </td>
                      <td>
                        <span className={`status ${employee.is_active ? 'status-active' : 'status-inactive'}`}>
                          {employee.is_active ? 'Activo' : 'Inactivo'}
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

              {employees.length === 0 && (
                <div className="no-data">
                  No hay empleados registrados aún.
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'asistencia' && (
          <div className="asistencia-section">
            <h2>Control de Asistencia</h2>
            <div className="placeholder-content">
              <p>Módulo de control de asistencia en desarrollo.</p>
              <p>Próximamente: registro de entradas/salidas, reportes de asistencia, etc.</p>
            </div>
          </div>
        )}

        {activeTab === 'ausentismo' && (
          <div className="ausentismo-section">
            <h2>Control de Ausentismo</h2>
            <div className="placeholder-content">
              <p>Módulo de control de ausentismo en desarrollo.</p>
              <p>Próximamente: registro de ausencias, tipos de ausencia, reportes, etc.</p>
            </div>
          </div>
        )}

        {activeTab === 'clima' && (
          <div className="clima-section">
            <h2>Clima Laboral</h2>
            <div className="placeholder-content">
              <p>Módulo de evaluación del clima laboral en desarrollo.</p>
              <p>Próximamente: encuestas, indicadores de satisfacción, reportes, etc.</p>
            </div>
          </div>
        )}

        {activeTab === 'objetivos' && (
          <div className="objetivos-section">
            <h2>Gestión de Objetivos</h2>
            <div className="placeholder-content">
              <p>Módulo de gestión de objetivos en desarrollo.</p>
              <p>Próximamente: definición de objetivos, seguimiento, evaluaciones, etc.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default RrhhPanel;
