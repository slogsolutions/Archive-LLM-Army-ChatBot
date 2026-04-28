'use client';

import { useEffect, useState, useCallback } from 'react';
import AppLayout from '../components/AppLayout';
import { api } from '../lib/api';

// ── helpers ───────────────────────────────────────────────────────────────────

function confBadge(score) {
  if (score === null || score === undefined) return 'badge-info';
  if (score >= 0.55) return 'badge-success';
  if (score >= 0.35) return 'badge-warning';
  return 'badge-danger';
}

function confLabel(score) {
  if (score === null || score === undefined) return '—';
  if (score >= 0.55) return `${(score * 100).toFixed(0)}% ✓`;
  if (score >= 0.35) return `${(score * 100).toFixed(0)}% ⚠`;
  return `${(score * 100).toFixed(0)}% ✗`;
}

function latColor(s) {
  if (!s) return 'text-muted';
  if (s < 60)  return 'text-success';
  if (s < 180) return 'text-warning';
  return 'text-danger';
}

const STATUS_BADGE = {
  ok:         'badge-success',
  rejected:   'badge-danger',
  not_found:  'badge-warning',
  error:      'badge-danger',
  ollama_down:'badge-danger',
};

// ── Summary cards ─────────────────────────────────────────────────────────────

function SummaryCard({ label, value, sub, color }) {
  return (
    <div className={`stat-card ${color || 'primary'}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value ?? '—'}</div>
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function LogsDashboard() {
  const [tab,       setTab]       = useState('rag');
  const [logs,      setLogs]      = useState([]);
  const [summary,   setSummary]   = useState(null);
  const [cache,     setCache]     = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState('');

  // Filter state
  const [status,  setStatus]  = useState('');
  const [intent,  setIntent]  = useState('');
  const [days,    setDays]    = useState(7);
  const [page,    setPage]    = useState(1);
  const [total,   setTotal]   = useState(0);

  const PER_PAGE = 50;

  const loadSummary = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([
        api.request('/logs/rag/summary'),
        api.request('/logs/embedding-cache'),
      ]);
      setSummary(s);
      setCache(c);
    } catch (e) {
      console.warn('Summary load failed:', e.message);
    }
  }, []);

  const loadRagLogs = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params = new URLSearchParams({ page, per_page: PER_PAGE, days });
      if (status) params.set('status', status);
      if (intent) params.set('intent', intent);
      const data = await api.request(`/logs/rag?${params}`);
      setLogs(data.items || []);
      setTotal(data.total || 0);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [page, days, status, intent]);

  const loadAuditLogs = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const data = await api.request(`/logs/audit?days=${days}&page=${page}&per_page=${PER_PAGE}`);
      setAuditLogs(data.items || []);
      setTotal(data.total || 0);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [page, days]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    setPage(1);
  }, [tab, status, intent, days]);

  useEffect(() => {
    if (tab === 'rag')   loadRagLogs();
    if (tab === 'audit') loadAuditLogs();
  }, [tab, loadRagLogs, loadAuditLogs]);

  const s24 = summary?.last_24h || {};
  const s7  = summary?.last_7d  || {};

  return (
    <AppLayout
      title="Monitoring & Logs"
      subtitle="RAG pipeline traces, confidence metrics, and audit trail."
    >
      {error && <div className="form-error mb-4">{error}</div>}

      {/* ── Summary row ── */}
      {summary && (
        <div className="stats-grid mb-6">
          <SummaryCard label="Queries (24h)"   value={s24.total}              color="primary" />
          <SummaryCard label="Rejected (24h)"  value={s24.rejected}           color="danger"
            sub={s24.total ? `${((s24.rejected||0)/s24.total*100).toFixed(0)}% of queries` : null} />
          <SummaryCard label="Avg Confidence (7d)"
            value={s7.avg_confidence != null ? `${(s7.avg_confidence*100).toFixed(0)}%` : '—'}
            color="success" />
          <SummaryCard label="Avg Latency (7d)"
            value={s7.avg_latency_s != null ? `${s7.avg_latency_s}s` : '—'}
            color={s7.avg_latency_s > 120 ? 'danger' : 'warning'} />
          {cache?.status === 'ok' && (
            <SummaryCard label="Embedding Cache"
              value={`${cache.cached_embeddings} hits`}
              sub={`${cache.used_memory_mb} MB`}
              color="info" />
          )}
        </div>
      )}

      {/* ── Intent breakdown (7d) ── */}
      {summary && s7.intents && (
        <div className="card mb-6 animated-panel" style={{ padding: '12px 16px' }}>
          <h3 className="section-title" style={{ marginBottom: 8 }}>Query Intents (last 7 days)</h3>
          <div className="flex flex-wrap gap-3">
            {Object.entries(s7.intents).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="badge badge-admin">{k}</span>
                <span className="text-sm font-semibold">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Tabs ── */}
      <div className="flex gap-2 mb-4 flex-wrap items-center">
        {['rag', 'audit'].map((t) => (
          <button key={t} type="button"
            className={`btn btn-sm ${tab === t ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setTab(t)}>
            {t === 'rag' ? 'RAG Query Logs' : 'Audit Trail'}
          </button>
        ))}

        {/* Filters */}
        <div className="flex gap-2 ml-auto flex-wrap">
          <select className="form-select" style={{ width: 120, padding: '4px 8px', fontSize: 13 }}
            value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[1, 7, 30, 90].map(d => <option key={d} value={d}>Last {d}d</option>)}
          </select>
          {tab === 'rag' && (
            <>
              <select className="form-select" style={{ width: 120, padding: '4px 8px', fontSize: 13 }}
                value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">All status</option>
                <option value="ok">OK</option>
                <option value="rejected">Rejected</option>
                <option value="not_found">Not found</option>
                <option value="error">Error</option>
              </select>
              <select className="form-select" style={{ width: 120, padding: '4px 8px', fontSize: 13 }}
                value={intent} onChange={(e) => setIntent(e.target.value)}>
                <option value="">All intents</option>
                <option value="prose">Prose</option>
                <option value="list">List</option>
                <option value="command">Command</option>
                <option value="mixed">Mixed</option>
              </select>
            </>
          )}
        </div>
      </div>

      {/* ── RAG Logs table ── */}
      {tab === 'rag' && (
        <div className="table-wrapper animated-panel">
          <table className="table">
            <thead>
              <tr>
                <th>Query</th>
                <th>Intent</th>
                <th>Status</th>
                <th>Confidence</th>
                <th>Retrieval</th>
                <th>Latency</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="text-center text-muted">Loading…</td></tr>
              ) : logs.length === 0 ? (
                <tr><td colSpan={7} className="text-center text-muted">No logs for this period.</td></tr>
              ) : logs.map((r) => (
                <tr key={r.id} title={r.answer_preview || ''}>
                  <td>
                    <div className="text-sm truncate max-w-xs" style={{ maxWidth: 280 }}>
                      {r.query}
                    </div>
                    {r.answer_preview && (
                      <div className="text-xs text-muted truncate" style={{ maxWidth: 280 }}>
                        {r.answer_preview.slice(0, 80)}…
                      </div>
                    )}
                  </td>
                  <td><span className="badge badge-info">{r.intent || '—'}</span></td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[r.status] || 'badge-info'}`}>
                      {r.status}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${confBadge(r.confidence)}`}>
                      {confLabel(r.confidence)}
                    </span>
                  </td>
                  <td className="text-sm">
                    <div>{r.retrieval_count} chunks</div>
                    <div className="text-xs text-muted">{r.unique_sources} docs</div>
                  </td>
                  <td className={`text-sm font-mono ${latColor(r.latency_s)}`}>
                    {r.latency_s != null ? `${r.latency_s}s` : '—'}
                  </td>
                  <td className="text-xs text-muted">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          {total > PER_PAGE && (
            <div className="flex items-center gap-3 px-4 py-3 border-t border-border">
              <button className="btn btn-secondary btn-sm"
                disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
              <span className="text-sm text-muted">
                Page {page} of {Math.ceil(total / PER_PAGE)} ({total} total)
              </span>
              <button className="btn btn-secondary btn-sm"
                disabled={page >= Math.ceil(total / PER_PAGE)} onClick={() => setPage(p => p + 1)}>
                Next →
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Audit Logs table ── */}
      {tab === 'audit' && (
        <div className="table-wrapper animated-panel">
          <table className="table">
            <thead>
              <tr>
                <th>Action</th>
                <th>User</th>
                <th>Role</th>
                <th>Target</th>
                <th>Status</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="text-center text-muted">Loading…</td></tr>
              ) : auditLogs.length === 0 ? (
                <tr><td colSpan={6} className="text-center text-muted">No audit entries.</td></tr>
              ) : auditLogs.map((r) => (
                <tr key={r.id}>
                  <td><span className="badge badge-admin">{r.action}</span></td>
                  <td className="text-sm">{r.user_id || '—'}</td>
                  <td className="text-xs text-muted">{r.role || '—'}</td>
                  <td className="text-xs text-muted">
                    {r.target_type && `${r.target_type} #${r.target_id}`}
                  </td>
                  <td>
                    <span className={`badge ${r.status === 'SUCCESS' ? 'badge-success' : 'badge-danger'}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="text-xs text-muted">
                    {r.timestamp ? new Date(r.timestamp).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
}
