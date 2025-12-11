// frontend/src/pages/Dashboard.jsx
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
} from "chart.js";

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const API_BASE = "/api";

function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({
    total_products: 0,
    total_locations: 0,
    total_stock_records: 0,
    stock_per_unit: [],
    stock_per_location: [],
  });

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError("");
        const res = await axios.get(`${API_BASE}/dashboard`);
        setData(res.data);
      } catch (err) {
        console.error(err);
        setError("No se pudo cargar el dashboard (error API)");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const stockUnitLabels = data.stock_per_unit.map(([name]) => name);
  const stockUnitValues = data.stock_per_unit.map(([, qty]) => qty);

  return (
    <div>
      <h1>Dashboard General</h1>

      <div className="row mt-4">
        <div className="col-md-4">
          <div className="card text-center">
            <h4>Productos</h4>
            <p className="display-6">{data.total_products}</p>
          </div>
        </div>

        <div className="col-md-4">
          <div className="card text-center">
            <h4>Ubicaciones</h4>
            <p className="display-6">{data.total_locations}</p>
          </div>
        </div>

        <div className="col-md-4">
          <div className="card text-center">
            <h4>Registros de Stock</h4>
            <p className="display-6">{data.total_stock_records}</p>
          </div>
        </div>
      </div>

      <hr className="mt-5" />

      <h3>Stock por Unidad de Negocio</h3>

      <div style={{ maxWidth: 600, height: 300 }}>
        <Bar
          data={{
            labels: stockUnitLabels,
            datasets: [
              {
                label: "Cantidad en Stock",
                data: stockUnitValues,
              },
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              y: { beginAtZero: true },
            },
          }}
        />
      </div>

      <hr className="mt-5" />

      <h3>Stock por Ubicación</h3>

      <table className="table">
        <thead>
          <tr>
            <th>Ubicación</th>
            <th>Stock Total</th>
          </tr>
        </thead>
        <tbody>
          {data.stock_per_location.map(([name, qty]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{qty}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {loading && <p>Cargando...</p>}
      {error && <p>{error}</p>}
    </div>
  );
}

export default Dashboard;
