// frontend/src/pages/PanelEjecutivo.jsx
import React, { useEffect, useMemo, useState } from "react";
import { Doughnut } from "react-chartjs-2";
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from "chart.js";

import apiService from "../services/api";

ChartJS.register(ArcElement, Tooltip, Legend);

function formatMoney(value) {
  const n = Number(value || 0);
  return (
    "$" +
    (Number.isFinite(n) ? n : 0).toLocaleString("es-AR", {
      maximumFractionDigits: 0,
    })
  );
}

function PanelEjecutivo() {
  const [data, setData] = useState({
    period: "ytd",
    desde: null,
    hasta: null,
    kpis: {},
    top_clientes: [],
    instrumentos: { labels: [], values: [] },
    friar: { cuenta: null, ultimos_pagos: [] },
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError("");
        const res = await apiService.getPanelEjecutivoV2("ytd");
        setData(res);
      } catch (err) {
        console.error(err);
        setError("No se pudo cargar el panel ejecutivo (error API)");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const instrumentosChart = useMemo(() => {
    const labels = data.instrumentos?.labels || [];
    const values = (data.instrumentos?.values || []).map((x) => Number(x || 0));
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
  }, [data.instrumentos]);

  const kpis = data.kpis || {};

  return (
    <div>
      <h1>Panel Ejecutivo</h1>

      <div className="text-muted small mt-2">
        Período: {data.desde || "-"} → {data.hasta || "-"}
      </div>

      <div className="row mt-4 g-3">
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Ingresos (SabioGo)</h6>
            <p className="display-6">{formatMoney(kpis.sabiogo_ingresos)}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Costos (SabioGo)</h6>
            <p className="display-6">{formatMoney(kpis.sabiogo_costos)}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Margen (SabioGo)</h6>
            <p className="display-6">{formatMoney(kpis.sabiogo_margen)}</p>
          </div>
        </div>
        <div className="col-md-3">
          <div className="card text-center">
            <h6 className="mt-3">Saldo c/c Friar</h6>
            <p className="display-6">{formatMoney(kpis.cta_cte_friar_saldo_actual)}</p>
          </div>
        </div>
      </div>

      <hr className="mt-5" />

      <div className="row g-3">
        <div className="col-lg-5">
          <div className="card p-3" style={{ height: 360 }}>
            <h4>Distribución de instrumentos</h4>
            <div style={{ height: 280 }}>
              <Doughnut
                data={instrumentosChart.data}
                options={instrumentosChart.options}
              />
            </div>
          </div>
        </div>

        <div className="col-lg-7">
          <div className="card p-3">
            <h4>Top 5 clientes por monto (SabioGo)</h4>
            <table className="table table-sm">
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th className="text-end">Monto</th>
                </tr>
              </thead>
              <tbody>
                {data.top_clientes?.length ? (
                  data.top_clientes.map((r) => (
                    <tr key={r.cliente}>
                      <td>{r.cliente}</td>
                      <td className="text-end">{formatMoney(r.monto)}</td>
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
      </div>

      <hr className="mt-5" />

      <div className="row g-3">
        <div className="col-lg-6">
          <div className="card p-3">
            <h4>Cuenta Corriente Friar</h4>
            {data.friar?.cuenta ? (
              <div className="small">
                <div>
                  <strong>Proveedor:</strong> {data.friar.cuenta.proveedor || "-"}
                </div>
                <div>
                  <strong>Saldo inicial:</strong> {formatMoney(data.friar.cuenta.saldo_inicial)}
                </div>
                <div>
                  <strong>Total pagos:</strong> {formatMoney(data.friar.cuenta.total_pagos)}
                </div>
                <div>
                  <strong>Saldo actual:</strong> {formatMoney(data.friar.cuenta.saldo_actual)}
                </div>
              </div>
            ) : (
              <div className="text-muted">Sin cuenta configurada</div>
            )}
          </div>
        </div>

        <div className="col-lg-6">
          <div className="card p-3">
            <h4>Últimos 5 pagos a Friar</h4>
            <table className="table table-sm">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Instrumento</th>
                  <th className="text-end">Monto</th>
                </tr>
              </thead>
              <tbody>
                {data.friar?.ultimos_pagos?.length ? (
                  data.friar.ultimos_pagos.map((p, idx) => (
                    <tr key={`${p.fecha || ""}-${idx}`}>
                      <td>{p.fecha ? String(p.fecha).slice(0, 10) : "-"}</td>
                      <td>{p.instrumento || "-"}</td>
                      <td className="text-end">{formatMoney(p.monto)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={3} className="text-muted">
                      Sin datos
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {loading && <p>Cargando...</p>}
      {error && <p>{error}</p>}
    </div>
  );
}

export default PanelEjecutivo;
