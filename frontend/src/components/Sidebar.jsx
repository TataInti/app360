// frontend/src/components/Sidebar.jsx
import React, { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

function Sidebar() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const initial = localStorage.getItem("reactSidebarCollapsed") === "true";
    setCollapsed(initial);
  }, []);

  useEffect(() => {
    localStorage.setItem("reactSidebarCollapsed", collapsed ? "true" : "false");
  }, [collapsed]);

  const linkClass = ({ isActive }) =>
    "sidebar-link " + (isActive ? "active-link" : "");

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <h2>Silva360</h2>

      <button
        type="button"
        className="sidebar-toggle-btn"
        onClick={() => setCollapsed((prev) => !prev)}
        aria-label={collapsed ? "Expandir barra lateral" : "Contraer barra lateral"}
      >
        <span className="sidebar-toggle-btn-icon">{collapsed ? ">" : "<"}</span>
        {!collapsed && <span className="sidebar-toggle-btn-text">Contraer</span>}
      </button>

      {/* Paneles Estratégicos */}
      {!collapsed && <div className="sidebar-section-title">Paneles Estratégicos</div>}

      <NavLink
        to="/dashboard-financiero"
        className={linkClass}
      >
        <span className="sidebar-label">Panel Tesoreria</span>
      </NavLink>

      <NavLink
        to="/dashboard-comercial"
        className={linkClass}
      >
        <span className="sidebar-label">Panel Ventas</span>
      </NavLink>

      <NavLink
        to="/panel-ejecutivo"
        className={linkClass}
      >
        <span className="sidebar-label">Panel Ejecutivo</span>
      </NavLink>

      <NavLink
        to="/inteligencia"
        className={linkClass}
      >
        <span className="sidebar-label">Inteligencia</span>
      </NavLink>

      {!collapsed && <hr />}

      {/* Operaciones */}
      {!collapsed && <div className="sidebar-section-title">Operaciones</div>}

      <NavLink to="/products" className={linkClass}>
        <span className="sidebar-label">Productos</span>
      </NavLink>

      <NavLink to="/locations" className={linkClass}>
        <span className="sidebar-label">Ubicaciones</span>
      </NavLink>

      <NavLink to="/stock" className={linkClass}>
        <span className="sidebar-label">Stock</span>
      </NavLink>

      {!collapsed && <hr />}

      {/* Comercial */}
      {!collapsed && <div className="sidebar-section-title">Comercial</div>}

      <NavLink to="/leads" className={linkClass}>
        <span className="sidebar-label">Leads</span>
      </NavLink>

      {!collapsed && <hr />}

      {/* Compras */}
      {!collapsed && <div className="sidebar-section-title">Compras</div>}

      <NavLink to="/compras" className={linkClass}>
        <span className="sidebar-label">Panel de Compras</span>
      </NavLink>

      {!collapsed && <hr />}

      {/* RRHH */}
      {!collapsed && <div className="sidebar-section-title">RRHH</div>}

      <NavLink to="/rrhh" className={linkClass}>
        <span className="sidebar-label">Panel RRHH</span>
      </NavLink>

      {!collapsed && <hr />}

      {/* Administración */}
      {!collapsed && <div className="sidebar-section-title">Administración</div>}

      <NavLink to="/sabiogo-import" className={linkClass}>
        <span className="sidebar-label">Importar SabioGo</span>
      </NavLink>
    </aside>
  );
}

export default Sidebar;
