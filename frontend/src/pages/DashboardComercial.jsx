// frontend/src/pages/DashboardComercial.jsx
import React, { useEffect, useState } from "react";
import axios from "axios";
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

ChartJS.register(
  BarElement,
  ArcElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend
);

const API_BASE = "/api";

function DashboardComercial() {
  const [data, setData] = useState({
    total_leads: 0,
    leads_por_estado: {},
    conversion: 0,
    leads_por_unidad: [],
    leads_por_origen: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError("");
        const res = await axios.get(`${API_BASE}/dashboard-comercial`);
        setData(res.data);
      } catch (err) {
        console.error(err);
        setError("No se pudo cargar el dashboard comercial (error API)");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const estadoLabels = Object.keys(data.leads_por_estado);
  const estadoValues = Object.values(data.leads_por_estado);

  return (
    <div>
      <h1>Dashboard Comercial</h1>

      <div className="row mt-4">
        <div className="col-md-4">
          <div className="card text-center">
            <h4>Total de Leads</h4>
            <p className="display-6">{data.total_leads}</p>
          </div>
        </div>

        <div className="col-md-4">
          <div className="card text-center">
            <h4>Leads Ganados</h4>
            <p className="display-6">
              {data.leads_por_estado.ganado || 0}
            </p>
          </div>
        </div>

        <div className="col-md-4">
          <div className="card text-center">
            <h4>Conversión</h4>
            <p className="display-6">{data.conversion} %</p>
          </div>
        </div>
      </div>

      <hr className="mt-5" />

      <h3>Leads por Estado</h3>
      <div style={{ maxWidth: 600, height: 300 }}>
        <Bar
          data={{
            labels: estadoLabels,
            datasets: [
              {
                label: "Cantidad",
                data: estadoValues,
              },
            ],
          }}
          options={{ responsive: true, maintainAspectRatio: false }}
        />
      </div>

      <hr className="mt-5" />

      <h3>Leads por Unidad de Negocio</h3>
      <div style={{ maxWidth: 500, height: 300 }}>
        <Pie
          data={{
            labels: data.leads_por_unidad.map(([name]) => name),
            datasets: [
              {
                data: data.leads_por_unidad.map(([, qty]) => qty),
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
            labels: data.leads_por_origen.map(([origen]) => origen),
            datasets: [
              {
                label: "Cantidad",
                data: data.leads_por_origen.map(([, qty]) => qty),
              },
            ],
          }}
          options={{ responsive: true, maintainAspectRatio: false }}
        />
      </div>

      {loading && <p>Cargando...</p>}
      {error && <p>{error}</p>}
    </div>
  );
}

export default DashboardComercial;
