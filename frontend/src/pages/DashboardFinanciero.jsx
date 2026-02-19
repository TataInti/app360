import React, { useEffect, useMemo, useState } from "react";
import { Bar, Doughnut } from "react-chartjs-2";
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  LineElement,
  PointElement,
  ArcElement,
} from "chart.js";
import apiService from "../services/api";

ChartJS.register(
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  LineElement,
  PointElement,
  ArcElement
);

const PERIODS = [
  { key: "7", label: "7d" },
  { key: "15", label: "15d" },
  { key: "30", label: "30d" },
  { key: "ytd", label: "YTD" },
];

function formatMoney(value) {
  const n = Number(value || 0);
  return (
    "$" +
    (Number.isFinite(n) ? n : 0).toLocaleString("es-AR", {
      maximumFractionDigits: 0,
    })
  );
}

function formatPct(value) {
  const n = Number(value || 0);
  return `${(Number.isFinite(n) ? n : 0).toFixed(1)} %`;
}

function formatLabelPeriodo(label, granularidad) {
  if (!label) return "-";
  if (granularidad === "mes") return String(label);
  // label esperado: YYYY-MM-DD
  const parts = String(label).split("-");
  if (parts.length !== 3) return String(label);
  return `${parts[2]}/${parts[1]}`;
}

export default function DashboardFinanciero() {
  const [period, setPeriod] = useState("30");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState({ kpis: {}, series: {} });

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        setLoading(true);
        setError("");
        const data = await apiService.getDashboardFinanciero(period);
        if (!cancelled) setPayload(data);
      } catch (e) {
        console.error(e);
        if (!cancelled) {
          setError(
            "No se pudo cargar el dashboard financiero. Verifica la conexión con el servidor."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => {
      cancelled = true;
    };
  }, [period]);

  const kpis = payload.kpis || {};
  const series = payload.series || {};

  const flujoChart = useMemo(() => {
    const flujo = series.flujo || {};
    const labelsRaw = flujo.labels || [];
    const granularidad = flujo.granularidad || "dia";

    const labels = labelsRaw.map((l) => formatLabelPeriodo(l, granularidad));
    const ingresos = (flujo.ingresos || []).map((x) => Number(x || 0));
    const egresos = (flujo.egresos || []).map((x) => Number(x || 0));
    const neto = (flujo.neto || []).map((x) => Number(x || 0));

    return {
      data: {
        labels,
        datasets: [
          {
            type: "bar",
            label: "Ingresos",
            data: ingresos,
            backgroundColor: "rgba(34, 197, 94, 0.25)",
            borderColor: "#16a34a",
            borderWidth: 1,
          },
          {
            type: "bar",
            label: "Egresos",
            data: egresos,
            backgroundColor: "rgba(239, 68, 68, 0.25)",
            borderColor: "#dc2626",
            borderWidth: 1,
          },
          {
            type: "line",
            label: "Neto",
            data: neto,
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.10)",
            tension: 0.35,
            pointRadius: 2,
            pointHoverRadius: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: "#111827" },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const v = Number(ctx.parsed?.y ?? ctx.parsed ?? 0);
                const label = ctx.dataset?.label ? `${ctx.dataset.label}: ` : "";
                return label + formatMoney(v);
              },
            },
          },
        },
        scales: {
          x: {
            ticks: { color: "#374151" },
            grid: { color: "rgba(55, 65, 81, 0.12)" },
          },
          y: {
            ticks: {
              color: "#374151",
              callback: (value) => formatMoney(value),
            },
            grid: { color: "rgba(55, 65, 81, 0.12)" },
          },
        },
      },
    };
  }, [series.flujo]);

  const instrumentosChart = useMemo(() => {
    const inst = series.instrumentos || {};
    const labels = inst.labels || [];
    const values = (inst.values || []).map((x) => Number(x || 0));

    return {
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: [
              "rgba(59, 130, 246, 0.35)",
              "rgba(34, 197, 94, 0.35)",
              "rgba(245, 158, 11, 0.35)",
              "rgba(236, 72, 153, 0.35)",
              "rgba(99, 102, 241, 0.35)",
              "rgba(20, 184, 166, 0.35)",
              "rgba(239, 68, 68, 0.35)",
            ],
            borderColor: [
              "#3b82f6",
              "#22c55e",
              "#f59e0b",
              "#ec4899",
              "#6366f1",
              "#14b8a6",
              "#ef4444",
            ],
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: "#111827" },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const label = ctx.label ? `${ctx.label}: ` : "";
                return label + formatMoney(ctx.parsed || 0);
              },
            },
          },
        },
      },
    };
  }, [series.instrumentos]);

  if (loading) return <div className="loading">Cargando dashboard financiero...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="dashboard-financiero-page">
      <div className="page-header">
        <h1>Dashboard Financiero</h1>
        <div className="btn-group mt-2" role="group" aria-label="Período">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              className={`btn ${period === p.key ? "btn-primary" : "btn-outline-primary"}`}
              onClick={() => setPeriod(p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="text-muted small mt-2">
          Período: {kpis.desde || "-"} → {kpis.hasta || "-"}
        </div>
      </div>

      <div className="row mt-4 g-3">
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Ingresos</h6>
            <p className="display-6">{formatMoney(kpis.ingresos_total)}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Egresos</h6>
            <p className="display-6">{formatMoney(kpis.egresos_total)}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Neto</h6>
            <p className="display-6">{formatMoney(kpis.neto)}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Movimientos</h6>
            <p className="display-6">{kpis.movimientos_total || 0}</p>
          </div>
        </div>

        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Ticket promedio</h6>
            <p className="display-6">{formatMoney(kpis.ticket_promedio)}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Egresos/Ingresos</h6>
            <p className="display-6">{formatPct(kpis.egresos_sobre_ingresos_pct)}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Días neto negativo</h6>
            <p className="display-6">{kpis.dias_neto_negativo || 0}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Empleados con adelantos/préstamos</h6>
            <p className="display-6">{kpis.rrhh_empleados_con_adelantos_prestamos || 0}</p>
          </div>
        </div>

        <div className="col-md-6">
          <div className="card text-center">
            <h6 className="mt-3">Monto adelantos/préstamos (período)</h6>
            <p className="display-6">{formatMoney(kpis.rrhh_monto_adelantos_prestamos)}</p>
          </div>
        </div>
        <div className="col-md-6">
          <div className="card text-center">
            <h6 className="mt-3">Saldo pendiente préstamos (global)</h6>
            <p className="display-6">{formatMoney(kpis.rrhh_monto_pendiente_prestamos)}</p>
          </div>
        </div>
      </div>

      <hr className="mt-5" />

      <div className="row g-3">
        <div className="col-lg-7">
          <div className="card p-3" style={{ height: 360 }}>
            <h5>Flujo de caja</h5>
            <div style={{ height: 280 }}>
              <Bar data={flujoChart.data} options={flujoChart.options} />
            </div>
          </div>
        </div>
        <div className="col-lg-5">
          <div className="card p-3" style={{ height: 360 }}>
            <h5>Distribución por instrumento</h5>
            <div style={{ height: 280 }}>
              <Doughnut
                data={instrumentosChart.data}
                options={instrumentosChart.options}
              />
            </div>
          </div>
        </div>
      </div>

      <hr className="mt-5" />

      <div className="row g-3">
        <div className="col-lg-6">
          <div className="card p-3">
            <h5>Máximo ingreso</h5>
            {kpis.max_ingreso ? (
              <div className="small">
                <div>
                  <strong>{formatMoney(kpis.max_ingreso.monto)}</strong> · {kpis.max_ingreso.instrumento || "-"}
                </div>
                <div className="text-muted">{kpis.max_ingreso.fecha_hora || ""}</div>
                <div>{kpis.max_ingreso.descripcion || ""}</div>
              </div>
            ) : (
              <div className="text-muted">Sin datos</div>
            )}
          </div>
        </div>
        <div className="col-lg-6">
          <div className="card p-3">
            <h5>Máximo egreso</h5>
            {kpis.max_egreso ? (
              <div className="small">
                <div>
                  <strong>{formatMoney(kpis.max_egreso.monto)}</strong> · {kpis.max_egreso.instrumento || "-"}
                </div>
                <div className="text-muted">{kpis.max_egreso.fecha_hora || ""}</div>
                <div>{kpis.max_egreso.descripcion || ""}</div>
              </div>
            ) : (
              <div className="text-muted">Sin datos</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
