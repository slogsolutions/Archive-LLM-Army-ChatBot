'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import AppLayout from '../../components/AppLayout';
import { api, formatFileSize } from '../../lib/api';

// Stages in display order
const PIPELINE_STAGES = [
  { key: 'uploaded',    label: 'Uploaded',        icon: 'upload_file' },
  { key: 'approved',    label: 'Approved',         icon: 'verified' },
  { key: 'processing',  label: 'OCR Running',      icon: 'sync' },
  { key: 'processed',   label: 'OCR Complete',     icon: 'text_snippet' },
  { key: 'reviewed',    label: 'Text Reviewed',    icon: 'edit_note' },
  { key: 'indexed',     label: 'Indexed',          icon: 'search' },
];

const STAGE_ORDER = ['uploaded', 'approved', 'processing', 'processed', 'reviewed', 'indexed'];

function stageIndex(status, isApproved) {
  if (!isApproved) return 0;
  const idx = STAGE_ORDER.indexOf(status);
  return idx === -1 ? 1 : Math.max(idx, 1);
}

function PipelineTimeline({ doc }) {
  const current = stageIndex(doc.status, doc.is_approved);
  const isError = doc.status === 'error';
  const isDeleted = doc.is_deleted || doc.status === 'delete_requested' || doc.status === 'deleted';

  return (
    <div className="pipeline-timeline">
      {PIPELINE_STAGES.map((stage, i) => {
        const done = i < current;
        const active = i === current && !isError;
        const isProcessing = stage.key === 'processing' && doc.status === 'processing';

        let stateClass = 'pipeline-step';
        if (done) stateClass += ' pipeline-done';
        else if (active) stateClass += ' pipeline-active';
        else stateClass += ' pipeline-pending';
        if (isError && i === current) stateClass += ' pipeline-error';

        return (
          <div key={stage.key} className="pipeline-step-wrapper">
            <div className={stateClass}>
              <div className="pipeline-icon">
                <span className="material-icons" style={{ fontSize: '16px' }}>
                  {isError && i === current ? 'error' : done ? 'check_circle' : stage.icon}
                </span>
              </div>
              <div className="pipeline-label">
                {isProcessing ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span className="pipeline-spinner" /> OCR Running…
                  </span>
                ) : stage.label}
              </div>
            </div>
            {i < PIPELINE_STAGES.length - 1 && (
              <div className={`pipeline-connector ${done ? 'pipeline-connector-done' : ''}`} />
            )}
          </div>
        );
      })}

      {isError && (
        <div className="pipeline-error-msg">
          <span className="material-icons" style={{ fontSize: '14px' }}>warning</span>
          OCR failed — use Re-queue OCR to retry
        </div>
      )}
      {doc.status === 'rejected' && (
        <div className="pipeline-error-msg" style={{ color: 'var(--color-danger)' }}>
          <span className="material-icons" style={{ fontSize: '14px' }}>cancel</span>
          Rejected{doc.rejector_name ? ` by ${doc.rejector_name}` : ''}
          {doc.rejection_reason && ` — ${doc.rejection_reason}`}
        </div>
      )}
      {isDeleted && (
        <div className="pipeline-error-msg" style={{ color: 'var(--color-danger)' }}>
          <span className="material-icons" style={{ fontSize: '14px' }}>delete</span>
          {doc.status === 'delete_requested' ? 'Deletion pending approval' : 'Document deleted'}
        </div>
      )}
    </div>
  );
}

const ACTIVE_STATUSES = new Set(['processing', 'uploaded']);
// Statuses where the "Index Corrected Text" action is valid
const CAN_INDEX_TEXT_STATUSES = new Set(['processed', 'reviewed', 'error']);

export default function PreviewEditPage() {
  const params = useParams();
  const id = params?.id;

  const user = api.getUser();
  const canApprove = user && ['officer', 'unit_admin', 'hq_admin', 'super_admin'].includes(user.role);
  const canEditText = user && ['officer', 'clerk'].includes(user.role);
  const canReindex = user && ['officer', 'unit_admin', 'hq_admin', 'super_admin'].includes(user.role);
  const canDirectDelete = user && (user.role === 'officer' || (user.role === 'clerk' && user.clerk_type === 'senior'));
  const canRequestDelete = user && user.role === 'clerk' && user.clerk_type === 'junior';
  const canApproveDelete = user && ['officer', 'unit_admin', 'hq_admin', 'super_admin'].includes(user.role);

  const [document, setDocument] = useState(null);
  const [text, setText] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isActing, setIsActing] = useState(false);
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const pollRef = useRef(null);

  const loadDocument = async (silent = false) => {
    if (!silent) setError('');
    if (!silent) setIsLoading(true);
    try {
      const data = await api.getDocument(id);
      setDocument(data);
      setText(data.corrected_text || data.ocr_text || '');
      return data;
    } catch (err) {
      if (!silent) setError(err.message || 'Unable to load document');
    } finally {
      if (!silent) setIsLoading(false);
    }
  };

  const startPolling = (doc) => {
    stopPolling();
    if (doc && ACTIVE_STATUSES.has(doc.status)) {
      pollRef.current = setInterval(async () => {
        const fresh = await loadDocument(true);
        if (fresh && !ACTIVE_STATUSES.has(fresh.status)) {
          stopPolling();
        }
      }, 5000);
    }
  };

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => {
    if (id) {
      loadDocument().then((doc) => startPolling(doc));
    }
    return stopPolling;
  }, [id]);

  useEffect(() => {
    if (document) startPolling(document);
  }, [document?.status, document?.is_approved]);

  const act = (label, fn) => async () => {
    setMessage('');
    setError('');
    setIsActing(true);
    try {
      const result = await fn();
      setMessage(result?.message || label);
      const fresh = await loadDocument(true);
      startPolling(fresh);
    } catch (err) {
      setError(err.message || `${label} failed`);
    } finally {
      setIsActing(false);
    }
  };

  const approve = act('Document approved', async () => {
    const result = await api.approveDocument(id);
    setShowRejectInput(false);
    return result;
  });

  const submitReject = act('Document rejected', async () => {
    if (!rejectReason.trim()) throw new Error('Rejection reason is required');
    const result = await api.rejectDocument(id, rejectReason.trim());
    setRejectReason('');
    setShowRejectInput(false);
    return result;
  });
  const approveDelete = act('Delete approved', () => api.approveDelete(id));
  const requestDelete = act('Delete request submitted', () => api.requestDelete(id));
  const directDelete = act('Document deleted', () => api.requestDelete(id));
  const reindex = act('Re-queued for OCR', () => api.reindexDocument(id));
  const indexText = act('Queued for indexing', () => api.indexDocumentText(id));

  const download = async () => {
    setMessage('');
    setError('');
    try {
      await api.downloadDocument(id, document?.file_name);
    } catch (err) {
      setError(err.message || 'Download failed');
    }
  };

  const saveText = async (event) => {
    event.preventDefault();
    setMessage('');
    setError('');
    setIsSaving(true);
    try {
      await api.updateDocumentText(id, text);
      setMessage('OCR text saved');
      await loadDocument(true);
    } catch (err) {
      setError(err.message || 'Unable to save OCR text');
    } finally {
      setIsSaving(false);
    }
  };

  const doc = document;

  return (
    <AppLayout
      title="Preview & Edit"
      subtitle="Document metadata, OCR review, approval, and download"
      actions={
        <Link href="/archive" className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '8px', textDecoration: 'none' }}>
          <span className="material-icons">arrow_back</span>
          Back
        </Link>
      }
    >
      {error && <div className="form-error mb-4">{error}</div>}
      {message && <div className="form-success mb-4">{message}</div>}

      {isLoading && <div className="card">Loading document...</div>}

      {!isLoading && doc && (
        <>
          {/* OCR pipeline timeline — full width above the two-col */}
          <div className="card mt-4 mb-4" style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <h2 className="section-title" style={{ margin: 0 }}>Processing Pipeline</h2>
              {ACTIVE_STATUSES.has(doc.status) && (
                <span style={{ fontSize: '12px', color: 'var(--color-primary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span className="pipeline-spinner" /> Auto-refreshing…
                </span>
              )}
              {!doc.is_approved && !ACTIVE_STATUSES.has(doc.status) && (
                <span style={{ fontSize: '12px', color: 'var(--color-warning)' }}>
                  Waiting for officer approval
                </span>
              )}
            </div>
            <PipelineTimeline doc={doc} />
            <div style={{ marginTop: '12px', fontSize: '12px', color: 'var(--color-muted)' }}>
              Uploaded by <strong>{doc.uploader_name || `User #${doc.uploaded_by || '—'}`}</strong>
              {doc.approver_name && <> · Approved by <strong>{doc.approver_name}</strong></>}
              {doc.created_at && <> · {new Date(doc.created_at).toLocaleString()}</>}
            </div>
          </div>

          <div className="two-col">
            {/* Left panel – OCR preview */}
            <div className="doc-preview">
              <span className="doc-preview-tag">{doc.document_type_name || 'Document'}</span>
              <h1 className="doc-preview-title">{doc.file_name}</h1>

              <div className="doc-stat-row">
                <div className="doc-stat-item px-4">
                  <label>Status</label>
                  <span>{doc.is_approved ? doc.status || 'approved' : 'pending approval'}</span>
                </div>
                <div className="doc-stat-item px-4">
                  <label>Size</label>
                  <span>{formatFileSize(doc.file_size)}</span>
                </div>
                {doc.year && (
                  <div className="doc-stat-item px-4">
                    <label>Year</label>
                    <span>{doc.year}</span>
                  </div>
                )}
                {doc.version > 1 && (
                  <div className="doc-stat-item px-4">
                    <label>Version</label>
                    <span>v{doc.version}</span>
                  </div>
                )}
              </div>

              <div className="doc-preview-body">
                {text ? (
                  text.split('\n').map((line, index) => (
                    <p key={`${index}`}>{line || '\u00A0'}</p>
                  ))
                ) : (
                  <p className="text-muted">
                    {!doc.is_approved
                      ? 'OCR will begin after an officer approves this document.'
                      : doc.status === 'uploaded'
                      ? 'Document is queued — waiting for the OCR worker to pick it up.'
                      : doc.status === 'processing'
                      ? 'OCR is running, text will appear here shortly…'
                      : doc.status === 'error'
                      ? 'OCR failed. Use Re-queue OCR to retry with this document.'
                      : 'No OCR text extracted.'}
                  </p>
                )}
              </div>
            </div>

            {/* Right panel – metadata + actions */}
            <div className="card">
              <h2 className="section-title">Document Metadata</h2>
              <div className="metadata-list mb-6">
                <div><strong>ID</strong><span>#{doc.id}</span></div>
                <div><strong>HQ</strong><span>{doc.hq_name || doc.hq_id || '-'}</span></div>
                <div><strong>Unit</strong><span>{doc.unit_name || doc.unit_id || '-'}</span></div>
                <div><strong>Branch</strong><span>{doc.branch_name || '-'}</span></div>
                <div><strong>Type</strong><span>{doc.document_type_name || '-'}</span></div>
                {doc.section && <div><strong>Section</strong><span>{doc.section}</span></div>}
                {doc.year && <div><strong>Year</strong><span>{doc.year}</span></div>}
                <div><strong>Visible Rank</strong><span>{doc.min_visible_rank || 6}+</span></div>
                <div><strong>Uploaded</strong><span>{doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '-'}</span></div>
              </div>

              {/* Rejection info */}
              {doc.status === 'rejected' && (
                <div className="info-card mb-4" style={{ borderLeft: '4px solid var(--color-danger)' }}>
                  <p className="info-card-text" style={{ margin: 0, color: 'var(--color-danger)' }}>
                    <strong>Rejected</strong>{doc.rejector_name ? ` by ${doc.rejector_name}` : ''}
                  </p>
                  {doc.rejection_reason && (
                    <p className="info-card-text" style={{ margin: '6px 0 0' }}>
                      Reason: <em>{doc.rejection_reason}</em>
                    </p>
                  )}
                </div>
              )}

              {/* Approval info */}
              {doc.is_approved && doc.approver_name && (
                <div className="info-card mb-4" style={{ borderLeft: '4px solid var(--color-success, #16a34a)' }}>
                  <p className="info-card-text" style={{ margin: 0 }}>
                    <strong>Approved</strong> by {doc.approver_name}
                  </p>
                </div>
              )}

              {/* Pending approval alert */}
              {!doc.is_approved && doc.status !== 'rejected' && (
                <div className="info-card amber-card mb-4">
                  <p className="info-card-text" style={{ margin: 0 }}>
                    This document is <strong>pending officer approval</strong>. OCR processing will begin after approval.
                  </p>
                </div>
              )}

              {/* Inline reject reason input */}
              {showRejectInput && (
                <div className="mb-4" style={{ border: '1px solid var(--color-danger)', borderRadius: '8px', padding: '12px' }}>
                  <label className="form-label" style={{ color: 'var(--color-danger)' }}>Rejection Reason</label>
                  <textarea
                    className="form-textarea"
                    rows={3}
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Enter reason for rejection..."
                  />
                  <div className="flex gap-2 mt-2">
                    <button
                      type="button"
                      className="btn btn-sm"
                      style={{ background: 'var(--color-danger)', color: '#fff' }}
                      onClick={submitReject}
                      disabled={isActing || !rejectReason.trim()}
                    >
                      Confirm Reject
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-secondary"
                      onClick={() => { setShowRejectInput(false); setRejectReason(''); }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* Delete request alert */}
              {doc.delete_requested && (
                <div className="info-card mb-4" style={{ borderLeft: '4px solid var(--color-danger)' }}>
                  <p className="info-card-text" style={{ margin: 0 }}>
                    A <strong>delete request</strong> has been submitted for this document.
                  </p>
                </div>
              )}

              {/* Action buttons */}
              <div className="review-actions mb-4">
                <button
                  type="button"
                  className="review-btn review-btn-reject"
                  onClick={download}
                  disabled={isActing}
                >
                  <span className="material-icons">download</span>
                  Download
                </button>

                {canApprove && !doc.is_approved && doc.status !== 'rejected' && (
                  <button
                    type="button"
                    className="review-btn review-btn-approve"
                    onClick={approve}
                    disabled={isActing}
                  >
                    <span className="material-icons">check_circle</span>
                    Approve
                  </button>
                )}

                {canApprove && !doc.is_approved && doc.status !== 'rejected' && (
                  <button
                    type="button"
                    className="review-btn review-btn-reject"
                    style={{ background: 'var(--color-danger)', color: '#fff' }}
                    onClick={() => setShowRejectInput((v) => !v)}
                    disabled={isActing}
                  >
                    <span className="material-icons">cancel</span>
                    Reject
                  </button>
                )}

                {canApprove && doc.status === 'rejected' && (
                  <button
                    type="button"
                    className="review-btn review-btn-approve"
                    onClick={approve}
                    disabled={isActing}
                  >
                    <span className="material-icons">check_circle</span>
                    Approve Anyway
                  </button>
                )}

                {canApproveDelete && doc.delete_requested && (
                  <button
                    type="button"
                    className="review-btn"
                    style={{ background: 'var(--color-danger)', color: '#fff' }}
                    onClick={approveDelete}
                    disabled={isActing}
                  >
                    <span className="material-icons">delete_forever</span>
                    Approve Delete
                  </button>
                )}

                {canDirectDelete && !doc.delete_requested && !doc.is_deleted && (
                  <button
                    type="button"
                    className="review-btn"
                    style={{ background: 'var(--color-danger)', color: '#fff' }}
                    onClick={directDelete}
                    disabled={isActing}
                  >
                    <span className="material-icons">delete</span>
                    Delete
                  </button>
                )}

                {canRequestDelete && !doc.delete_requested && !doc.is_deleted && (
                  <button
                    type="button"
                    className="review-btn"
                    style={{ background: 'var(--color-warning)', color: '#fff' }}
                    onClick={requestDelete}
                    disabled={isActing}
                  >
                    <span className="material-icons">delete_outline</span>
                    Request Delete
                  </button>
                )}

                {canReindex && !doc.is_deleted && (
                  <button
                    type="button"
                    className="review-btn"
                    style={{ background: 'var(--color-primary)', color: '#fff' }}
                    onClick={reindex}
                    disabled={isActing || doc.status === 'processing'}
                    title={!doc.is_approved ? 'Approve and queue for OCR' : doc.status === 'error' ? 'Retry OCR processing' : 'Re-run OCR from scratch'}
                  >
                    <span className="material-icons">sync</span>
                    {!doc.is_approved ? 'Approve & Queue OCR' : doc.status === 'error' ? 'Retry OCR' : 'Re-run OCR'}
                  </button>
                )}

                {canEditText && doc.is_approved && CAN_INDEX_TEXT_STATUSES.has(doc.status) && !doc.is_deleted && (
                  <button
                    type="button"
                    className="review-btn"
                    style={{ background: 'var(--color-success, #16a34a)', color: '#fff' }}
                    onClick={indexText}
                    disabled={isActing}
                    title="Index the current corrected text into Elasticsearch (does not re-run OCR)"
                  >
                    <span className="material-icons">library_add</span>
                    Index Text
                  </button>
                )}
              </div>

              {/* OCR text editor */}
              {canEditText && (
                <form onSubmit={saveText}>
                  <div className="divider"></div>
                  <div className="form-group">
                    <label className="form-label">OCR / Corrected Text</label>
                    <textarea
                      className="form-textarea ocr-textarea"
                      value={text}
                      onChange={(event) => setText(event.target.value)}
                      placeholder="OCR text will appear here after processing. Correct errors here, save, then click Index Text to update the search index."
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary w-full mt-4"
                    style={{ justifyContent: 'center' }}
                    disabled={isSaving}
                  >
                    {isSaving ? 'Saving...' : 'Save Corrected Text'}
                  </button>
                  {doc.is_approved && (doc.ocr_text || doc.corrected_text) && (
                    <p style={{ fontSize: '12px', color: 'var(--color-muted)', marginTop: '8px', textAlign: 'center' }}>
                      After saving, click <strong>Index Text</strong> above to update the search index with your corrections.
                    </p>
                  )}
                </form>
              )}
            </div>
          </div>
        </>
      )}
    </AppLayout>
  );
}
