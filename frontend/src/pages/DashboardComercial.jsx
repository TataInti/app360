// frontend/src/pages/DashboardComercial.jsx
import React, { useEffect, useState } from "react";
import { Bar, Pie } from "react-chartjs-2";
import {
  Chart as ChartJS,
  BarElement,
  ArcElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
} from "chart.js";
import apiService from '../services/api';

ChartJS.register(
  BarElement,
  ArcElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend
);

function formatMoney(value) {
  return `$${Number(value || 0).toLocaleString("es-AR", { maximumFractionDigits: 0 })}`;
}

function DashboardComercial() {
  const [data, setData] = useState({
    period: "30",
    desde: null,
    hasta: null,
    kpis: {},
    series: {
      leads_por_estado: {},
      leads_por_origen: [],
      leads_por_canal: [],
      top_campanias_por_leads: [],
    },
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError("");
        const dashboardData = await apiService.getDashboardComercialV2("30");
        setData(dashboardData);
      } catch (err) {
        console.error('Error loading commercial dashboard:', err);
        setError("No se pudo cargar el dashboard comercial. Verifica la conexión con el servidor.");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const kpis = data.kpis || {};
  const series = data.series || {};

  const estadoLabels = Object.keys(series.leads_por_estado || {});
  const estadoValues = Object.values(series.leads_por_estado || {});

  if (loading) {
    return <div className="loading">Cargando dashboard comercial...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="dashboard-comercial-page">
      <div className="page-header">
        <h1>Dashboard Comercial</h1>
        <div className="text-muted small mt-2">
          Período: {data.desde || "-"} → {data.hasta || "-"}
        </div>
      </div>

      <div className="row mt-4">
        <div className="col-md-4">
          <div className="card text-center">
            <h4>Total de Leads</h4>
            <p className="display-6">{kpis.leads_total || 0}</p>
          </div>
        </div>

        <div className="col-md-4">
          <div className="card text-center">
            <h4>Campañas Activas</h4>
            <p className="display-6">{kpis.campanias_activas || 0}</p>
          </div>
        </div>

        <div className="col-md-4">
          <div className="card text-center">
            <h4>Conversión (total)</h4>
            <p className="display-6">{kpis.conversion_total_pct || 0} %</p>
          </div>
        </div>
      </div>

      <div className="row mt-3">
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Leads (período)</h6>
            <p className="display-6">{kpis.leads_periodo || 0}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Ventas (período)</h6>
            <p className="display-6">{formatMoney(kpis.ventas_periodo_total)}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Promociones activas</h6>
            <p className="display-6">{kpis.promociones_activas || 0}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Comisiones (mes)</h6>
            <p className="display-6">{formatMoney(kpis.comisiones_mes_total)}</p>
          </div>
        </div>
      </div>

      <div className="row mt-3">
        <div className="col-md-6">
          <div className="card text-center pre-card-accent">
            <h6 className="mt-3">Ventas PRE (período)</h6>
            <p className="display-6">{formatMoney(kpis.ventas_pre_periodo_total)}</p>
            <small className="text-muted">Operaciones PRE: {kpis.ventas_pre_periodo_count || 0}</small>
          </div>
        </div>
        <div className="col-md-6">
          <div className="card text-center pre-card-accent-soft">
            <h6 className="mt-3">Objetivos en progreso</h6>
            <p className="display-6">{kpis.objetivos_en_progreso || 0}</p>
            <small className="text-muted">Avance sincronizable desde PRE</small>
          </div>
        </div>
      </div>

      <hr className="mt-5" />

      <h3>Leads por Estado</h3>
      <div className="card" style={{ maxWidth: 600, height: 300, margin: '0 auto' }}>
        <Bar
          data={{
            labels: estadoLabels,
            datasets: [
              {
                label: "Cantidad",
                data: estadoValues,
                backgroundColor: 'rgba(34, 197, 94, 0.8)',
                borderColor: 'rgba(34, 197, 94, 1)',
                borderWidth: 1,
              },
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              y: {
                beginAtZero: true,
                ticks: {
                  precision: 0
                }
              },
            },
            plugins: {
              legend: {
                display: true,
                position: 'top',
              },
              tooltip: {
                callbacks: {
                  label: function(context) {
                    return `Leads: ${context.parsed.y}`;
                  }
                }
              }
            }
          }}
        />
      </div>


      <hr className="mt-5" />

      <h3>Detalle de Ventas PRE (operativo)</h3>
      <div style={{ maxWidth: 1100 }}>
        <table className="table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Vendedor</th>
              <th>Cliente</th>
              <th>Producto</th>
              <th>Comprobante</th>
              <th className="text-end">Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {(series.pre_detalle || []).length ? (
              series.pre_detalle.map((row) => (
                <tr key={row.id}>
                  <td>{row.fecha || "-"}</td>
                  <td>{row.vendedor || "Sin vendedor"}</td>
                  <td>{row.cliente || "Sin cliente"}</td>
                  <td>{row.producto || "Sin producto"}</td>
                  <td>{row.comprobante || "PRE"} {row.nro_comprob ? `#${row.nro_comprob}` : ""}</td>
                  <td className="text-end">{formatMoney(row.subtot)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="text-muted">Sin operaciones PRE para el período</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="row mt-3">
        <div className="col-md-4">
          <h5>PRE por vendedor</h5>
          <table className="table table-sm">
            <thead>
              <tr><th>Vendedor</th><th className="text-end">Monto</th></tr>
            </thead>
            <tbody>
              {(series.pre_por_vendedor || []).length ? (
                series.pre_por_vendedor.map(([nombre, _cant, monto]) => (
                  <tr key={nombre}><td>{nombre}</td><td className="text-end">{formatMoney(monto)}</td></tr>
                ))
              ) : (
                <tr><td colSpan={2} className="text-muted">Sin datos</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="col-md-4">
          <h5>PRE por cliente</h5>
          <table className="table table-sm">
            <thead>
              <tr><th>Cliente</th><th className="text-end">Monto</th></tr>
            </thead>
            <tbody>
              {(series.pre_por_cliente || []).length ? (
                series.pre_por_cliente.map(([nombre, _cant, monto]) => (
                  <tr key={nombre}><td>{nombre}</td><td className="text-end">{formatMoney(monto)}</td></tr>
                ))
              ) : (
                <tr><td colSpan={2} className="text-muted">Sin datos</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="col-md-4">
          <h5>PRE por producto</h5>
          <table className="table table-sm">
            <thead>
              <tr><th>Producto</th><th className="text-end">Monto</th></tr>
            </thead>
            <tbody>
              {(series.pre_por_producto || []).length ? (
                series.pre_por_producto.map(([nombre, _cant, monto]) => (
                  <tr key={nombre}><td>{nombre}</td><td className="text-end">{formatMoney(monto)}</td></tr>
                ))
              ) : (
                <tr><td colSpan={2} className="text-muted">Sin datos</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <h3>Leads por Canal (Marketing)</h3>
      <div style={{ maxWidth: 500, height: 300 }}>
        <Pie
          data={{
            labels: (series.leads_por_canal || []).map(([name]) => name),
            datasets: [
              {
                data: (series.leads_por_canal || []).map(([, qty]) => qty),
              },
            ],
          }}
          options={{ responsive: true, maintainAspectRatio: false }}
        />
      </div>

      <hr className="mt-5" />

      <h3>Leads por Origen</h3>
      <div style={{ maxWidth: 600, height: 300 }}>
        <Bar
          data={{
            labels: (series.leads_por_origen || []).map(([origen]) => origen),
            datasets: [
              {
                label: "Cantidad",
                data: (series.leads_por_origen || []).map(([, qty]) => qty),
              },
            ],
          }}
          options={{ responsive: true, maintainAspectRatio: false }}
        />
      </div>

      <hr className="mt-5" />

      <h3>Top Campañas por Leads</h3>
      <div style={{ maxWidth: 700 }}>
        <table className="table">
          <thead>
            <tr>
              <th>Campaña</th>
              <th>Leads</th>
            </tr>
          </thead>
          <tbody>
            {(series.top_campanias_por_leads || []).length ? (
              series.top_campanias_por_leads.map(([name, qty]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{qty}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={2} className="text-muted">
                  Sin datos
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

    </div>
  );
}

export default DashboardComercial;
