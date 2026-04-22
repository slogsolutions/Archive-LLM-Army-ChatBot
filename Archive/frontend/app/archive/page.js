'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import AppLayout from '../components/AppLayout';
import { api, formatFileSize } from '../lib/api';

// Tabs shown to each role category
const OFFICER_TABS = [
  { key: 'all',              label: 'All' },
  { key: 'pending',          label: 'Pending Review' },
  { key: 'indexed',          label: 'Indexed' },
  { key: 'processed',        label: 'Processed' },
  { key: 'delete_requested', label: 'Delete Requests' },
];

const CLERK_TABS = [
  { key: 'all',       label: 'All' },
  { key: 'my_uploads', label: 'My Uploads' },
  { key: 'indexed',   label: 'Indexed' },
  { key: 'processed', label: 'Processed' },
];

const DEFAULT_TABS = [
  { key: 'all',     label: 'All' },
  { key: 'indexed', label: 'Indexed' },
];

function getTabs(role) {
  if (['officer', 'unit_admin', 'hq_admin', 'super_admin'].includes(role)) return OFFICER_TABS;
  if (role === 'clerk') return CLERK_TABS;
  return DEFAULT_TABS;
}

function statusBadge(doc) {
  if (doc.status === 'rejected') return 'badge-danger';
  if (doc.delete_requested) return 'badge-danger';
  if (!doc.is_approved) return 'badge-pending';
  if (doc.status === 'indexed') return 'badge-success';
  if (['processed', 'reviewed'].includes(doc.status)) return 'badge-approved';
  return 'badge-approved';
}

function statusLabel(doc) {
  if (doc.status === 'rejected') return 'rejected';
  if (doc.delete_requested) return 'delete requested';
  if (!doc.is_approved) return 'pending approval';
  return doc.status || 'approved';
}

export default function DocumentArchivePage() {
  const router = useRouter();
  const user = api.getUser();
  const role = user?.role || '';

  const tabs = getTabs(role);

  const [documents, setDocuments] = useState([]);
  const [searchResults, setSearchResults] = useState(null);
  const [query, setQuery] = useState('');
  const [activeTab, setActiveTab] = useState('all');
  const [filterBranch, setFilterBranch] = useState('');
  const [filterDocType, setFilterDocType] = useState('');
  const [filterYear, setFilterYear] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);

  const searchTimer = useRef(null);

  const loadDocuments = (tab = activeTab) => {
    setError('');
    setIsLoading(true);
    setSearchResults(null);

    const params = {};

    if (tab === 'my_uploads') {
      params.my_uploads = true;
    } else if (tab === 'pending') {
      params.status = 'pending';
    } else if (tab === 'delete_requested') {
      params.status = 'delete_requested';
    } else if (tab !== 'all') {
      params.status = tab;
    }

    if (filterBranch) params.branch_name = filterBranch;
    if (filterDocType) params.doc_type = filterDocType;
    if (filterYear) params.year = filterYear;

    api.listDocuments(params)
      .then((data) => setDocuments(Array.isArray(data) ? data : []))
      .catch((err) => setError(err.message || 'Unable to load documents'))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    loadDocuments(activeTab);
  }, [activeTab, filterBranch, filterDocType, filterYear]);

  // Debounced semantic search
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);

    const trimmed = query.trim();
    if (!trimmed || trimmed.length < 2) {
      setSearchResults(null);
      return;
    }

    setIsSearching(true);
    searchTimer.current = setTimeout(async () => {
      try {
        const filters = {};
        if (filterBranch) filters.branch = filterBranch;
        if (filterDocType) filters.doc_type = filterDocType;
        if (filterYear) filters.year = filterYear;
        const results = await api.searchDocuments(trimmed, filters);
        setSearchResults(Array.isArray(results) ? results : []);
      } catch {
        setSearchResults(null);
      } finally {
        setIsSearching(false);
      }
    }, 500);

    return () => clearTimeout(searchTimer.current);
  }, [query, filterBranch, filterDocType, filterYear]);

  const visibleDocuments = useMemo(() => {
    const search = query.trim().toLowerCase();
    if (!search) return documents;
    return documents.filter((doc) =>
      [doc.file_name, doc.branch_name, doc.document_type_name, doc.status, doc.hq_name, doc.unit_name]
        .some((v) => String(v || '').toLowerCase().includes(search))
    );
  }, [documents, query]);

  const displayDocs = searchResults !== null ? searchResults : visibleDocuments;
  const isSearchMode = searchResults !== null;

  const stats = {
    total: documents.length,
    pending: documents.filter((d) => !d.is_approved && d.status !== 'rejected').length,
    approved: documents.filter((d) => d.is_approved).length,
    indexed: documents.filter((d) => d.status === 'indexed').length,
    rejected: documents.filter((d) => d.status === 'rejected').length,
  };

  const isOfficer = ['officer', 'unit_admin', 'hq_admin', 'super_admin'].includes(role);
  const isClerk = role === 'clerk';

  return (
    <AppLayout
      title="Document Archive"
      subtitle="View, approve, download, and search documents allowed by your access level."
      actions={
        <div className="search-bar">
          <span className="material-icons">{isSearching ? 'hourglass_empty' : 'search'}</span>
          <input
            type="text"
            placeholder="Semantic search or filter..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query && (
            <button
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
              onClick={() => setQuery('')}
            >
              <span className="material-icons" style={{ fontSize: '18px' }}>close</span>
            </button>
          )}
        </div>
      }
    >
      {error && <div className="form-error mb-4">{error}</div>}

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-label">Total</div>
          <div className="stat-value">{isLoading ? '...' : stats.total}</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-label">Pending Approval</div>
          <div className="stat-value">{isLoading ? '...' : stats.pending}</div>
        </div>
        <div className="stat-card success">
          <div className="stat-label">Approved</div>
          <div className="stat-value">{isLoading ? '...' : stats.approved}</div>
        </div>
        <div className="stat-card danger">
          <div className="stat-label">Indexed</div>
          <div className="stat-value">{isLoading ? '...' : stats.indexed}</div>
        </div>
      </div>

      {/* Filters row */}
      <div className="flex gap-3 mt-6 mb-2" style={{ flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          className="form-input"
          style={{ maxWidth: '160px' }}
          placeholder="Branch..."
          value={filterBranch}
          onChange={(e) => setFilterBranch(e.target.value)}
        />
        <input
          className="form-input"
          style={{ maxWidth: '180px' }}
          placeholder="Doc type..."
          value={filterDocType}
          onChange={(e) => setFilterDocType(e.target.value)}
        />
        <input
          type="number"
          className="form-input"
          style={{ maxWidth: '110px' }}
          placeholder="Year..."
          value={filterYear}
          onChange={(e) => setFilterYear(e.target.value)}
        />
        {(filterBranch || filterDocType || filterYear) && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => { setFilterBranch(''); setFilterDocType(''); setFilterYear(''); }}
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Tabs */}
      {!isSearchMode && (
        <div className="flex gap-2 mt-2 mb-4" style={{ flexWrap: 'wrap' }}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              className={`btn btn-sm ${activeTab === tab.key ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
              {tab.key === 'pending' && stats.pending > 0 && (
                <span style={{
                  marginLeft: '6px', background: 'var(--color-warning)',
                  color: '#fff', borderRadius: '10px', padding: '0 6px', fontSize: '11px'
                }}>{stats.pending}</span>
              )}
              {tab.key === 'my_uploads' && stats.rejected > 0 && (
                <span style={{
                  marginLeft: '6px', background: 'var(--color-danger)',
                  color: '#fff', borderRadius: '10px', padding: '0 6px', fontSize: '11px'
                }}>{stats.rejected}</span>
              )}
            </button>
          ))}
        </div>
      )}

      {isSearchMode && (
        <div className="flex items-center gap-2 mb-4">
          <span className="badge badge-approved">Semantic Search</span>
          <span className="text-sm text-muted">{searchResults.length} chunk result{searchResults.length !== 1 ? 's' : ''} for &quot;{query}&quot;</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setQuery('')}>Clear</button>
        </div>
      )}

      <div className="two-col-wide-right">
        <div className="table-wrapper">
          {isSearchMode ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Branch / Type</th>
                  <th>Excerpt</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {displayDocs.map((r, idx) => (
                  <tr key={idx} onClick={() => router.push(`/archive/${r.doc_id}`)} style={{ cursor: 'pointer' }}>
                    <td>
                      <div className="flex items-center gap-3">
                        <div className="file-icon pdf"><span className="material-icons">description</span></div>
                        <div>
                          <strong>{r.file_name}</strong>
                          <div className="text-xs text-muted">p.{r.page_number} · chunk {r.chunk_index}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div>{r.branch || '-'}</div>
                      <div className="text-xs text-muted">{r.doc_type || '-'} {r.year ? `· ${r.year}` : ''}</div>
                    </td>
                    <td style={{ maxWidth: '320px' }}>
                      <span className="text-sm" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                        {r.content}
                      </span>
                    </td>
                    <td>
                      <span className="badge badge-approved">{(r.score || 0).toFixed(3)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>HQ / Unit</th>
                  <th>Branch / Type</th>
                  <th>Year</th>
                  <th>Size</th>
                  <th>Status / Approval</th>
                </tr>
              </thead>
              <tbody>
                {visibleDocuments.map((doc) => (
                  <tr key={doc.id} onClick={() => router.push(`/archive/${doc.id}`)} style={{ cursor: 'pointer' }}>
                    <td>
                      <div className="flex items-center gap-3">
                        <div className="file-icon pdf"><span className="material-icons">description</span></div>
                        <div>
                          <strong>{doc.file_name}</strong>
                          <div className="text-xs text-muted">Rank {doc.min_visible_rank || 6}+</div>
                        </div>
                      </div>
                    </td>
                    <td className="text-muted">
                      <div>{doc.hq_name || '-'}</div>
                      <div className="text-xs">{doc.unit_name || '-'}</div>
                    </td>
                    <td>
                      <div>{doc.branch_name || '-'}</div>
                      <div className="text-xs text-muted">{doc.document_type_name || '-'}</div>
                    </td>
                    <td className="text-muted">{doc.year || '-'}</td>
                    <td className="text-muted">{formatFileSize(doc.file_size)}</td>
                    <td>
                      <span className={`badge ${statusBadge(doc)}`}>{statusLabel(doc)}</span>
                      {doc.is_approved && doc.approver_name && (
                        <div className="text-xs text-muted" style={{ marginTop: '2px' }}>
                          ✓ {doc.approver_name}
                        </div>
                      )}
                      {doc.status === 'rejected' && doc.rejector_name && (
                        <div className="text-xs" style={{ marginTop: '2px', color: 'var(--color-danger)' }}>
                          ✗ {doc.rejector_name}
                          {doc.rejection_reason && (
                            <span title={doc.rejection_reason}> — {doc.rejection_reason.length > 30 ? doc.rejection_reason.slice(0, 30) + '…' : doc.rejection_reason}</span>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {!isLoading && displayDocs.length === 0 && (
            <div className="empty-state">
              <span className="material-icons">manage_search</span>
              <div>{isSearchMode ? 'No matching chunks found.' : 'No documents match this view.'}</div>
            </div>
          )}
        </div>

        <div className="flex-col gap-6">
          <div className="info-card">
            <h3 className="info-card-title">Access Controlled</h3>
            <p className="info-card-text">
              Documents are filtered server-side by HQ, unit, branch, approval state, and rank visibility.
            </p>
          </div>

          {isOfficer && stats.pending > 0 && (
            <div className="info-card amber-card">
              <h3 className="info-card-title">
                <span className="material-icons" style={{ fontSize: '16px', verticalAlign: 'middle' }}>pending_actions</span>
                {' '}{stats.pending} Pending Review
              </h3>
              <p className="info-card-text">
                Switch to <strong>Pending Review</strong> tab to approve or reject documents uploaded by clerks.
              </p>
            </div>
          )}

          {isClerk && stats.rejected > 0 && (
            <div className="info-card" style={{ borderLeft: '4px solid var(--color-danger)' }}>
              <h3 className="info-card-title" style={{ color: 'var(--color-danger)' }}>
                <span className="material-icons" style={{ fontSize: '16px', verticalAlign: 'middle' }}>cancel</span>
                {' '}{stats.rejected} Rejected
              </h3>
              <p className="info-card-text">
                Check the <strong>My Uploads</strong> tab to see rejection reasons.
              </p>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
