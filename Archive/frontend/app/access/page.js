'use client';

import { useEffect, useState, useCallback } from 'react';
import AppLayout from '../components/AppLayout';
import { api, formatRole } from '../lib/api';

// ── Constants ─────────────────────────────────────────────────────────────────

const ACCESS_LEVELS = [
  { value: 1, label: 'Super Admin Only',   badge: 'badge-danger' },
  { value: 2, label: 'HQ Admin & Above',   badge: 'badge-warning' },
  { value: 3, label: 'Unit Admin & Above', badge: 'badge-warning' },
  { value: 4, label: 'Officers & Above',   badge: 'badge-admin' },
  { value: 5, label: 'Clerks & Above',     badge: 'badge-success' },
  { value: 6, label: 'All Staff',          badge: 'badge-info' },
];

const ROLES = [
  { value: 'super_admin', label: 'Super Admin', rank: 1 },
  { value: 'hq_admin',    label: 'HQ Admin',    rank: 2 },
  { value: 'unit_admin',  label: 'Unit Admin',  rank: 3 },
  { value: 'officer',     label: 'Officer',     rank: 4 },
  { value: 'clerk',       label: 'Clerk',       rank: 5 },
  { value: 'trainee',     label: 'Trainee',     rank: 6 },
];

const ROLE_RANK = Object.fromEntries(ROLES.map((r) => [r.value, r.rank]));

function accessLabel(rank) {
  return ACCESS_LEVELS.find((l) => l.value === rank) || ACCESS_LEVELS[5];
}

// ── Inline save status indicator ──────────────────────────────────────────────

function SaveStatus({ status }) {
  if (!status) return null;
  if (status === 'saving') return <span className="text-xs text-muted ml-2">saving…</span>;
  if (status === 'ok')     return <span className="text-xs text-success ml-2">✓ saved</span>;
  return <span className="text-xs text-danger ml-2">{status}</span>;
}

// ── Document Access Row ───────────────────────────────────────────────────────

function DocRow({ doc, currentUser }) {
  const [rank, setRank]       = useState(doc.min_visible_rank ?? 6);
  const [status, setStatus]   = useState(null);
  const canEdit = currentUser.role !== 'clerk' && currentUser.role !== 'trainee';

  async function save(newRank) {
    setRank(newRank);
    setStatus('saving');
    try {
      await api.patchDocumentAccess(doc.id, Number(newRank));
      setStatus('ok');
    } catch (e) {
      setStatus(e.message || 'error');
    } finally {
      setTimeout(() => setStatus(null), 2000);
    }
  }

  const al = accessLabel(rank);
  const shortName = doc.file_name?.replace(/^[0-9a-f-]{36}_/i, '') || doc.file_name;

  return (
    <tr>
      <td>
        <div className="flex flex-col">
          <strong className="text-sm truncate max-w-xs" title={shortName}>{shortName}</strong>
          <span className="text-xs text-muted">{doc.document_type_name} · {doc.branch_name}</span>
        </div>
      </td>
      <td>
        <span className={`badge ${doc.is_approved ? 'badge-success' : 'badge-warning'}`}>
          {doc.is_approved ? 'Approved' : 'Pending'}
        </span>
      </td>
      <td>
        {canEdit ? (
          <div className="flex items-center gap-2">
            <select
              className="form-select"
              style={{ width: 200, padding: '4px 8px', fontSize: 13 }}
              value={rank}
              onChange={(e) => save(e.target.value)}
            >
              {ACCESS_LEVELS.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
            <SaveStatus status={status} />
          </div>
        ) : (
          <span className={`badge ${al.badge}`}>{al.label}</span>
        )}
      </td>
      <td className="text-muted text-xs">
        {doc.year || '—'}
      </td>
    </tr>
  );
}

// ── User Access Row ───────────────────────────────────────────────────────────

function UserRow({ user, currentUser, hqs, units }) {
  const [role, setRole]         = useState(user.role);
  const [rankLevel, setRankLevel] = useState(user.rank_level);
  const [status, setStatus]     = useState(null);

  // Can edit if current user has higher rank (lower rank_level number)
  const canEdit = (
    ['super_admin', 'hq_admin', 'unit_admin'].includes(currentUser.role) &&
    currentUser.rank_level < user.rank_level
  );

  async function saveRole(newRole) {
    setRole(newRole);
    setRankLevel(ROLE_RANK[newRole] ?? rankLevel);
    setStatus('saving');
    try {
      await api.patchUserAccess(user.id, { role: newRole, rank_level: ROLE_RANK[newRole] });
      setStatus('ok');
    } catch (e) {
      setStatus(e.message || 'error');
    } finally {
      setTimeout(() => setStatus(null), 2000);
    }
  }

  async function saveRank(newRank) {
    setRankLevel(Number(newRank));
    setStatus('saving');
    try {
      await api.patchUserAccess(user.id, { rank_level: Number(newRank) });
      setStatus('ok');
    } catch (e) {
      setStatus(e.message || 'error');
    } finally {
      setTimeout(() => setStatus(null), 2000);
    }
  }

  const hqName   = hqs.find((h) => h.id === user.hq_id)?.name || '—';
  const unitName = units.find((u) => u.id === user.unit_id)?.name || '—';

  // Roles the current user is allowed to assign
  const assignableRoles = ROLES.filter((r) => r.rank > currentUser.rank_level);

  return (
    <tr>
      <td>
        <div className="flex items-center gap-3">
          <div className="avatar avatar-green">{user.name?.charAt(0)?.toUpperCase() || 'U'}</div>
          <div>
            <strong>{user.name}</strong>
            <div className="text-xs text-muted">{user.army_number}</div>
          </div>
        </div>
      </td>
      <td className="text-xs text-muted">{hqName} / {unitName}</td>
      <td>
        {canEdit ? (
          <select
            className="form-select"
            style={{ width: 150, padding: '4px 8px', fontSize: 13 }}
            value={role}
            onChange={(e) => saveRole(e.target.value)}
          >
            {assignableRoles.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        ) : (
          <span className="badge badge-admin">{formatRole(role)}</span>
        )}
      </td>
      <td>
        {canEdit ? (
          <select
            className="form-select"
            style={{ width: 120, padding: '4px 8px', fontSize: 13 }}
            value={rankLevel}
            onChange={(e) => saveRank(e.target.value)}
          >
            {ACCESS_LEVELS.filter((l) => l.value > currentUser.rank_level).map((l) => (
              <option key={l.value} value={l.value}>Level {l.value}</option>
            ))}
          </select>
        ) : (
          <span className="text-sm">Level {rankLevel}</span>
        )}
      </td>
      <td>
        <SaveStatus status={status} />
        {!canEdit && (
          <span className="text-xs text-muted">No permission</span>
        )}
      </td>
    </tr>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function AccessControlPage() {
  const [tab, setTab]       = useState('documents');
  const [docs, setDocs]     = useState([]);
  const [users, setUsers]   = useState([]);
  const [hqs, setHqs]       = useState([]);
  const [units, setUnits]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState('');
  const [currentUser, setCurrentUser] = useState(null);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [me, docList, userList, hqList, unitList] = await Promise.all([
        api.me(),
        api.listDocuments({ limit: 200 }),
        api.listUsers().catch(() => []),
        api.listHq(),
        api.listUnits(),
      ]);
      setCurrentUser(me);
      setDocs(Array.isArray(docList) ? docList : docList?.documents || []);
      setUsers(Array.isArray(userList) ? userList : []);
      setHqs(Array.isArray(hqList) ? hqList : []);
      setUnits(Array.isArray(unitList) ? unitList : []);
    } catch (e) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!currentUser) return null;

  const q = search.toLowerCase();
  const filteredDocs  = docs.filter((d) =>
    !q ||
    d.file_name?.toLowerCase().includes(q) ||
    d.document_type_name?.toLowerCase().includes(q) ||
    d.branch_name?.toLowerCase().includes(q)
  );
  const filteredUsers = users.filter((u) =>
    !q ||
    u.name?.toLowerCase().includes(q) ||
    u.army_number?.toLowerCase().includes(q) ||
    u.role?.toLowerCase().includes(q)
  );

  return (
    <AppLayout
      title="Access Control"
      subtitle="Manage document visibility levels and user roles directly from the UI."
    >
      {error && <div className="form-error mb-4">{error}</div>}

      {/* ── Permission hierarchy legend ── */}
      <div className="card mb-6" style={{ padding: '12px 16px' }}>
        <h3 className="section-title" style={{ marginBottom: 8 }}>Rank & Visibility Matrix</h3>
        <div className="flex flex-wrap gap-2">
          {ACCESS_LEVELS.map((l) => (
            <span key={l.value} className={`badge ${l.badge}`} style={{ fontSize: 12 }}>
              Level {l.value} — {l.label}
            </span>
          ))}
        </div>
        <p className="text-xs text-muted mt-2">
          Each document&apos;s access level controls who can view it.
          You can only assign levels <strong>at or below your own rank</strong>.
          Role changes are limited to your subordinates.
        </p>
      </div>

      {/* ── Tabs ── */}
      <div className="flex gap-2 mb-4">
        {['documents', 'users'].map((t) => (
          <button
            key={t}
            type="button"
            className={`btn ${tab === t ? 'btn-primary' : 'btn-secondary'} btn-sm`}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
        <input
          className="form-input ml-auto"
          style={{ width: 240, padding: '4px 10px', fontSize: 13 }}
          placeholder={`Search ${tab}…`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* ── Documents tab ── */}
      {tab === 'documents' && (
        <div className="table-wrapper animated-panel">
          <table className="table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Status</th>
                <th>
                  Min Access Level
                  <span className="text-xs text-muted ml-2">(who can view)</span>
                </th>
                <th>Year</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="text-center text-muted">Loading…</td></tr>
              ) : filteredDocs.length === 0 ? (
                <tr><td colSpan={4} className="text-center text-muted">No documents found.</td></tr>
              ) : filteredDocs.map((doc) => (
                <DocRow key={doc.id} doc={doc} currentUser={currentUser} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Users tab ── */}
      {tab === 'users' && (
        <div className="table-wrapper animated-panel">
          <table className="table">
            <thead>
              <tr>
                <th>Personnel</th>
                <th>Scope (HQ / Unit)</th>
                <th>
                  Role
                  <span className="text-xs text-muted ml-2">(dropdown = editable)</span>
                </th>
                <th>Rank Level</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="text-center text-muted">Loading…</td></tr>
              ) : filteredUsers.length === 0 ? (
                <tr><td colSpan={5} className="text-center text-muted">No users in your scope.</td></tr>
              ) : filteredUsers.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  currentUser={currentUser}
                  hqs={hqs}
                  units={units}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
}
