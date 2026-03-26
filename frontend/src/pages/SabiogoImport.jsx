// frontend/src/pages/SabiogoImport.jsx
import React, { useState, useRef } from "react";

const SABIOGO_BASE = import.meta.env.VITE_SABIOGO_BASE_URL || "/sabiogo";

const ARCHIVOS_CONFIG = [
  {
    key: "carnes_ventas",
    label: "Ventas – Carnes",
    desc: "carnes_ventas_globales.xls",
    color: "#ef4444",
    icon: "🥩",
  },
  {
    key: "lacteos_ventas",
    label: "Ventas – Lácteos",
    desc: "lacteos_ventas_globales.xls",
    color: "#3b82f6",
    icon: "🥛",
  },
  {
    key: "carnes_compras",
    label: "Compras – Carnes",
    desc: "carnes_compras_globales.xls",
    color: "#f97316",
    icon: "📦",
  },
  {
    key: "lacteos_compras",
    label: "Compras – Lácteos",
    desc: "lacteos_compras_globales.xls",
    color: "#8b5cf6",
    icon: "📦",
  },
];

function FileDropZone({ config, file, onSelect, disabled }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) onSelect(config.key, f);
  };

  const style = {
    border: `2px dashed ${dragging ? config.color : file ? config.color : "#d1d5db"}`,
    borderRadius: 12,
    padding: "1.25rem 1rem",
    textAlign: "center",
    cursor: disabled ? "not-allowed" : "pointer",
    background: file ? `${config.color}10` : dragging ? `${config.color}08` : "#fafafa",
    transition: "all 0.2s",
    opacity: disabled ? 0.6 : 1,
  };

  return (
    <div
      style={style}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={disabled ? undefined : handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".xls,.xlsx"
        style={{ display: "none" }}
        onChange={(e) => e.target.files[0] && onSelect(config.key, e.target.files[0])}
        disabled={disabled}
      />
      <div style={{ fontSize: 28, marginBottom: 6 }}>{config.icon}</div>
      <div style={{ fontWeight: 600, color: config.color, fontSize: "0.95rem" }}>
        {config.label}
      </div>
      {file ? (
        <div style={{ fontSize: "0.8rem", color: "#374151", marginTop: 4 }}>
          ✓ <strong>{file.name}</strong>{" "}
          <span style={{ color: "#6b7280" }}>({(file.size / 1024 / 1024).toFixed(1)} MB)</span>
        </div>
      ) : (
        <div style={{ fontSize: "0.8rem", color: "#9ca3af", marginTop: 4 }}>
          Arrastrá o hacé click · {config.desc}
        </div>
      )}
    </div>
  );
}

function ResultRow({ label, stats, error, color }) {
  if (error) {
    return (
      <div style={{ padding: "0.5rem 0.75rem", background: "#fef2f2", borderRadius: 8, marginBottom: 8, border: "1px solid #fecaca" }}>
        <strong style={{ color }}>{label}</strong>{" "}
        <span style={{ color: "#dc2626", fontSize: "0.85rem" }}>✗ {error}</span>
      </div>
    );
  }
  if (!stats) return null;
  return (
    <div style={{ padding: "0.5rem 0.75rem", background: "#f0fdf4", borderRadius: 8, marginBottom: 8, border: "1px solid #bbf7d0" }}>
      <strong style={{ color }}>{label}</strong>
      <span style={{ marginLeft: 8, fontSize: "0.85rem", color: "#374151" }}>
        ✓ Insertadas: <b>{stats.filas_insertadas?.toLocaleString()}</b>
        &nbsp;| Procesadas: <b>{stats.filas_procesadas?.toLocaleString()}</b>
        &nbsp;| Duplicadas: <b>{stats.filas_duplicadas}</b>
        &nbsp;| Errores: <b>{stats.filas_error}</b>
      </span>
    </div>
  );
}

export default function SabiogoImport() {
  const [files, setFiles] = useState({});
  const [replace, setReplace] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [globalError, setGlobalError] = useState("");

  const handleSelect = (key, file) => {
    setFiles((prev) => ({ ...prev, [key]: file }));
  };

  const handleRemove = (key) => {
    setFiles((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const totalFiles = Object.keys(files).length;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (totalFiles === 0) {
      setGlobalError("Seleccioná al menos un archivo.");
      return;
    }
    setGlobalError("");
    setResult(null);
    setLoading(true);

    const formData = new FormData();
    formData.append("replace", replace ? "true" : "false");
    for (const [key, file] of Object.entries(files)) {
      formData.append(key, file);
    }

    try {
      const resp = await fetch(`${SABIOGO_BASE}/api/cargar-globales`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      const data = await resp.json();
      if (!resp.ok && resp.status !== 207) {
        throw new Error(data.error || `HTTP ${resp.status}`);
      }
      setResult(data);
    } catch (err) {
      setGlobalError(err.message || "Error desconocido");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setFiles({});
    setResult(null);
    setGlobalError("");
  };

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: "1.5rem 1rem" }}>
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: 4 }}>
          Importar datos SabioGo
        </h1>
        <p style={{ color: "#6b7280", fontSize: "0.9rem" }}>
          Cargá hasta 4 archivos simultáneamente. Acepta <code>.xls</code> y <code>.xlsx</code>.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        {/* Grid de archivos */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
            gap: "1rem",
            marginBottom: "1.25rem",
          }}
        >
          {ARCHIVOS_CONFIG.map((cfg) => (
            <div key={cfg.key}>
              <FileDropZone
                config={cfg}
                file={files[cfg.key]}
                onSelect={handleSelect}
                disabled={loading}
              />
              {files[cfg.key] && (
                <button
                  type="button"
                  onClick={() => handleRemove(cfg.key)}
                  disabled={loading}
                  style={{
                    marginTop: 4, fontSize: "0.75rem", color: "#6b7280",
                    background: "none", border: "none", cursor: "pointer", padding: "0 2px",
                  }}
                >
                  ✕ quitar
                </button>
              )}
            </div>
          ))}
        </div>

        {/* Opción reemplazo */}
        <div
          style={{
            background: replace ? "#fff7ed" : "#f9fafb",
            border: `1px solid ${replace ? "#fed7aa" : "#e5e7eb"}`,
            borderRadius: 10,
            padding: "0.75rem 1rem",
            marginBottom: "1.25rem",
            display: "flex",
            alignItems: "flex-start",
            gap: "0.75rem",
          }}
        >
          <input
            type="checkbox"
            id="replace-check"
            checked={replace}
            onChange={(e) => setReplace(e.target.checked)}
            disabled={loading}
            style={{ marginTop: 3, width: 16, height: 16, cursor: "pointer" }}
          />
          <label htmlFor="replace-check" style={{ cursor: "pointer", flex: 1 }}>
            <strong>Reemplazar datos existentes del origen</strong>
            <div style={{ fontSize: "0.8rem", color: replace ? "#c2410c" : "#6b7280", marginTop: 2 }}>
              {replace
                ? "⚠ Se eliminarán todos los registros del origen correspondiente antes de importar."
                : "Los datos nuevos se añadirán a los existentes (modo append)."}
            </div>
          </label>
        </div>

        {/* Botón */}
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <button
            type="submit"
            disabled={loading || totalFiles === 0}
            style={{
              background: totalFiles > 0 && !loading ? "#2563eb" : "#93c5fd",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "0.6rem 1.5rem",
              fontWeight: 600,
              fontSize: "0.95rem",
              cursor: totalFiles > 0 && !loading ? "pointer" : "not-allowed",
              transition: "background 0.2s",
            }}
          >
            {loading
              ? "Importando…"
              : `Importar ${totalFiles > 0 ? `(${totalFiles} archivo${totalFiles > 1 ? "s" : ""})` : ""}`}
          </button>
          {(totalFiles > 0 || result) && (
            <button
              type="button"
              onClick={handleReset}
              disabled={loading}
              style={{
                background: "none", border: "1px solid #d1d5db",
                borderRadius: 8, padding: "0.6rem 1rem",
                color: "#374151", cursor: "pointer", fontSize: "0.9rem",
              }}
            >
              Limpiar
            </button>
          )}
        </div>
      </form>

      {/* Error global */}
      {globalError && (
        <div
          style={{
            marginTop: "1rem", background: "#fef2f2", border: "1px solid #fecaca",
            borderRadius: 8, padding: "0.75rem 1rem", color: "#dc2626",
          }}
        >
          ✗ {globalError}
        </div>
      )}

      {/* Resultados */}
      {result && (
        <div style={{ marginTop: "1.5rem" }}>
          <div
            style={{
              background: result.success ? "#f0fdf4" : "#fffbeb",
              border: `1px solid ${result.success ? "#86efac" : "#fde68a"}`,
              borderRadius: 10,
              padding: "1rem 1.25rem",
              marginBottom: "1rem",
            }}
          >
            <strong style={{ fontSize: "1rem" }}>
              {result.success ? "✓ Importación completada" : "⚠ Importación con errores parciales"}
            </strong>
            <div style={{ fontSize: "0.85rem", color: "#374151", marginTop: 4 }}>
              Total filas insertadas:{" "}
              <strong>{result.total_filas_insertadas?.toLocaleString()}</strong>
              {result.replace && (
                <span style={{ marginLeft: 8, color: "#c2410c" }}>
                  · modo reemplazo activado
                </span>
              )}
            </div>
          </div>

          {ARCHIVOS_CONFIG.map((cfg) => (
            <ResultRow
              key={cfg.key}
              label={cfg.label}
              stats={result.archivos?.[cfg.key]}
              error={result.errores?.[cfg.key]}
              color={cfg.color}
            />
          ))}

          {result.objetivos_sync && (
            <details style={{ marginTop: "0.75rem" }}>
              <summary style={{ cursor: "pointer", fontSize: "0.85rem", color: "#6b7280" }}>
                Sincronización de objetivos PRE ({result.objetivos_sync.ejecuciones?.length} períodos)
              </summary>
              <pre
                style={{
                  fontSize: "0.75rem", background: "#f9fafb",
                  border: "1px solid #e5e7eb", borderRadius: 8,
                  padding: "0.75rem", marginTop: 6, overflowX: "auto",
                }}
              >
                {JSON.stringify(result.objetivos_sync, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
