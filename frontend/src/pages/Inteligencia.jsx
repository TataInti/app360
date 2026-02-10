import React, { useEffect, useMemo, useState } from "react";
import { Bar, Doughnut, Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  BarElement,
  ArcElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";
import apiService from "../services/api";

ChartJS.register(
  BarElement,
  ArcElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend
);

const currencyFmt = new Intl.NumberFormat("es-ES", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
});

const percentFmt = (value) => `${(value * 100).toFixed(1)}%`;

function KPIStat({ title, value, delta }) {
  const isUp = delta !== undefined && delta >= 0;
  const deltaClass = delta === undefined ? "" : isUp ? "delta-up" : "delta-down";
  const deltaText = delta === undefined ? null : `${isUp ? "▲" : "▼"} ${(delta * 100).toFixed(1)}%`;

  return (
    <div className="kpi-card">
      <p className="kpi-title">{title}</p>
      <p className="kpi-value">{value}</p>
      {deltaText && <span className={`kpi-delta ${deltaClass}`}>{deltaText}</span>}
    </div>
  );
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="chart-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
        <h4 className="section-title">{title}</h4>
        {subtitle && <span className="subtle">{subtitle}</span>}
      </div>
      {children}
    </div>
  );
}

function Pill({ active, label, onClick }) {
  return (
    <button className={`pill-button ${active ? "active" : ""}`} onClick={onClick}>
      {label}
    </button>
  );
}

function useTabData(tab, range) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const params = `range=${range}`;
        let response;
        if (tab === "overview") {
          response = await apiService.getInteligenciaOverview(params);
        } else if (tab === "rentabilidad") {
          response = await apiService.getInteligenciaRentabilidad(params);
        } else {
          response = await apiService.getInteligenciaEficiencia(params);
        }
        if (active) {
          setData(response);
        }
      } catch (err) {
        console.warn("Falling back to mock inteligencia data", err);
        if (active) {
          setData(getFallbackData(tab));
          setError("Usando datos de ejemplo. Conecta /api/bi/* para cifras reales.");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [tab, range]);

  return { data, loading, error };
}

function getFallbackData(tab) {
  if (tab === "overview") {
    return {
      kpis: {
        cash_flow: 420000,
        ebitda: 210000,
        gross_margin: 0.54,
        net_margin: 0.21,
        burn_rate: 95000,
        runway_months: 9.5,
        deltas: {
          cash_flow: 0.08,
          ebitda: 0.06,
          gross_margin: 0.02,
          net_margin: -0.01,
          burn_rate: -0.05,
          runway_months: 0.07,
        },
      },
      mix_ingresos: {
        labels: ["Servicios", "Productos", "Proyectos", "Soporte"],
        valores: [42, 28, 18, 12],
      },
      ingresos_costos: {
        labels: ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar"],
        ingresos: [380, 410, 430, 455, 470, 495],
        costos: [240, 250, 260, 270, 280, 285],
        ebitda: [110, 125, 140, 155, 160, 170],
      },
      top_series: {
        labels: ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar"],
        cash_flow: [60, 85, 70, 95, 110, 120],
        burn: [90, 92, 95, 97, 96, 94],
      },
    };
  }

  if (tab === "rentabilidad") {
    return {
      kpis: {
        gross_margin: 0.54,
        net_margin: 0.21,
        ebitda_margin: 0.27,
        ltv_cac: 3.4,
        deltas: {
          gross_margin: 0.01,
          net_margin: -0.02,
          ebitda_margin: 0.02,
          ltv_cac: 0.3,
        },
      },
      margen_unidades: {
        labels: ["Servicios", "Productos", "Proyectos", "Soporte"],
        bruto: [58, 45, 62, 55],
        neto: [28, 18, 30, 24],
      },
      mix_costos: {
        labels: ["Operativos", "Personal", "Marketing", "Infra"],
        valores: [38, 32, 18, 12],
      },
      margen_serie: {
        labels: ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar"],
        bruto: [0.5, 0.52, 0.55, 0.53, 0.54, 0.56],
        neto: [0.2, 0.22, 0.23, 0.21, 0.21, 0.24],
      },
      top_clientes: [
        { cliente: "Acme SA", margen: 0.32, ingreso: 180000 },
        { cliente: "Globex", margen: 0.28, ingreso: 140000 },
        { cliente: "Innova", margen: 0.25, ingreso: 120000 },
      ],
      alertas: [
        { unidad: "Productos", margen: 0.18, objetivo: 0.22 },
        { unidad: "Soporte", margen: 0.16, objetivo: 0.20 },
      ],
    };
  }

  return {
    kpis: {
      cash_balance: 760000,
      cash_in: 520000,
      cash_out: 395000,
      dso: 52,
      dpo: 38,
      inventory_days: 41,
      burn_rate: 95000,
      runway_months: 9.5,
      arpu: 860,
      payback_months: 7.2,
      deltas: {
        cash_balance: 0.04,
        cash_in: 0.09,
        cash_out: -0.03,
        dso: -0.05,
        dpo: 0.02,
        inventory_days: -0.04,
        burn_rate: -0.05,
        runway_months: 0.07,
        arpu: 0.06,
        payback_months: -0.08,
      },
    },
    cash_flow: {
      labels: ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar"],
      cash_in: [320, 340, 360, 380, 410, 440],
      cash_out: [260, 270, 295, 305, 320, 325],
      balance: [420, 430, 450, 480, 520, 575],
    },
    eficiencia: {
      labels: ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar"],
      dso: [58, 56, 54, 53, 52, 50],
      dpo: [34, 35, 36, 37, 38, 39],
      inventory: [48, 46, 44, 43, 41, 40],
    },
    gastos_mix: {
      labels: ["OPEX", "CAPEX", "Nómina", "Marketing"],
      valores: [44, 18, 28, 10],
    },
    cobranzas: [
      { cliente: "Acme SA", monto: 68000, vencimiento: "2026-02-15" },
      { cliente: "Globex", monto: 52000, vencimiento: "2026-02-20" },
      { cliente: "Innova", monto: 38000, vencimiento: "2026-02-24" },
    ],
  };
}

function Inteligencia() {
  const [tab, setTab] = useState("overview");
  const [range, setRange] = useState("6m");
  const { data, loading, error } = useTabData(tab, range);

  const charts = useMemo(() => buildCharts(tab, data), [tab, data]);

  return (
    <div className="int-page">
      <div className="page-header">
        <div>
          <h1>Inteligencia Financiera</h1>
          <div className="inline-meta">
            <span>Enfoque: cash flow, EBITDA, márgenes</span>
            <span>Horizonte: 6 meses</span>
          </div>
        </div>
        <div className="pill-group">
          <Pill label="6M" active={range === "6m"} onClick={() => setRange("6m")} />
          <Pill label="12M" active={range === "12m"} onClick={() => setRange("12m")} />
          <Pill label="24M" active={range === "24m"} onClick={() => setRange("24m")} />
        </div>
      </div>

      <div className="int-tabs">
        <button className={`int-tab ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>
          Overview
        </button>
        <button className={`int-tab ${tab === "rentabilidad" ? "active" : ""}`} onClick={() => setTab("rentabilidad")}>
          Rentabilidad
        </button>
        <button className={`int-tab ${tab === "eficiencia" ? "active" : ""}`} onClick={() => setTab("eficiencia")}>
          Cash & Eficiencia
        </button>
      </div>

      {loading && <div className="loading">Cargando inteligencia...</div>}
      {error && <div className="error">{error}</div>}

      {!loading && data && (
        <>
          {tab === "overview" && <OverviewView data={data} charts={charts} />}
          {tab === "rentabilidad" && <RentabilidadView data={data} charts={charts} />}
          {tab === "eficiencia" && <EficienciaView data={data} charts={charts} />}
        </>
      )}
    </div>
  );
}

function OverviewView({ data, charts }) {
  const k = data.kpis || {};
  const d = k.deltas || {};
  return (
    <>
      <div className="kpi-grid">
        <KPIStat title="Cash Flow 30d" value={currencyFmt.format(k.cash_flow || 0)} delta={d.cash_flow} />
        <KPIStat title="EBITDA 30d" value={currencyFmt.format(k.ebitda || 0)} delta={d.ebitda} />
        <KPIStat title="Margen Bruto" value={percentFmt(k.gross_margin || 0)} delta={d.gross_margin} />
        <KPIStat title="Margen Neto" value={percentFmt(k.net_margin || 0)} delta={d.net_margin} />
        <KPIStat title="Burn Rate" value={currencyFmt.format(k.burn_rate || 0)} delta={d.burn_rate} />
        <KPIStat title="Runway (meses)" value={`${(k.runway_months || 0).toFixed(1)} m`} delta={d.runway_months} />
      </div>

      <div className="charts-grid">
        <ChartCard title="Ingresos vs Costos vs EBITDA" subtitle="Serie mensual">
          <Line data={charts.ingresosCostos} options={lineOptions()} height={280} />
        </ChartCard>
        <ChartCard title="Mix de Ingresos" subtitle="Composición actual">
          <Doughnut data={charts.mixIngresos} options={doughnutOptions()} height={280} />
        </ChartCard>
      </div>

      <div className="charts-grid">
        <ChartCard title="Cash Flow neto" subtitle="Últimos 6 meses">
          <Bar data={charts.cashFlow} options={barOptions("Cash neto", "USD")()} height={280} />
        </ChartCard>
        <ChartCard title="Burn mensual" subtitle="Tendencia">
          <Line data={charts.burn} options={lineOptions()} height={280} />
        </ChartCard>
      </div>
    </>
  );
}

function RentabilidadView({ data, charts }) {
  const k = data.kpis || {};
  const d = k.deltas || {};
  return (
    <>
      <div className="kpi-grid">
        <KPIStat title="Margen Bruto" value={percentFmt(k.gross_margin || 0)} delta={d.gross_margin} />
        <KPIStat title="Margen Neto" value={percentFmt(k.net_margin || 0)} delta={d.net_margin} />
        <KPIStat title="Margen EBITDA" value={percentFmt(k.ebitda_margin || 0)} delta={d.ebitda_margin} />
        <KPIStat title="LTV/CAC" value={`x${(k.ltv_cac || 0).toFixed(1)}`} delta={d.ltv_cac} />
      </div>

      <div className="charts-grid">
        <ChartCard title="Margen por Unidad" subtitle="Bruto y Neto">
          <Bar data={charts.margenUnidades} options={barOptions("Margen", "%", true)} height={280} />
        </ChartCard>
        <ChartCard title="Mix de Costos" subtitle="OPEX vs CAPEX">
          <Doughnut data={charts.mixCostos} options={doughnutOptions()} height={280} />
        </ChartCard>
      </div>

      <div className="charts-grid">
        <ChartCard title="Serie de Margen" subtitle="Bruto y Neto 6 meses">
          <Line data={charts.margenSerie} options={lineOptions(true)} height={280} />
        </ChartCard>
        <div className="table-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <h4 className="section-title">Top Clientes por Margen</h4>
            <span className="subtle">Top 3</span>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Margen</th>
                <th>Ingreso</th>
              </tr>
            </thead>
            <tbody>
              {(data.top_clientes || []).map((c) => (
                <tr key={c.cliente}>
                  <td>{c.cliente}</td>
                  <td>{percentFmt(c.margen || 0)}</td>
                  <td>{currencyFmt.format(c.ingreso || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h4 className="section-title" style={{ marginTop: "1rem" }}>Alertas de margen</h4>
          <div className="inline-meta">
            {(data.alertas || []).length === 0 && <span className="subtle">Sin alertas</span>}
            {(data.alertas || []).map((a) => (
              <span key={a.unidad} className="tag">
                {a.unidad}: {percentFmt(a.margen || 0)} (obj {percentFmt(a.objetivo || 0)})
              </span>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function EficienciaView({ data, charts }) {
  const k = data.kpis || {};
  const d = k.deltas || {};
  return (
    <>
      <div className="kpi-grid">
        <KPIStat title="Saldo de Caja" value={currencyFmt.format(k.cash_balance || 0)} delta={d.cash_balance} />
        <KPIStat title="Cash In" value={currencyFmt.format(k.cash_in || 0)} delta={d.cash_in} />
        <KPIStat title="Cash Out" value={currencyFmt.format(k.cash_out || 0)} delta={d.cash_out} />
        <KPIStat title="DSO" value={`${k.dso || 0} días`} delta={d.dso} />
        <KPIStat title="DPO" value={`${k.dpo || 0} días`} delta={d.dpo} />
        <KPIStat title="Días Inventario" value={`${k.inventory_days || 0} días`} delta={d.inventory_days} />
        <KPIStat title="Burn Rate" value={currencyFmt.format(k.burn_rate || 0)} delta={d.burn_rate} />
        <KPIStat title="Runway" value={`${(k.runway_months || 0).toFixed(1)} m`} delta={d.runway_months} />
        <KPIStat title="ARPU" value={currencyFmt.format(k.arpu || 0)} delta={d.arpu} />
        <KPIStat title="Payback" value={`${(k.payback_months || 0).toFixed(1)} m`} delta={d.payback_months} />
      </div>

      <div className="charts-grid">
        <ChartCard title="Cash In/Out y Saldo" subtitle="Serie 6 meses">
          <Line data={charts.cashFlow} options={lineOptions()} height={280} />
        </ChartCard>
        <ChartCard title="DSO, DPO, Inventario" subtitle="Días operativos">
          <Line data={charts.eficiencia} options={lineOptions()} height={280} />
        </ChartCard>
      </div>

      <div className="charts-grid">
        <ChartCard title="Composición de Gastos" subtitle="OPEX vs CAPEX">
          <Doughnut data={charts.gastosMix} options={doughnutOptions()} height={280} />
        </ChartCard>
        <div className="table-card">
          <h4 className="section-title" style={{ marginBottom: "0.75rem" }}>Cobranzas próximas</h4>
          <table className="table">
            <thead>
              <tr>
                <th>Cliente</th>
                <th>Monto</th>
                <th>Vencimiento</th>
              </tr>
            </thead>
            <tbody>
              {(data.cobranzas || []).map((c) => (
                <tr key={`${c.cliente}-${c.vencimiento}`}>
                  <td>{c.cliente}</td>
                  <td>{currencyFmt.format(c.monto || 0)}</td>
                  <td>{c.vencimiento}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function buildCharts(tab, data) {
  if (!data) return {};

  if (tab === "overview") {
    return {
      ingresosCostos: {
        labels: data.ingresos_costos?.labels || [],
        datasets: [
          {
            label: "Ingresos",
            data: data.ingresos_costos?.ingresos || [],
            borderColor: "#2563eb",
            backgroundColor: "rgba(37, 99, 235, 0.12)",
            tension: 0.35,
            fill: true,
          },
          {
            label: "Costos",
            data: data.ingresos_costos?.costos || [],
            borderColor: "#ef4444",
            backgroundColor: "rgba(239, 68, 68, 0.12)",
            tension: 0.35,
            fill: true,
          },
          {
            label: "EBITDA",
            data: data.ingresos_costos?.ebitda || [],
            borderColor: "#16a34a",
            backgroundColor: "rgba(22, 163, 74, 0.12)",
            tension: 0.35,
            fill: false,
          },
        ],
      },
      mixIngresos: {
        labels: data.mix_ingresos?.labels || [],
        datasets: [
          {
            data: data.mix_ingresos?.valores || [],
            backgroundColor: ["#2563eb", "#16a34a", "#f59e0b", "#a855f7", "#0ea5e9"],
          },
        ],
      },
      cashFlow: {
        labels: data.top_series?.labels || [],
        datasets: [
          {
            type: "bar",
            label: "Cash neto",
            data: data.top_series?.cash_flow || [],
            backgroundColor: "#2563eb",
            borderRadius: 6,
          },
        ],
      },
      burn: {
        labels: data.top_series?.labels || [],
        datasets: [
          {
            label: "Burn",
            data: data.top_series?.burn || [],
            borderColor: "#ef4444",
            backgroundColor: "rgba(239, 68, 68, 0.12)",
            tension: 0.35,
            fill: true,
          },
        ],
      },
    };
  }

  if (tab === "rentabilidad") {
    return {
      margenUnidades: {
        labels: data.margen_unidades?.labels || [],
        datasets: [
          {
            label: "Bruto %",
            data: data.margen_unidades?.bruto || [],
            backgroundColor: "rgba(37, 99, 235, 0.7)",
            borderRadius: 6,
          },
          {
            label: "Neto %",
            data: data.margen_unidades?.neto || [],
            backgroundColor: "rgba(22, 163, 74, 0.7)",
            borderRadius: 6,
          },
        ],
      },
      mixCostos: {
        labels: data.mix_costos?.labels || [],
        datasets: [
          {
            data: data.mix_costos?.valores || [],
            backgroundColor: ["#2563eb", "#16a34a", "#f59e0b", "#a855f7", "#0ea5e9"],
          },
        ],
      },
      margenSerie: {
        labels: data.margen_serie?.labels || [],
        datasets: [
          {
            label: "Bruto %",
            data: (data.margen_serie?.bruto || []).map((v) => v * 100),
            borderColor: "#2563eb",
            backgroundColor: "rgba(37, 99, 235, 0.12)",
            tension: 0.35,
            fill: true,
          },
          {
            label: "Neto %",
            data: (data.margen_serie?.neto || []).map((v) => v * 100),
            borderColor: "#16a34a",
            backgroundColor: "rgba(22, 163, 74, 0.12)",
            tension: 0.35,
            fill: true,
          },
        ],
      },
    };
  }

  return {
    cashFlow: {
      labels: data.cash_flow?.labels || [],
      datasets: [
        {
          label: "Cash In",
          data: data.cash_flow?.cash_in || [],
          borderColor: "#16a34a",
          backgroundColor: "rgba(22, 163, 74, 0.12)",
          tension: 0.35,
          fill: true,
        },
        {
          label: "Cash Out",
          data: data.cash_flow?.cash_out || [],
          borderColor: "#ef4444",
          backgroundColor: "rgba(239, 68, 68, 0.12)",
          tension: 0.35,
          fill: true,
        },
        {
          label: "Saldo",
          data: data.cash_flow?.balance || [],
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.1)",
          tension: 0.35,
          fill: false,
        },
      ],
    },
    eficiencia: {
      labels: data.eficiencia?.labels || [],
      datasets: [
        {
          label: "DSO",
          data: data.eficiencia?.dso || [],
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.12)",
          tension: 0.35,
          fill: false,
        },
        {
          label: "DPO",
          data: data.eficiencia?.dpo || [],
          borderColor: "#16a34a",
          backgroundColor: "rgba(22, 163, 74, 0.12)",
          tension: 0.35,
          fill: false,
        },
        {
          label: "Inventario",
          data: data.eficiencia?.inventory || [],
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.12)",
          tension: 0.35,
          fill: false,
        },
      ],
    },
    gastosMix: {
      labels: data.gastos_mix?.labels || [],
      datasets: [
        {
          data: data.gastos_mix?.valores || [],
          backgroundColor: ["#2563eb", "#16a34a", "#f59e0b", "#a855f7", "#0ea5e9"],
        },
      ],
    },
  };
}

function barOptions(label = "Valor", unit = "", isPercent = false) {
  return () => ({
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { stacked: false, grid: { display: false } },
      y: {
        beginAtZero: true,
        ticks: {
          callback: (v) => {
            if (isPercent) return `${v}%`;
            if (unit === "USD") return currencyFmt.format(v);
            return v;
          },
        },
      },
    },
    plugins: {
      legend: { display: true, position: "top" },
      tooltip: {
        callbacks: {
          label: (ctx) => {
            const val = ctx.parsed.y;
            if (isPercent) return `${ctx.dataset.label}: ${val}%`;
            if (unit === "USD") return `${ctx.dataset.label}: ${currencyFmt.format(val)}`;
            return `${ctx.dataset.label}: ${val}`;
          },
        },
      },
    },
    elements: { bar: { borderRadius: 6 } },
  });
}

function lineOptions(isPercent = false) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    tension: 0.35,
    interaction: { mode: "index", intersect: false },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          callback: (v) => (isPercent ? `${v}%` : v),
        },
      },
      x: { grid: { display: false } },
    },
    plugins: {
      legend: { position: "top" },
      tooltip: {
        callbacks: {
          label: (ctx) => {
            const val = ctx.parsed.y;
            if (isPercent) return `${ctx.dataset.label}: ${val.toFixed(1)}%`;
            return `${ctx.dataset.label}: ${val}`;
          },
        },
      },
    },
  };
}

function doughnutOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "right" },
      tooltip: {
        callbacks: {
          label: (ctx) => `${ctx.label}: ${ctx.parsed}%`,
        },
      },
    },
  };
}

export default Inteligencia;
