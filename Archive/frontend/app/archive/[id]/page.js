'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import AppLayout from '../../components/AppLayout';
import { api, formatFileSize } from '../../lib/api';

export default function PreviewEditPage() {
  const params = useParams();
  const id = params?.id;
  const [document, setDocument] = useState(null);
  const [text, setText] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const loadDocument = async () => {
    setError('');
    setIsLoading(true);

    try {
      const data = await api.getDocument(id);
      setDocument(data);
      setText(data.corrected_text || data.ocr_text || '');
    } catch (err) {
      setError(err.message || 'Unable to load document');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (id) loadDocument();
  }, [id]);

  const approve = async () => {
    setMessage('');
    setError('');

    try {
      await api.approveDocument(id);
      setMessage('Document approved');
      await loadDocument();
    } catch (err) {
      setError(err.message || 'Unable to approve document');
    }
  };

  const saveText = async (event) => {
    event.preventDefault();
    setMessage('');
    setError('');
    setIsSaving(true);

    try {
      await api.updateDocumentText(id, text);
      setMessage('OCR text updated');
      await loadDocument();
    } catch (err) {
      setError(err.message || 'Unable to update OCR text');
    } finally {
      setIsSaving(false);
    }
  };

  const download = async () => {
    setMessage('');
    setError('');

    try {
      await api.downloadDocument(id, document?.file_name);
    } catch (err) {
      setError(err.message || 'Unable to download document');
    }
  };

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

      {!isLoading && document && (
        <div className="two-col mt-4">
          <div className="doc-preview">
            <span className="doc-preview-tag">{document.document_type_name || 'Document'}</span>
            <h1 className="doc-preview-title">{document.file_name}</h1>

            <div className="doc-stat-row">
              <div className="doc-stat-item px-4">
                <label>Status</label>
                <span>{document.is_approved ? document.status || 'approved' : 'pending'}</span>
              </div>
              <div className="doc-stat-item px-4">
                <label>Size</label>
                <span>{formatFileSize(document.file_size)}</span>
              </div>
            </div>

            <div className="doc-preview-body">
              {text ? (
                text.split('\n').map((line, index) => <p key={`${line}-${index}`}>{line || ' '}</p>)
              ) : (
                <p>OCR text has not been generated yet. The backend worker will fill this after processing.</p>
              )}
            </div>

            <div className="signature-block">
              Uploaded by user ID
              <strong>{document.uploaded_by || '-'}</strong>
            </div>
          </div>

          <div className="card">
            <h2 className="section-title">Document Metadata</h2>
            <div className="metadata-list mb-6">
              <div><strong>ID</strong><span>{document.id}</span></div>
              <div><strong>Branch</strong><span>{document.branch_name || '-'}</span></div>
              <div><strong>HQ</strong><span>{document.hq_id || '-'}</span></div>
              <div><strong>Unit</strong><span>{document.unit_id || '-'}</span></div>
              <div><strong>Visible Rank</strong><span>{document.min_visible_rank || 6}</span></div>
            </div>

            <form onSubmit={saveText}>
              <div className="form-group">
                <label className="form-label">OCR / Corrected Text</label>
                <textarea
                  className="form-textarea ocr-textarea"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="OCR text will appear here after processing."
                />
              </div>

              <div className="divider"></div>

              <div className="review-actions">
                <button type="button" className="review-btn review-btn-reject" onClick={download}>
                  <span className="material-icons">download</span>
                  Download
                </button>
                <button type="button" className="review-btn review-btn-approve" onClick={approve}>
                  <span className="material-icons">check</span>
                  Approve
                </button>
              </div>

              <button type="submit" className="btn btn-primary w-full mt-4" style={{ justifyContent: 'center' }} disabled={isSaving}>
                {isSaving ? 'Saving...' : 'Save OCR Text'}
              </button>
            </form>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
