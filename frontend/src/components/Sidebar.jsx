// frontend/src/components/Sidebar.jsx
import React from "react";
import { NavLink, useLocation } from "react-router-dom";

function Sidebar() {
  const location = useLocation();
  const current = location.pathname;

  const linkClass = ({ isActive }) =>
    "sidebar-link " + (isActive ? "active-link" : "");

  return (
    <aside className="sidebar">
      <h2>Silva360</h2>

      {/* Paneles Estratégicos */}
      <div className="sidebar-section-title">Paneles Estratégicos</div>

      <NavLink
        to="/dashboard-financiero"
        className={linkClass}
      >
        Dashboard Financiero
      </NavLink>

      <NavLink
        to="/dashboard-comercial"
        className={linkClass}
      >
        Dashboard Comercial
      </NavLink>

      <NavLink
        to="/panel-ejecutivo"
        className={linkClass}
      >
        Panel Ejecutivo
      </NavLink>

      <NavLink
        to="/inteligencia"
        className={linkClass}
      >
        Inteligencia
      </NavLink>

      <hr />

      {/* Operaciones */}
      <div className="sidebar-section-title">Operaciones</div>

      <NavLink to="/products" className={linkClass}>
        Productos
      </NavLink>

      <NavLink to="/locations" className={linkClass}>
        Ubicaciones
      </NavLink>

      <NavLink to="/stock" className={linkClass}>
        Stock
      </NavLink>

      <hr />

      {/* Comercial */}
      <div className="sidebar-section-title">Comercial</div>

      <NavLink to="/leads" className={linkClass}>
        Leads
      </NavLink>

      <hr />

      {/* Compras */}
      <div className="sidebar-section-title">Compras</div>

      <NavLink to="/compras" className={linkClass}>
        Panel de Compras
      </NavLink>

      <hr />

      {/* RRHH */}
      <div className="sidebar-section-title">RRHH</div>

      <NavLink to="/rrhh" className={linkClass}>
        Panel RRHH
      </NavLink>
    </aside>
  );
}

export default Sidebar;
