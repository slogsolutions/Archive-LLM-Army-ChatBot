'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import AppLayout from '../components/AppLayout';
import { api, formatFileSize } from '../lib/api';

export default function DashboardPage() {
  const [documents, setDocuments] = useState([]);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      try {
        const [documentList, userList] = await Promise.all([
          api.listDocuments().catch(() => []),
          api.listUsers().catch(() => []),
        ]);

        if (!active) return;
        setDocuments(Array.isArray(documentList) ? documentList : []);
        setUsers(Array.isArray(userList) ? userList : []);
      } catch (err) {
        if (active) setError(err.message || 'Unable to load dashboard');
      } finally {
        if (active) setIsLoading(false);
      }
    }

    loadDashboard();
    return () => {
      active = false;
    };
  }, []);

  const stats = useMemo(() => {
    const approved = documents.filter((doc) => doc.is_approved).length;
    const pending = documents.filter((doc) => !doc.is_approved).length;
    const storage = documents.reduce((total, doc) => total + (doc.file_size || 0), 0);

    return { approved, pending, storage };
  }, [documents]);

  return (
    <AppLayout title="Overview" subtitle="Live archive status from the backend">
      <h1 className="page-title mb-6">Welcome back</h1>
      {error && <div className="form-error mb-4">{error}</div>}

      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-icon primary"><span className="material-icons">description</span></div>
          <div className="stat-label">Total Documents</div>
          <div className="stat-value">{isLoading ? '...' : documents.length}</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-icon warning"><span className="material-icons">pending_actions</span></div>
          <div className="stat-label">Pending Approvals</div>
          <div className="stat-value">{isLoading ? '...' : stats.pending}</div>
        </div>
        <div className="stat-card success">
          <div className="stat-icon success"><span className="material-icons">check_circle</span></div>
          <div className="stat-label">Approved</div>
          <div className="stat-value">{isLoading ? '...' : stats.approved}</div>
        </div>
        <div className="stat-card danger">
          <div className="stat-icon danger"><span className="material-icons">group</span></div>
          <div className="stat-label">Managed Users</div>
          <div className="stat-value">{isLoading ? '...' : users.length}</div>
        </div>
      </div>

      <div className="two-col mt-8">
        <div>
          <h2 className="section-title">Quick Actions</h2>
          <div className="quick-actions">
            <Link className="quick-action-card" href="/uploads">
              <div className="quick-action-icon" style={{ background: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
                <span className="material-icons">upload_file</span>
              </div>
              <div>
                <div className="quick-action-title">Upload</div>
                <div className="quick-action-desc">Add new records</div>
              </div>
            </Link>
            <Link className="quick-action-card" href="/archive">
              <div className="quick-action-icon" style={{ background: 'var(--color-tertiary-light)', color: 'var(--color-tertiary)' }}>
                <span className="material-icons">fact_check</span>
              </div>
              <div>
                <div className="quick-action-title">Review</div>
                <div className="quick-action-desc">{stats.pending} pending</div>
              </div>
            </Link>
            <Link className="quick-action-card" href="/users">
              <div className="quick-action-icon" style={{ background: 'var(--color-surface-highest)', color: 'var(--color-on-surface-var)' }}>
                <span className="material-icons">admin_panel_settings</span>
              </div>
              <div>
                <div className="quick-action-title">Access</div>
                <div className="quick-action-desc">Manage roles</div>
              </div>
            </Link>
          </div>

          <h2 className="section-title mt-8">Storage Usage</h2>
          <div className="card-sm">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-bold text-primary">{formatFileSize(stats.storage)}</span>
              <span className="text-sm text-muted">stored in MinIO metadata</span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${Math.min(100, Math.max(3, stats.storage / 1024 / 1024))}%` }}></div>
            </div>
          </div>
        </div>

        <div>
          <h2 className="section-title">Recent Documents</h2>
          <div className="card">
            {documents.slice(0, 5).map((doc) => (
              <div className="activity-item" key={doc.id}>
                <div className="avatar avatar-blue">{doc.file_name?.charAt(0)?.toUpperCase() || 'D'}</div>
                <div className="activity-text">
                  <strong>{doc.file_name}</strong>
                  <div className="mt-2">
                    <span className="activity-time">{doc.status || 'uploaded'}</span> - <span className="activity-cat">{doc.document_type_name || 'Document'}</span>
                  </div>
                </div>
              </div>
            ))}
            {!isLoading && documents.length === 0 && (
              <div className="empty-state">
                <span className="material-icons">inventory_2</span>
                <div>No documents available for your role yet.</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
