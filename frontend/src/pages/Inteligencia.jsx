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

const TAB_LABELS = {
  liquidez: "Liquidez",
  rentabilidad: "Rentabilidad",
  eficiencia: "Eficiencia",
  proyecciones: "Proyecciones",
};

function KPIStat({ title, value, delta, badge }) {
  const isUp = delta !== undefined && delta >= 0;
  const deltaClass = delta === undefined ? "" : isUp ? "delta-up" : "delta-down";
  const deltaText = delta === undefined ? null : `${isUp ? "▲" : "▼"} ${(delta * 100).toFixed(1)}%`;

  return (
    <div className="kpi-card">
      <p className="kpi-title">{title}</p>
      <p className="kpi-value">{value}</p>
      <div className="kpi-meta">
        {deltaText && <span className={`kpi-delta ${deltaClass}`}>{deltaText}</span>}
        {badge && <span className="kpi-badge">{badge}</span>}
      </div>
    </div>
  );
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="chart-card">
      <div className="chart-card-head">
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

function useTabData(tab, range, scenario) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams();
        if (range) params.append("range", range);
        if (tab === "proyecciones" && scenario) params.append("scenario", scenario);

        let response;
        if (tab === "liquidez") {
          response = await apiService.getInteligenciaLiquidez(params.toString());
        } else if (tab === "rentabilidad") {
          response = await apiService.getInteligenciaRentabilidad(params.toString());
        } else if (tab === "proyecciones") {
          response = await apiService.getInteligenciaProyecciones(params.toString());
        } else {
          response = await apiService.getInteligenciaEficiencia(params.toString());
        }

        if (active) setData(response);
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
  }, [tab, range, scenario]);

  return { data, loading, error };
}

function getFallbackData(tab) {
  if (tab === "liquidez") {
    return {
      kpis: {
        cash_on_hand: 820000,
        fcf_30d: 125000,
        fcf_90d: 310000,
        burn: 95000,
        runway_months: 9.8,
        ccc: 54,
        nwc_ratio: 0.12,
        deltas: {
          cash_on_hand: 0.04,
          fcf_30d: 0.07,
          fcf_90d: 0.06,
          burn: -0.05,
          runway_months: 0.08,
          ccc: -0.03,
          nwc_ratio: 0.01,
        },
      },
      cash_weekly: {
        labels: ["W1", "W2", "W3", "W4", "W5", "W6"],
        cash_in: [180, 190, 210, 205, 215, 225],
        cash_out: [150, 160, 165, 170, 175, 172],
        balance: [420, 430, 450, 470, 495, 520],
      },
      aging_ar: { labels: ["0-30", "31-60", "61-90", "90+"], values: [42, 28, 18, 12] },
      aging_ap: { labels: ["0-30", "31-60", "61-90", "90+"], values: [38, 26, 22, 14] },
    };
  }

  if (tab === "rentabilidad") {
    return {
      kpis: {
        gross_margin: 0.55,
        ebitda_margin: 0.28,
        net_margin: 0.18,
        roic: 0.16,
        roe: 0.19,
        ltv_cac: 3.4,
        arpu: 860,
        payback_months: 7.2,
        deltas: {
          gross_margin: 0.01,
          ebitda_margin: 0.02,
          net_margin: -0.01,
          roic: 0.02,
          roe: 0.01,
          ltv_cac: 0.3,
          arpu: 0.05,
          payback_months: -0.1,
        },
      },
      margen_unidades: {
        labels: ["Servicios", "Productos", "Proyectos", "Soporte"],
        bruto: [58, 45, 62, 55],
        neto: [28, 18, 30, 24],
      },
      mix_costos: {
        labels: ["OPEX", "CAPEX", "Marketing", "Personal", "Infra"],
        valores: [34, 16, 18, 22, 10],
      },
      margen_serie: {
        labels: ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar"],
        bruto: [0.52, 0.53, 0.54, 0.55, 0.55, 0.56],
        neto: [0.17, 0.18, 0.18, 0.19, 0.18, 0.19],
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

  if (tab === "eficiencia") {
    return {
      kpis: {
        dso: 52,
        dpo: 41,
        dio: 40,
        ccc: 51,
        nwc_ratio: 0.11,
        overdue_ratio: 0.07,
        deltas: {
          dso: -0.05,
          dpo: 0.02,
          dio: -0.04,
          ccc: -0.06,
          nwc_ratio: 0.01,
          overdue_ratio: -0.02,
        },
      },
      eficiencia: {
        labels: ["Oct", "Nov", "Dic", "Ene", "Feb", "Mar"],
        dso: [58, 56, 54, 53, 52, 50],
        dpo: [34, 35, 36, 38, 40, 41],
        dio: [48, 46, 44, 43, 41, 40],
      },
      aging_ar: { labels: ["0-30", "31-60", "61-90", "90+"], values: [48, 24, 18, 10] },
      aging_ap: { labels: ["0-30", "31-60", "61-90", "90+"], values: [36, 28, 22, 14] },
      cobranzas: [
        { cliente: "Acme SA", monto: 68000, vencimiento: "2026-02-15" },
        { cliente: "Globex", monto: 52000, vencimiento: "2026-02-20" },
        { cliente: "Innova", monto: 38000, vencimiento: "2026-02-24" },
      ],
    };
  }

  return {
    kpis: {
      fcf_proj: 820000,
      debt_ebitda: 2.4,
      interest_coverage: 4.8,
      deltas: {
        fcf_proj: 0.05,
        debt_ebitda: -0.1,
        interest_coverage: 0.12,
      },
    },
    escenarios: {
      base: {
        labels: ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"],
        ingresos: [480, 500, 520, 540, 560, 580, 600, 620],
        ebitda: [120, 128, 132, 140, 148, 152, 160, 168],
        fcf: [80, 90, 95, 105, 115, 120, 130, 140],
      },
      optimista: {
        labels: ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"],
        ingresos: [490, 515, 540, 565, 590, 620, 645, 670],
        ebitda: [126, 134, 142, 152, 162, 170, 180, 190],
        fcf: [86, 98, 108, 120, 130, 142, 152, 165],
      },
      estres: {
        labels: ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"],
        ingresos: [470, 485, 495, 510, 525, 535, 550, 565],
        ebitda: [110, 118, 122, 126, 132, 136, 140, 145],
        fcf: [70, 78, 80, 85, 90, 96, 102, 110],
      },
    },
    capex_vs_inversion: {
      labels: ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"],
      capex: [30, 28, 32, 30, 31, 29, 28, 27],
      otros: [12, 14, 15, 12, 13, 13, 12, 12],
    },
    estructura_capital: { labels: ["Equity", "Deuda"], values: [65, 35] },
    supuestos: [
      "Crecimiento trimestral 5% en escenario base",
      "Capex estable desde T2",
      "Costo de deuda 8% fijo",
    ],
  };
}

function Inteligencia() {
  const [tab, setTab] = useState("liquidez");
  const [range, setRange] = useState("6m");
  const [scenario, setScenario] = useState("base");
  const { data, loading, error } = useTabData(tab, range, scenario);

  const charts = useMemo(() => buildCharts(tab, data, scenario), [tab, data, scenario]);

  return (
    <div className="int-page">
      <div className="page-header">
        <div>
          <h1>Inteligencia Financiera</h1>
          <div className="inline-meta">
            <span>Foco: liquidez, rentabilidad, eficiencia y proyecciones</span>
            <span>Rango: {range.toUpperCase()}</span>
          </div>
        </div>
        <div className="pill-group">
          <Pill label="6M" active={range === "6m"} onClick={() => setRange("6m")} />
          <Pill label="12M" active={range === "12m"} onClick={() => setRange("12m")} />
          <Pill label="24M" active={range === "24m"} onClick={() => setRange("24m")} />
        </div>
      </div>

      <div className="int-tabs">
        {Object.entries(TAB_LABELS).map(([key, label]) => (
          <button key={key} className={`int-tab ${tab === key ? "active" : ""}`} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "proyecciones" && (
        <div className="pill-group" style={{ marginTop: "-0.35rem" }}>
          {[
            { key: "base", label: "Base" },
            { key: "optimista", label: "Optimista" },
            { key: "estres", label: "Estresado" },
          ].map((s) => (
            <Pill key={s.key} label={s.label} active={scenario === s.key} onClick={() => setScenario(s.key)} />
          ))}
        </div>
      )}

      {loading && <div className="loading">Cargando inteligencia...</div>}
      {error && <div className="error">{error}</div>}

      {!loading && data && (
        <>
          {tab === "liquidez" && <LiquidezView data={data} charts={charts} />}
          {tab === "rentabilidad" && <RentabilidadView data={data} charts={charts} />}
          {tab === "eficiencia" && <EficienciaView data={data} charts={charts} />}
          {tab === "proyecciones" && <ProyeccionesView data={data} charts={charts} scenario={scenario} />}
        </>
      )}
    </div>
  );
}

function LiquidezView({ data, charts }) {
  const k = data.kpis || {};
  const d = k.deltas || {};
  return (
    <>
      <div className="kpi-grid">
        <KPIStat title="Caja disponible" value={currencyFmt.format(k.cash_on_hand || 0)} delta={d.cash_on_hand} badge=">= 2.5x nómina" />
        <KPIStat title="FCF 30d" value={currencyFmt.format(k.fcf_30d || 0)} delta={d.fcf_30d} />
        <KPIStat title="FCF 90d" value={currencyFmt.format(k.fcf_90d || 0)} delta={d.fcf_90d} />
        <KPIStat title="Burn mensual" value={currencyFmt.format(k.burn || 0)} delta={d.burn} />
        <KPIStat title="Runway" value={`${(k.runway_months || 0).toFixed(1)} m`} delta={d.runway_months} />
        <KPIStat title="CCC" value={`${k.ccc || 0} días`} delta={d.ccc} badge="< 55" />
        <KPIStat title="NWC/Ingresos" value={percentFmt(k.nwc_ratio || 0)} delta={d.nwc_ratio} badge="10-15%" />
      </div>

      <div className="charts-grid">
        <ChartCard title="Cash In/Out semanal" subtitle="Apilado">
          <Bar data={charts.cashStacked} options={barOptions("Cash", "USD", false, true)()} height={280} />
        </ChartCard>
        <ChartCard title="Balance de caja" subtitle="Serie 12M">
          <Line data={charts.cashBalance} options={lineOptions()} height={280} />
        </ChartCard>
      </div>

      <div className="charts-grid">
        <ChartCard title="Aging de cuentas por cobrar" subtitle="AR buckets">
          <Doughnut data={charts.agingAR} options={doughnutOptions()} height={260} />
        </ChartCard>
        <ChartCard title="Aging de cuentas por pagar" subtitle="AP buckets">
          <Doughnut data={charts.agingAP} options={doughnutOptions()} height={260} />
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
        <KPIStat title="Margen Bruto" value={percentFmt(k.gross_margin || 0)} delta={d.gross_margin} badge=">= 55%" />
        <KPIStat title="Margen EBITDA" value={percentFmt(k.ebitda_margin || 0)} delta={d.ebitda_margin} badge=">= 28%" />
        <KPIStat title="Margen Neto" value={percentFmt(k.net_margin || 0)} delta={d.net_margin} badge=">= 18%" />
        <KPIStat title="ROIC" value={percentFmt(k.roic || 0)} delta={d.roic} badge=">= 15%" />
        <KPIStat title="ROE" value={percentFmt(k.roe || 0)} delta={d.roe} />
        <KPIStat title="LTV/CAC" value={`x${(k.ltv_cac || 0).toFixed(1)}`} delta={d.ltv_cac} badge=">= 3.0" />
        <KPIStat title="ARPU" value={currencyFmt.format(k.arpu || 0)} delta={d.arpu} />
        <KPIStat title="Payback" value={`${(k.payback_months || 0).toFixed(1)} m`} delta={d.payback_months} />
      </div>

      <div className="charts-grid">
        <ChartCard title="Margen por unidad" subtitle="Bruto vs Neto">
          <Bar data={charts.margenUnidades} options={barOptions("Margen", "%", true)()} height={280} />
        </ChartCard>
        <ChartCard title="Mix de costos" subtitle="OPEX / CAPEX / otros">
          <Doughnut data={charts.mixCostos} options={doughnutOptions()} height={280} />
        </ChartCard>
      </div>

      <div className="charts-grid">
        <ChartCard title="Serie de márgenes" subtitle="18M">
          <Line data={charts.margenSerie} options={lineOptions(true)} height={280} />
        </ChartCard>
        <div className="table-card">
          <div className="chart-card-head">
            <h4 className="section-title">Top clientes por margen</h4>
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
        <KPIStat title="DSO" value={`${k.dso || 0} días`} delta={d.dso} badge="< 55" />
        <KPIStat title="DPO" value={`${k.dpo || 0} días`} delta={d.dpo} badge="> 40" />
        <KPIStat title="DIO" value={`${k.dio || 0} días`} delta={d.dio} badge="< 45" />
        <KPIStat title="CCC" value={`${k.ccc || 0} días`} delta={d.ccc} badge="< 55" />
        <KPIStat title="NWC/Ingresos" value={percentFmt(k.nwc_ratio || 0)} delta={d.nwc_ratio} />
        <KPIStat title="Cobranzas vencidas" value={percentFmt(k.overdue_ratio || 0)} delta={d.overdue_ratio} />
      </div>

      <div className="charts-grid">
        <ChartCard title="DSO / DPO / DIO" subtitle="Tendencia 6M">
          <Line data={charts.eficiencia} options={lineOptions()} height={280} />
        </ChartCard>
        <ChartCard title="Aging AR" subtitle="Cuentas por cobrar">
          <Doughnut data={charts.agingAR} options={doughnutOptions()} height={260} />
        </ChartCard>
      </div>

      <div className="charts-grid">
        <ChartCard title="Aging AP" subtitle="Cuentas por pagar">
          <Doughnut data={charts.agingAP} options={doughnutOptions()} height={260} />
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

function ProyeccionesView({ data, charts, scenario }) {
  const k = data.kpis || {};
  const d = k.deltas || {};
  return (
    <>
      <div className="kpi-grid">
        <KPIStat title="FCF proyectado" value={currencyFmt.format(k.fcf_proj || 0)} delta={d.fcf_proj} />
        <KPIStat title="Deuda / EBITDA" value={`${(k.debt_ebitda || 0).toFixed(1)}x`} delta={d.debt_ebitda} badge="< 3.0x" />
        <KPIStat title="Cobertura intereses" value={`${(k.interest_coverage || 0).toFixed(1)}x`} delta={d.interest_coverage} badge="> 4.0x" />
      </div>

      <div className="charts-grid">
        <ChartCard title={`Escenario ${scenario}`} subtitle="Ingresos / EBITDA / FCF 24M">
          <Line data={charts.escenario} options={lineOptions()} height={280} />
        </ChartCard>
        <ChartCard title="Estructura de capital" subtitle="Equity vs Deuda">
          <Doughnut data={charts.estructuraCapital} options={doughnutOptions()} height={260} />
        </ChartCard>
      </div>

      <div className="charts-grid">
        <ChartCard title="CAPEX vs Inversión" subtitle="Serie 24M">
          <Bar data={charts.capexVsInversion} options={barOptions("USD", "USD", false, true)()} height={280} />
        </ChartCard>
        <div className="table-card">
          <h4 className="section-title" style={{ marginBottom: "0.75rem" }}>Supuestos clave</h4>
          <ul className="bullet-list">
            {(data.supuestos || []).map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}

function buildCharts(tab, data, scenario) {
  if (!data) return {};

  if (tab === "liquidez") {
    return {
      cashStacked: {
        labels: data.cash_weekly?.labels || [],
        datasets: [
          { label: "Cash In", data: data.cash_weekly?.cash_in || [], backgroundColor: "#0f766e" },
          { label: "Cash Out", data: data.cash_weekly?.cash_out || [], backgroundColor: "#f97316" },
        ],
      },
      cashBalance: {
        labels: data.cash_weekly?.labels || [],
        datasets: [
          {
            label: "Balance",
            data: data.cash_weekly?.balance || [],
            borderColor: "#2563eb",
            backgroundColor: "rgba(37, 99, 235, 0.12)",
            tension: 0.35,
            fill: true,
          },
        ],
      },
      agingAR: {
        labels: data.aging_ar?.labels || [],
        datasets: [{ data: data.aging_ar?.values || [], backgroundColor: ["#2563eb", "#16a34a", "#f59e0b", "#ef4444"] }],
      },
      agingAP: {
        labels: data.aging_ap?.labels || [],
        datasets: [{ data: data.aging_ap?.values || [], backgroundColor: ["#2563eb", "#16a34a", "#f59e0b", "#ef4444"] }],
      },
    };
  }

  if (tab === "rentabilidad") {
    return {
      margenUnidades: {
        labels: data.margen_unidades?.labels || [],
        datasets: [
          { label: "Bruto %", data: data.margen_unidades?.bruto || [], backgroundColor: "rgba(37, 99, 235, 0.8)", borderRadius: 8 },
          { label: "Neto %", data: data.margen_unidades?.neto || [], backgroundColor: "rgba(22, 163, 74, 0.8)", borderRadius: 8 },
        ],
      },
      mixCostos: {
        labels: data.mix_costos?.labels || [],
        datasets: [{ data: data.mix_costos?.valores || [], backgroundColor: ["#0f766e", "#2563eb", "#f59e0b", "#16a34a", "#a855f7"] }],
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

  if (tab === "eficiencia") {
    return {
      eficiencia: {
        labels: data.eficiencia?.labels || [],
        datasets: [
          { label: "DSO", data: data.eficiencia?.dso || [], borderColor: "#2563eb", backgroundColor: "rgba(37, 99, 235, 0.12)", tension: 0.35, fill: false },
          { label: "DPO", data: data.eficiencia?.dpo || [], borderColor: "#16a34a", backgroundColor: "rgba(22, 163, 74, 0.12)", tension: 0.35, fill: false },
          { label: "DIO", data: data.eficiencia?.dio || [], borderColor: "#f59e0b", backgroundColor: "rgba(245, 158, 11, 0.12)", tension: 0.35, fill: false },
        ],
      },
      agingAR: {
        labels: data.aging_ar?.labels || [],
        datasets: [{ data: data.aging_ar?.values || [], backgroundColor: ["#2563eb", "#16a34a", "#f59e0b", "#ef4444"] }],
      },
      agingAP: {
        labels: data.aging_ap?.labels || [],
        datasets: [{ data: data.aging_ap?.values || [], backgroundColor: ["#2563eb", "#16a34a", "#f59e0b", "#ef4444"] }],
      },
    };
  }

  const scenarioData = data.escenarios?.[scenario] || { labels: [], ingresos: [], ebitda: [], fcf: [] };
  return {
    escenario: {
      labels: scenarioData.labels,
      datasets: [
        { label: "Ingresos", data: scenarioData.ingresos, borderColor: "#2563eb", backgroundColor: "rgba(37, 99, 235, 0.12)", tension: 0.35, fill: true },
        { label: "EBITDA", data: scenarioData.ebitda, borderColor: "#16a34a", backgroundColor: "rgba(22, 163, 74, 0.12)", tension: 0.35, fill: true },
        { label: "FCF", data: scenarioData.fcf, borderColor: "#f59e0b", backgroundColor: "rgba(245, 158, 11, 0.12)", tension: 0.35, fill: true },
      ],
    },
    estructuraCapital: {
      labels: data.estructura_capital?.labels || [],
      datasets: [{ data: data.estructura_capital?.values || [], backgroundColor: ["#0f766e", "#2563eb"] }],
    },
    capexVsInversion: {
      labels: data.capex_vs_inversion?.labels || [],
      datasets: [
        { label: "CAPEX", data: data.capex_vs_inversion?.capex || [], backgroundColor: "#2563eb", borderRadius: 8 },
        { label: "Otros", data: data.capex_vs_inversion?.otros || [], backgroundColor: "#0f766e", borderRadius: 8 },
      ],
    },
  };
}

function barOptions(label = "Valor", unit = "", isPercent = false, stacked = false) {
  return () => ({
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { stacked, grid: { display: false } },
      y: {
        stacked,
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
