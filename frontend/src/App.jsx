// frontend/src/App.jsx
import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";

// Páginas
import Dashboard from "./pages/Dashboard";
import DashboardComercial from "./pages/DashboardComercial";
import PanelEjecutivo from "./pages/PanelEjecutivo";

import Products from "./pages/Products";
import Locations from "./pages/Locations";
import Stock from "./pages/Stock";

import Leads from "./pages/Leads";
import Compras from "./pages/Compras";
import RrhhPanel from "./pages/RrhhPanel";

function App() {
  return (
    <Layout>
      <Routes>
        {/* Redirijo raíz al dashboard operativo */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />

        {/* Paneles estratégicos */}
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/dashboard-comercial" element={<DashboardComercial />} />
        <Route path="/panel-ejecutivo" element={<PanelEjecutivo />} />

        {/* Operaciones */}
        <Route path="/products" element={<Products />} />
        <Route path="/locations" element={<Locations />} />
        <Route path="/stock" element={<Stock />} />

        {/* Comercial */}
        <Route path="/leads" element={<Leads />} />

        {/* Compras */}
        <Route path="/compras" element={<Compras />} />

        {/* RRHH */}
        <Route path="/rrhh" element={<RrhhPanel />} />

        {/* Fallback */}
        <Route path="*" element={<div>Página no encontrada</div>} />
      </Routes>
    </Layout>
  );
}

export default App;
