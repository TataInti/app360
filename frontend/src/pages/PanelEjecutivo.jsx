// frontend/src/pages/PanelEjecutivo.jsx
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

function PanelEjecutivo() {
  const [data, setData] = useState({
    total_leads: 0,
    total_products: 0,
    total_locations: 0,
    conversion: 0,
    leads_por_estado: {},
    stock_por_unidad: [],
    stock_bajo: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError("");
        const res = await axios.get(`${API_BASE}/panel-ejecutivo`);
        setData(res.data);
      } catch (err) {
        console.error(err);
        setError("No se pudo cargar el panel ejecutivo (error API)");
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
      <h1>Panel Ejecutivo Global</h1>

      <div className="row mt-4">
        <div className="col-md-3">
          <div className="card text-center">
            <h5>Total Leads</h5>
            <p className="display-6">{data.total_leads}</p>
          </div>
        </div>

        <div className="col-md-3">
          <div className="card text-center">
            <h5>Total Productos</h5>
            <p className="display-6">{data.total_products}</p>
          </div>
        </div>

        <div className="col-md-3">
          <div className="card text-center">
            <h5>Total Ubicaciones</h5>
            <p className="display-6">{data.total_locations}</p>
          </div>
        </div>

        <div className="col-md-3">
          <div className="card text-center">
            <h5>Conversión Comercial</h5>
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

      <h3>Stock por Unidad de Negocio</h3>
      <div style={{ maxWidth: 500, height: 300 }}>
        <Pie
          data={{
            labels: data.stock_por_unidad.map(([name]) => name),
            datasets: [
              {
                data: data.stock_por_unidad.map(([, qty]) => qty),
              },
            ],
          }}
          options={{ responsive: true, maintainAspectRatio: false }}
        />
      </div>

      <hr className="mt-5" />

      <h3>Productos con Stock Bajo</h3>
      {data.stock_bajo.length > 0 ? (
        <table className="table">
          <thead>
            <tr>
              <th>Producto</th>
              <th>Cantidad Total</th>
            </tr>
          </thead>
          <tbody>
            {data.stock_bajo.map(([name, qty]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{qty}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>No hay productos con stock bajo.</p>
      )}

      {loading && <p>Cargando...</p>}
      {error && <p>{error}</p>}
    </div>
  );
}

export default PanelEjecutivo;
