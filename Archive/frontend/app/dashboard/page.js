'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import AppLayout from '../components/AppLayout';
import { api, formatFileSize, formatRole } from '../lib/api';

function StatusBadge({ status, isApproved, deleteRequested }) {
  if (deleteRequested) return <span className="badge badge-danger">delete req.</span>;
  if (!isApproved) return <span className="badge badge-pending">pending</span>;
  if (status === 'indexed') return <span className="badge badge-success">indexed</span>;
  if (status === 'error') return <span className="badge badge-danger">error</span>;
  if (['processed', 'reviewed'].includes(status)) return <span className="badge badge-approved">processed</span>;
  return <span className="badge badge-approved">{status || 'approved'}</span>;
}

export default function DashboardPage() {
  const router = useRouter();
  const user = api.getUser();

  const isAdmin = user && ['super_admin', 'hq_admin', 'unit_admin'].includes(user.role);
  const isOfficerOrAdmin = user && ['officer', 'unit_admin', 'hq_admin', 'super_admin'].includes(user.role);

  const isClerk = user && user.role === 'clerk';

  const [documents, setDocuments] = useState([]);
  const [myUploads, setMyUploads] = useState([]);
  const [users, setUsers] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState([]);
  const [pendingDeletions, setPendingDeletions] = useState([]);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const promises = [
          api.listDocuments({ limit: 100 }).catch(() => []),
        ];

        if (isClerk) promises.push(api.listDocuments({ my_uploads: true, limit: 100 }).catch(() => []));
        if (isAdmin) promises.push(api.listUsers().catch(() => []));
        if (isOfficerOrAdmin) {
          promises.push(api.listPendingApprovals().catch(() => []));
          promises.push(api.listPendingDeletions().catch(() => []));
        }

        const results = await Promise.all(promises);
        if (!active) return;

        setDocuments(Array.isArray(results[0]) ? results[0] : []);
        let offset = 1;
        if (isClerk) { setMyUploads(Array.isArray(results[offset]) ? results[offset] : []); offset++; }
        if (isAdmin) { setUsers(Array.isArray(results[offset]) ? results[offset] : []); offset++; }
        if (isOfficerOrAdmin) {
          setPendingApprovals(Array.isArray(results[offset]) ? results[offset] : []); offset++;
          setPendingDeletions(Array.isArray(results[offset]) ? results[offset] : []);
        }
      } catch (err) {
        if (active) setError(err.message || 'Unable to load dashboard');
      } finally {
        if (active) setIsLoading(false);
      }
    }

    load();
    return () => { active = false; };
  }, []);

  const stats = useMemo(() => {
    const approved = documents.filter((d) => d.is_approved).length;
    const pending = documents.filter((d) => !d.is_approved).length;
    const indexed = documents.filter((d) => d.status === 'indexed').length;
    const errors = documents.filter((d) => d.status === 'error').length;
    const storage = documents.reduce((t, d) => t + (d.file_size || 0), 0);
    const deleteReqs = documents.filter((d) => d.delete_requested).length;
    return { approved, pending, indexed, errors, storage, deleteReqs, total: documents.length };
  }, [documents]);

  const userStats = useMemo(() => ({
    admins: users.filter((u) => ['super_admin', 'hq_admin', 'unit_admin'].includes(u.role)).length,
    officers: users.filter((u) => u.role === 'officer').length,
    clerks: users.filter((u) => u.role === 'clerk').length,
    trainees: users.filter((u) => u.role === 'trainee').length,
  }), [users]);

  const recentDocs = documents.slice(0, 6);
  const errorDocs = documents.filter((d) => d.status === 'error');

  return (
    <AppLayout title="Dashboard" subtitle={`Welcome back, ${user?.name || '—'} · ${formatRole(user?.role)}`}>
      {error && <div className="form-error mb-4">{error}</div>}

      {/* ── Primary stats ── */}
      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-icon primary"><span className="material-icons">description</span></div>
          <div className="stat-label">Total Documents</div>
          <div className="stat-value">{isLoading ? '…' : stats.total}</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-icon warning"><span className="material-icons">pending_actions</span></div>
          <div className="stat-label">Pending Approval</div>
          <div className="stat-value">{isLoading ? '…' : stats.pending}</div>
        </div>
        <div className="stat-card success">
          <div className="stat-icon success"><span className="material-icons">check_circle</span></div>
          <div className="stat-label">Indexed &amp; Ready</div>
          <div className="stat-value">{isLoading ? '…' : stats.indexed}</div>
        </div>
        <div className="stat-card danger">
          <div className="stat-icon danger"><span className="material-icons">error_outline</span></div>
          <div className="stat-label">OCR Errors</div>
          <div className="stat-value">{isLoading ? '…' : stats.errors}</div>
        </div>
      </div>

      {/* ── Admin user stats ── */}
      {isAdmin && (
        <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>
          <div className="stat-card primary">
            <div className="stat-label">Admins</div>
            <div className="stat-value" style={{ fontSize: '24px' }}>{isLoading ? '…' : userStats.admins}</div>
          </div>
          <div className="stat-card warning">
            <div className="stat-label">Officers</div>
            <div className="stat-value" style={{ fontSize: '24px' }}>{isLoading ? '…' : userStats.officers}</div>
          </div>
          <div className="stat-card success">
            <div className="stat-label">Clerks</div>
            <div className="stat-value" style={{ fontSize: '24px' }}>{isLoading ? '…' : userStats.clerks}</div>
          </div>
          <div className="stat-card danger">
            <div className="stat-label">Trainees</div>
            <div className="stat-value" style={{ fontSize: '24px' }}>{isLoading ? '…' : userStats.trainees}</div>
          </div>
        </div>
      )}

      <div className="two-col mt-8">
        {/* ── Left column ── */}
        <div className="flex-col gap-6">

          {/* Quick actions */}
          <div>
            <h2 className="section-title">Quick Actions</h2>
            <div className="quick-actions">
              {(user?.role === 'officer' || user?.role === 'clerk') && (
                <Link className="quick-action-card" href="/uploads">
                  <div className="quick-action-icon" style={{ background: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
                    <span className="material-icons">upload_file</span>
                  </div>
                  <div>
                    <div className="quick-action-title">Upload</div>
                    <div className="quick-action-desc">Add new records</div>
                  </div>
                </Link>
              )}
              <Link className="quick-action-card" href="/archive">
                <div className="quick-action-icon" style={{ background: 'var(--color-tertiary-light)', color: 'var(--color-tertiary)' }}>
                  <span className="material-icons">inventory_2</span>
                </div>
                <div>
                  <div className="quick-action-title">Archive</div>
                  <div className="quick-action-desc">{stats.total} documents</div>
                </div>
              </Link>
              {isOfficerOrAdmin && stats.pending > 0 && (
                <Link className="quick-action-card" href="/archive?tab=pending">
                  <div className="quick-action-icon" style={{ background: 'var(--color-error-container)', color: 'var(--color-error)' }}>
                    <span className="material-icons">fact_check</span>
                  </div>
                  <div>
                    <div className="quick-action-title">Review</div>
                    <div className="quick-action-desc">{stats.pending} pending</div>
                  </div>
                </Link>
              )}
              {isAdmin && (
                <Link className="quick-action-card" href="/users">
                  <div className="quick-action-icon" style={{ background: 'var(--color-surface-highest)', color: 'var(--color-on-surface-var)' }}>
                    <span className="material-icons">admin_panel_settings</span>
                  </div>
                  <div>
                    <div className="quick-action-title">Users</div>
                    <div className="quick-action-desc">Manage access</div>
                  </div>
                </Link>
              )}
            </div>
          </div>

          {/* Clerk — My Upload Status */}
          {isClerk && (
            <div className="card">
              <h2 className="section-title mb-3">My Upload Status</h2>
              <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(3,1fr)', gap: '8px' }}>
                <Link href="/archive?tab=pending" style={{ textDecoration: 'none' }}>
                  <div className="stat-card warning" style={{ cursor: 'pointer', padding: '12px' }}>
                    <div className="stat-label" style={{ fontSize: '11px' }}>Pending</div>
                    <div className="stat-value" style={{ fontSize: '22px' }}>
                      {isLoading ? '…' : myUploads.filter((d) => !d.is_approved && d.status !== 'rejected').length}
                    </div>
                  </div>
                </Link>
                <Link href="/archive?tab=my_uploads" style={{ textDecoration: 'none' }}>
                  <div className="stat-card success" style={{ cursor: 'pointer', padding: '12px' }}>
                    <div className="stat-label" style={{ fontSize: '11px' }}>Approved</div>
                    <div className="stat-value" style={{ fontSize: '22px' }}>
                      {isLoading ? '…' : myUploads.filter((d) => d.is_approved).length}
                    </div>
                  </div>
                </Link>
                <Link href="/archive?tab=rejected" style={{ textDecoration: 'none' }}>
                  <div className="stat-card danger" style={{ cursor: 'pointer', padding: '12px' }}>
                    <div className="stat-label" style={{ fontSize: '11px' }}>Rejected</div>
                    <div className="stat-value" style={{ fontSize: '22px' }}>
                      {isLoading ? '…' : myUploads.filter((d) => d.status === 'rejected').length}
                    </div>
                  </div>
                </Link>
              </div>
              {myUploads.filter((d) => !d.is_approved || d.status === 'rejected').slice(0, 4).map((doc) => (
                <div
                  key={doc.id}
                  className="activity-item"
                  style={{ cursor: 'pointer', marginTop: '8px' }}
                  onClick={() => router.push(`/archive/${doc.id}`)}
                >
                  <div className="avatar" style={{
                    background: doc.status === 'rejected' ? 'var(--color-error-container)' : 'var(--color-warning-container, #fff3e0)',
                    color: doc.status === 'rejected' ? 'var(--color-error)' : 'var(--color-warning)',
                  }}>
                    <span className="material-icons">{doc.status === 'rejected' ? 'cancel' : 'hourglass_empty'}</span>
                  </div>
                  <div className="activity-text" style={{ flex: 1, minWidth: 0 }}>
                    <strong style={{ fontSize: '13px', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {doc.file_name}
                    </strong>
                    <div className="text-xs text-muted mt-1">
                      {doc.status === 'rejected'
                        ? <>✗ {doc.rejector_name || 'Officer'}{doc.rejection_reason ? ` — ${doc.rejection_reason.slice(0, 50)}` : ''}</>
                        : 'Awaiting officer approval'}
                    </div>
                  </div>
                  <StatusBadge status={doc.status} isApproved={doc.is_approved} deleteRequested={doc.delete_requested} />
                </div>
              ))}
            </div>
          )}

          {/* Storage */}
          <div className="card-sm">
            <h3 className="section-title mb-2">Storage</h3>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-bold text-primary">{formatFileSize(stats.storage)}</span>
              <span className="text-sm text-muted">across {stats.total} files</span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${Math.min(100, Math.max(3, stats.storage / (100 * 1024 * 1024) * 100))}%` }}></div>
            </div>
          </div>

          {/* OCR errors — needs attention */}
          {errorDocs.length > 0 && (
            <div className="card">
              <h2 className="section-title" style={{ color: 'var(--color-error)' }}>
                OCR Errors — Action Required
              </h2>
              {errorDocs.map((doc) => (
                <div
                  key={doc.id}
                  className="activity-item"
                  style={{ cursor: 'pointer', borderLeft: '3px solid var(--color-error)', paddingLeft: '12px' }}
                  onClick={() => router.push(`/archive/${doc.id}`)}
                >
                  <div className="avatar" style={{ background: 'var(--color-error-container)', color: 'var(--color-error)' }}>
                    <span className="material-icons">error</span>
                  </div>
                  <div className="activity-text">
                    <strong style={{ fontSize: '13px', wordBreak: 'break-all' }}>{doc.file_name}</strong>
                    <div className="mt-1 text-xs text-muted">
                      {doc.branch_name || '—'} · {doc.document_type_name || '—'}
                      <span style={{ marginLeft: '8px', color: 'var(--color-error)' }}>Click to re-index</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Right column ── */}
        <div className="flex-col gap-6">

          {/* Pending approvals for officers/admins */}
          {isOfficerOrAdmin && (
            <div className="card">
              <div className="flex justify-between items-center mb-4">
                <h2 className="section-title" style={{ margin: 0 }}>Pending Approvals</h2>
                <span className="badge badge-pending">{pendingApprovals.length}</span>
              </div>
              {pendingApprovals.length === 0 ? (
                <div className="empty-state" style={{ padding: '16px 0' }}>
                  <span className="material-icons">check_circle</span>
                  <div>All documents approved</div>
                </div>
              ) : (
                pendingApprovals.slice(0, 5).map((doc) => (
                  <div
                    key={doc.id}
                    className="activity-item"
                    style={{ cursor: 'pointer' }}
                    onClick={() => router.push(`/archive/${doc.id}`)}
                  >
                    <div className="avatar avatar-blue">{doc.file_name?.charAt(0)?.toUpperCase() || 'D'}</div>
                    <div className="activity-text" style={{ flex: 1, minWidth: 0 }}>
                      <strong style={{ fontSize: '13px', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {doc.file_name}
                      </strong>
                      <div className="text-xs text-muted mt-1">
                        {doc.uploader_name || 'Unknown'} · {doc.branch_name || '—'} · {doc.document_type_name || '—'}
                      </div>
                    </div>
                    <span className="badge badge-pending" style={{ flexShrink: 0 }}>Approve</span>
                  </div>
                ))
              )}
              {pendingApprovals.length > 5 && (
                <Link href="/archive" className="btn btn-ghost btn-sm mt-2">View all {pendingApprovals.length}</Link>
              )}
            </div>
          )}

          {/* Pending delete requests */}
          {isOfficerOrAdmin && pendingDeletions.length > 0 && (
            <div className="card">
              <div className="flex justify-between items-center mb-4">
                <h2 className="section-title" style={{ margin: 0, color: 'var(--color-error)' }}>Delete Requests</h2>
                <span className="badge badge-danger">{pendingDeletions.length}</span>
              </div>
              {pendingDeletions.map((doc) => (
                <div
                  key={doc.id}
                  className="activity-item"
                  style={{ cursor: 'pointer' }}
                  onClick={() => router.push(`/archive/${doc.id}`)}
                >
                  <div className="avatar" style={{ background: 'var(--color-error-container)', color: 'var(--color-error)' }}>
                    <span className="material-icons">delete_outline</span>
                  </div>
                  <div className="activity-text" style={{ flex: 1, minWidth: 0 }}>
                    <strong style={{ fontSize: '13px', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {doc.file_name}
                    </strong>
                    <div className="text-xs text-muted mt-1">{doc.branch_name || '—'} · Requested deletion</div>
                  </div>
                  <span className="badge badge-danger" style={{ flexShrink: 0 }}>Review</span>
                </div>
              ))}
            </div>
          )}

          {/* Recent documents */}
          <div className="card">
            <div className="flex justify-between items-center mb-4">
              <h2 className="section-title" style={{ margin: 0 }}>Recent Documents</h2>
              <Link href="/archive" className="btn btn-ghost btn-sm">View all</Link>
            </div>
            {recentDocs.length === 0 && !isLoading && (
              <div className="empty-state" style={{ padding: '16px 0' }}>
                <span className="material-icons">inventory_2</span>
                <div>No documents available for your access level.</div>
              </div>
            )}
            {recentDocs.map((doc) => (
              <div
                key={doc.id}
                className="activity-item"
                style={{ cursor: 'pointer' }}
                onClick={() => router.push(`/archive/${doc.id}`)}
              >
                <div className="avatar avatar-blue">{doc.file_name?.charAt(0)?.toUpperCase() || 'D'}</div>
                <div className="activity-text" style={{ flex: 1, minWidth: 0 }}>
                  <strong style={{ fontSize: '13px', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {doc.file_name}
                  </strong>
                  <div className="text-xs text-muted mt-1">
                    {doc.hq_name || '—'} / {doc.unit_name || '—'} · {doc.document_type_name || 'Document'}
                  </div>
                </div>
                <StatusBadge status={doc.status} isApproved={doc.is_approved} deleteRequested={doc.delete_requested} />
              </div>
            ))}
          </div>

          {/* Role info card */}
          <div className="info-card">
            <h3 className="info-card-title">Your Access Level</h3>
            <p className="info-card-text">
              <strong>{formatRole(user?.role)}</strong>
              {user?.hq_id && ` · HQ scope`}
              {user?.unit_id && ` · Unit scope`}
              {user?.branch_id && ` · Branch scope`}
              {user?.clerk_type && ` · ${user.clerk_type} clerk`}
              {user?.task_category && ` (${user.task_category})`}
            </p>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
