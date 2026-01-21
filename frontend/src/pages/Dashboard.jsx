// frontend/src/pages/Dashboard.jsx
import React, { useEffect, useState } from "react";
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
} from "chart.js";
import apiService from '../services/api';

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);

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
        const dashboardData = await apiService.getDashboard();
        setData(dashboardData);
      } catch (err) {
        console.error('Error loading dashboard:', err);
        setError("No se pudo cargar el dashboard. Verifica la conexión con el servidor.");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const stockUnitLabels = data.stock_per_unit.map(([name]) => name);
  const stockUnitValues = data.stock_per_unit.map(([, qty]) => qty);

  if (loading) {
    return <div className="loading">Cargando dashboard...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <h1>Dashboard General</h1>
      </div>

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

      <div className="card" style={{ maxWidth: 600, height: 300, margin: '0 auto' }}>
        <Bar
          data={{
            labels: stockUnitLabels,
            datasets: [
              {
                label: "Cantidad en Stock",
                data: stockUnitValues,
                backgroundColor: 'rgba(37, 99, 235, 0.8)',
                borderColor: 'rgba(37, 99, 235, 1)',
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
                    return `Stock: ${context.parsed.y} unidades`;
                  }
                }
              }
            }
          }}
        />
      </div>
    </div>
  );
}

export default Dashboard;

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
