'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import AppLayout from '../components/AppLayout';
import { api, formatFileSize } from '../lib/api';

function statusBadge(doc) {
  if (!doc.is_approved) return 'badge-pending';
  if (doc.status === 'reviewed') return 'badge-approved';
  return 'badge-approved';
}

export default function DocumentArchivePage() {
  const router = useRouter();
  const [documents, setDocuments] = useState([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;

    api.listDocuments()
      .then((data) => {
        if (active) setDocuments(Array.isArray(data) ? data : []);
      })
      .catch((err) => {
        if (active) setError(err.message || 'Unable to load documents');
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const visibleDocuments = useMemo(() => {
    const search = query.trim().toLowerCase();
    if (!search) return documents;

    return documents.filter((doc) => [
      doc.file_name,
      doc.branch_name,
      doc.document_type_name,
      doc.status,
      doc.ocr_text,
      doc.corrected_text,
    ].some((value) => String(value || '').toLowerCase().includes(search)));
  }, [documents, query]);

  const pending = documents.filter((doc) => !doc.is_approved).length;
  const approved = documents.filter((doc) => doc.is_approved).length;
  const processed = documents.filter((doc) => ['processed', 'reviewed', 'indexed', 'approved'].includes(doc.status)).length;

  return (
    <AppLayout
      title="Document Archive"
      subtitle="View, approve, download, and search documents allowed by backend RBAC."
      actions={
        <div className="search-bar">
          <span className="material-icons">search</span>
          <input type="text" placeholder="Search visible documents..." value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
      }
    >
      {error && <div className="form-error mb-4">{error}</div>}
      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-label">Total Documents</div>
          <div className="stat-value">{isLoading ? '...' : documents.length}</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-label">Pending Review</div>
          <div className="stat-value">{isLoading ? '...' : pending}</div>
        </div>
        <div className="stat-card success">
          <div className="stat-label">Approved</div>
          <div className="stat-value">{isLoading ? '...' : approved}</div>
        </div>
        <div className="stat-card danger">
          <div className="stat-label">OCR Ready</div>
          <div className="stat-value">{isLoading ? '...' : processed}</div>
        </div>
      </div>

      <div className="two-col-wide-right mt-8">
        <div className="table-wrapper">
          <table className="table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Branch</th>
                <th>Type</th>
                <th>Size</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visibleDocuments.map((doc) => (
                <tr key={doc.id} onClick={() => router.push(`/archive/${doc.id}`)}>
                  <td>
                    <div className="flex items-center gap-3">
                      <div className="file-icon pdf"><span className="material-icons">description</span></div>
                      <div>
                        <strong>{doc.file_name}</strong>
                        <div className="text-xs text-muted">Rank {doc.min_visible_rank || 6} and above</div>
                      </div>
                    </div>
                  </td>
                  <td>{doc.branch_name || '-'}</td>
                  <td>{doc.document_type_name || '-'}</td>
                  <td className="text-muted">{formatFileSize(doc.file_size)}</td>
                  <td><span className={`badge ${statusBadge(doc)}`}>{doc.is_approved ? doc.status || 'approved' : 'pending'}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!isLoading && visibleDocuments.length === 0 && (
            <div className="empty-state">
              <span className="material-icons">manage_search</span>
              <div>No documents match this view.</div>
            </div>
          )}
        </div>

        <div className="flex-col gap-6">
          <div className="info-card">
            <h3 className="info-card-title">Backend Permissions Active</h3>
            <p className="info-card-text">
              This list comes from `/documents/`, so HQ, unit, branch, approval, and rank visibility are enforced server-side.
            </p>
          </div>
          <div className="card-sm">
            <h3 className="section-title mb-2">Search Scope</h3>
            <p className="text-sm text-muted mb-4">The filter searches only the documents returned for your role.</p>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
