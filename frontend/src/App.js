import { useEffect, useState, useCallback } from "react";

const API = "http://localhost:8000";

const sevColor = (s) => ({ P0: "#ff4d4f", P1: "#fa8c16", P2: "#fadb14" }[s] || "#8892a4");
const statusColor = (s) => ({ OPEN: "#ff4d4f", INVESTIGATING: "#fa8c16", RESOLVED: "#1677ff", CLOSED: "#52c41a" }[s] || "#8892a4");
const fmt = (ts) => ts ? new Date(ts * 1000).toLocaleString() : "—";
const fmtMttr = (s) => s == null ? "—" : s < 60 ? `${s.toFixed(0)}s` : `${(s/60).toFixed(1)} min`;

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, opts);
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

const RCA_CATEGORIES = ["Infrastructure Failure","Code Defect","Third-party Service","Human Error / Misconfiguration","Capacity / Scaling Issue","Security Incident","Unknown"];

function RcaModal({ incident, onClose, onSuccess }) {
  const now = new Date();
  const startDefault = incident.start_time ? new Date(incident.start_time * 1000).toISOString().slice(0,16) : now.toISOString().slice(0,16);
  const [form, setForm] = useState({ start_time: startDefault, end_time: now.toISOString().slice(0,16), root_cause_category: "", fix_applied: "", prevention_steps: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async () => {
    if (!form.root_cause_category) { setError("Please select a root cause category."); return; }
    if (!form.fix_applied.trim()) { setError("Fix Applied is required."); return; }
    if (!form.prevention_steps.trim()) { setError("Prevention Steps is required."); return; }
    setLoading(true); setError("");
    try { const result = await api(`/rca/${incident.id}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) }); onSuccess(result); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.modal} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalHeader}>
          <span style={{ fontWeight: 600, fontSize: 16 }}>📋 RCA — Incident #{incident.id}</span>
          <button onClick={onClose} style={{ background: "none", color: "#8892a4", padding: 4 }}>✕</button>
        </div>
        <div style={S.modalBody}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <label style={S.label}>Incident Start *<input type="datetime-local" value={form.start_time} onChange={set("start_time")} /></label>
            <label style={S.label}>Incident End *<input type="datetime-local" value={form.end_time} onChange={set("end_time")} /></label>
          </div>
          <label style={S.label}>Root Cause Category *
            <select value={form.root_cause_category} onChange={set("root_cause_category")}>
              <option value="">— Select category —</option>
              {RCA_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label style={S.label}>Fix Applied *<textarea placeholder="What was done to fix this incident…" value={form.fix_applied} onChange={set("fix_applied")} rows={3} /></label>
          <label style={S.label}>Prevention Steps *<textarea placeholder="How to prevent this from happening again?" value={form.prevention_steps} onChange={set("prevention_steps")} rows={3} /></label>
          {error && <div style={S.errBox}>⚠️ {error}</div>}
          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <button onClick={onClose} style={{ background: "#2e3354", color: "#e2e8f0" }}>Cancel</button>
            <button onClick={handleSubmit} disabled={loading} style={{ background: "#52c41a", color: "#fff" }}>{loading ? "Closing…" : "✅ Submit & Close"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SignalsModal({ incident, onClose }) {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { api(`/signals/${incident.id}`).then(setSignals).finally(() => setLoading(false)); }, [incident.id]);
  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={{ ...S.modal, maxWidth: 680 }} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalHeader}>
          <span style={{ fontWeight: 600 }}>📡 Raw Signals — Incident #{incident.id}</span>
          <button onClick={onClose} style={{ background: "none", color: "#8892a4", padding: 4 }}>✕</button>
        </div>
        <div style={{ maxHeight: 480, overflowY: "auto", padding: "12px 20px" }}>
          {loading && <p style={{ color: "#8892a4" }}>Loading…</p>}
          {!loading && signals.length === 0 && <p style={{ color: "#8892a4" }}>No signals yet.</p>}
          {signals.map((sig, i) => (
            <div key={i} style={{ display: "flex", gap: 12, padding: "6px 0", borderBottom: "1px solid #2e3354", fontSize: 13 }}>
              <span style={{ color: sevColor(sig.severity), fontWeight: 600, minWidth: 32 }}>{sig.severity}</span>
              <span style={{ color: "#8892a4", fontSize: 12 }}>{new Date(sig.ingested_at * 1000).toLocaleTimeString()}</span>
              <span style={{ flex: 1 }}>{sig.payload?.message || "—"}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function IncidentCard({ incident, onRefresh }) {
  const [showRca, setShowRca] = useState(false);
  const [showSignals, setShowSignals] = useState(false);
  const [toast, setToast] = useState("");

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(""), 3000); };

  const transition = async (status) => {
    try { await api(`/transition/${incident.id}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }); onRefresh(); }
    catch (e) { showToast(`Error: ${e.message}`); }
  };

  const rca = incident.rca ? (typeof incident.rca === "string" ? JSON.parse(incident.rca) : incident.rca) : null;

  return (
    <>
      <div style={S.card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <span style={{ ...S.badge, background: sevColor(incident.severity), color: "#000" }}>{incident.severity}</span>
            <span style={{ ...S.badge, background: statusColor(incident.status), color: "#fff", marginLeft: 6 }}>{incident.status}</span>
          </div>
          <span style={{ color: "#8892a4", fontSize: 12 }}>#{incident.id}</span>
        </div>
        <div style={{ marginTop: 10, fontWeight: 600, fontSize: 15 }}>{incident.component_id}</div>
        <div style={{ color: "#8892a4", fontSize: 12, marginTop: 2 }}>Started: {fmt(incident.start_time)}</div>
        {incident.status === "CLOSED" && <div style={{ marginTop: 6, fontSize: 12, color: "#52c41a" }}>MTTR: {fmtMttr(incident.mttr_seconds)}</div>}
        {rca && (
          <div style={{ marginTop: 10, background: "#1a1d27", borderRadius: 6, padding: "8px 10px", fontSize: 12, borderLeft: "3px solid #52c41a" }}>
            <div style={{ fontWeight: 500 }}>RCA: {rca.root_cause_category}</div>
            <div style={{ color: "#8892a4", marginTop: 2 }}>{rca.fix_applied?.slice(0,80)}…</div>
          </div>
        )}
        {toast && <div style={{ marginTop: 8, background: "#2e3354", borderRadius: 6, padding: "6px 10px", fontSize: 12, color: "#52c41a" }}>{toast}</div>}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
          <button onClick={() => setShowSignals(true)} style={{ background: "#2e3354", color: "#e2e8f0" }}>📡 Signals</button>
          {incident.status === "OPEN" && <button onClick={() => transition("INVESTIGATING")} style={{ background: "#fa8c16", color: "#fff" }}>🔍 Investigate</button>}
          {incident.status === "INVESTIGATING" && <button onClick={() => transition("RESOLVED")} style={{ background: "#1677ff", color: "#fff" }}>✅ Resolve</button>}
          {incident.status === "RESOLVED" && <button onClick={() => setShowRca(true)} style={{ background: "#52c41a", color: "#fff" }}>📋 Submit RCA & Close</button>}
        </div>
      </div>
      {showRca && <RcaModal incident={incident} onClose={() => setShowRca(false)} onSuccess={(r) => { setShowRca(false); showToast(`✅ Closed! MTTR: ${fmtMttr(r.mttr_seconds)}`); onRefresh(); }} />}
      {showSignals && <SignalsModal incident={incident} onClose={() => setShowSignals(false)} />}
    </>
  );
}

export default function App() {
  const [incidents, setIncidents] = useState([]);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [health, setHealth] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState("");

  const fetchIncidents = useCallback(async () => {
    try { const data = await api("/incidents"); setIncidents(data); setLastUpdated(new Date().toLocaleTimeString()); setError(""); }
    catch { setError("Cannot reach backend. Is Docker running?"); }
  }, []);

  const fetchHealth = useCallback(async () => {
    try { setHealth(await api("/health")); } catch { setHealth(null); }
  }, []);

  useEffect(() => {
    fetchIncidents(); fetchHealth();
    const t1 = setInterval(fetchIncidents, 3000);
    const t2 = setInterval(fetchHealth, 5000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [fetchIncidents, fetchHealth]);

  const filtered = incidents.filter((i) => {
    const mf = filter === "ALL" || i.status === filter || i.severity === filter;
    const ms = i.component_id.toLowerCase().includes(search.toLowerCase());
    return mf && ms;
  });

  return (
    <div style={{ minHeight: "100vh", background: "#0f1117" }}>
      <div style={{ background: "#1a1d27", borderBottom: "1px solid #2e3354", padding: "14px 24px", display: "flex", justifyContent: "space-between", alignItems: "center", position: "sticky", top: 0, zIndex: 100 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700 }}>🚨 Incident Management System</h1>
          <div style={{ fontSize: 12, color: "#8892a4" }}>Last updated: {lastUpdated || "—"}{health && <span style={{ marginLeft: 12 }}>· Queue: {health.queue_depth}</span>}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: health ? "#52c41a" : "#ff4d4f" }} />
          <span style={{ fontSize: 12, color: "#8892a4" }}>{health ? "Backend healthy" : "Backend unreachable"}</span>
        </div>
      </div>
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 20px" }}>
        {error && <div style={{ background: "#3a1a1a", border: "1px solid #ff4d4f", borderRadius: 8, padding: "10px 14px", color: "#ff4d4f", marginBottom: 16 }}>{error}</div>}
        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
          {[{ label: "Total", value: incidents.length, color: "#e2e8f0" }, { label: "Open", value: incidents.filter(i => i.status==="OPEN").length, color: "#ff4d4f" }, { label: "P0", value: incidents.filter(i => i.severity==="P0").length, color: "#ff4d4f" }, { label: "Closed", value: incidents.filter(i => i.status==="CLOSED").length, color: "#52c41a" }].map(({ label, value, color }) => (
            <div key={label} style={{ background: "#1a1d27", border: "1px solid #2e3354", borderRadius: 8, padding: "12px 20px", minWidth: 90, textAlign: "center" }}>
              <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
              <div style={{ color: "#8892a4", fontSize: 12 }}>{label}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          <input placeholder="Search component…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ maxWidth: 220 }} />
          {["ALL","OPEN","INVESTIGATING","RESOLVED","CLOSED","P0","P1","P2"].map((f) => (
            <button key={f} onClick={() => setFilter(f)} style={{ background: filter===f ? "#6366f1" : "#2e3354", color: "#e2e8f0", padding: "5px 12px" }}>{f}</button>
          ))}
        </div>
        {filtered.length === 0
          ? <div style={{ textAlign: "center", color: "#8892a4", marginTop: 60 }}>{incidents.length === 0 ? "No incidents yet. Run: python simulate.py" : "No incidents match filter."}</div>
          : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 16 }}>
              {filtered.map((inc) => <IncidentCard key={inc.id} incident={inc} onRefresh={fetchIncidents} />)}
            </div>
        }
      </div>
    </div>
  );
}

const S = {
  overlay: { position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 999, padding: 16 },
  modal: { background: "#21253a", border: "1px solid #2e3354", borderRadius: 12, width: "100%", maxWidth: 560, maxHeight: "90vh", overflowY: "auto" },
  modalHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 20px", borderBottom: "1px solid #2e3354" },
  modalBody: { padding: 20, display: "flex", flexDirection: "column", gap: 14 },
  label: { display: "flex", flexDirection: "column", gap: 5, fontSize: 13, color: "#8892a4" },
  errBox: { background: "#3a1a1a", border: "1px solid #ff4d4f", borderRadius: 6, padding: "8px 12px", color: "#ff4d4f", fontSize: 13 },
  card: { background: "#21253a", border: "1px solid #2e3354", borderRadius: 10, padding: 16 },
  badge: { display: "inline-block", borderRadius: 4, padding: "2px 8px", fontSize: 11, fontWeight: 700 },
};
