// frontend/src/App.jsx
import React, { Suspense, lazy } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";

// Lazy load pages
const Dashboard = lazy(() => import("./pages/Dashboard"));
const DashboardFinanciero = lazy(() => import("./pages/DashboardFinanciero"));
const DashboardComercial = lazy(() => import("./pages/DashboardComercial"));
const PanelEjecutivo = lazy(() => import("./pages/PanelEjecutivo"));
const Inteligencia = lazy(() => import("./pages/Inteligencia"));
const Products = lazy(() => import("./pages/Products"));
const Locations = lazy(() => import("./pages/Locations"));
const Stock = lazy(() => import("./pages/Stock"));
const Leads = lazy(() => import("./pages/Leads"));
const Compras = lazy(() => import("./pages/Compras"));
const RrhhPanel = lazy(() => import("./pages/RrhhPanel"));

// Loading component
function LoadingSpinner() {
  return <div className="loading-spinner">Cargando...</div>;
}

function App() {
  return (
    <Layout>
      <Suspense fallback={<LoadingSpinner />}>
        <Routes>
          {/* Redirijo raíz al dashboard operativo */}
          <Route path="/" element={<Navigate to="/dashboard-financiero" replace />} />

          {/* Paneles estratégicos */}
          <Route path="/dashboard" element={<Navigate to="/dashboard-financiero" replace />} />
          <Route path="/dashboard-financiero" element={<DashboardFinanciero />} />
          <Route path="/dashboard-comercial" element={<DashboardComercial />} />
          <Route path="/panel-ejecutivo" element={<PanelEjecutivo />} />
          <Route path="/inteligencia" element={<Inteligencia />} />

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
      </Suspense>
    </Layout>
  );
}

export default App;
