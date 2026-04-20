'use client';

import { useRef, useState } from 'react';
import AppLayout from '../components/AppLayout';
import { api, formatFileSize } from '../lib/api';

const initialForm = {
  branch: '',
  document_type: '',
  hq_id: '',
  unit_id: '',
  branch_id: '',
  min_visible_rank: 6,
};

export default function UploadDocumentsPage() {
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [uploads, setUploads] = useState([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  const updateForm = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const selectFile = (selectedFile) => {
    setFile(selectedFile || null);
    setError('');
  };

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setMessage('');

    if (!file) {
      setError('Please choose a file first');
      return;
    }

    setIsUploading(true);
    try {
      const result = await api.uploadDocument({ ...form, file });
      setUploads((current) => [{ file, result }, ...current]);
      setMessage(`Uploaded ${result.file_name}. Approval: ${result.approved ? 'approved' : 'pending'}`);
      setFile(null);
      setForm(initialForm);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      setError(err.message || 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <AppLayout
      title="Upload Documents"
      subtitle="Upload files to MinIO and trigger the backend OCR workflow."
    >
      {error && <div className="form-error mb-4">{error}</div>}
      {message && <div className="form-success mb-4">{message}</div>}

      <div className="two-col mt-6">
        <div className="flex-col gap-6">
          <div
            className={`drop-zone ${isDragging ? 'dragging' : ''}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              selectFile(event.dataTransfer.files?.[0]);
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              className="hidden-input"
              onChange={(event) => selectFile(event.target.files?.[0])}
            />
            <div className="drop-zone-icon"><span className="material-icons">cloud_upload</span></div>
            <div className="drop-zone-title">{file ? file.name : 'Drag and drop a file here'}</div>
            <div className="drop-zone-sub">
              {file ? `${formatFileSize(file.size)} ready to upload` : 'PDF, image, office, or CSV records supported by your backend storage.'}
            </div>
          </div>

          <div className="card">
            <h2 className="section-title flex items-center gap-2">
              <span className="material-icons text-primary" style={{ fontSize: '20px' }}>edit_note</span>
              Document Information
            </h2>

            <form onSubmit={submit}>
              <div className="form-group">
                <label className="form-label">Branch Name</label>
                <input className="form-input" value={form.branch} onChange={(event) => updateForm('branch', event.target.value)} placeholder="A, Q, G..." required />
              </div>
              <div className="form-group">
                <label className="form-label">Document Type</label>
                <input className="form-input" value={form.document_type} onChange={(event) => updateForm('document_type', event.target.value)} placeholder="ration, training, personnel..." required />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">HQ ID</label>
                  <input type="number" className="form-input" value={form.hq_id} onChange={(event) => updateForm('hq_id', event.target.value)} placeholder="Optional" />
                </div>
                <div className="form-group">
                  <label className="form-label">Unit ID</label>
                  <input type="number" className="form-input" value={form.unit_id} onChange={(event) => updateForm('unit_id', event.target.value)} placeholder="Optional" />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Branch ID</label>
                  <input type="number" className="form-input" value={form.branch_id} onChange={(event) => updateForm('branch_id', event.target.value)} placeholder="Optional" />
                </div>
                <div className="form-group">
                  <label className="form-label">Minimum Visible Rank</label>
                  <input type="number" min="1" max="6" className="form-input" value={form.min_visible_rank} onChange={(event) => updateForm('min_visible_rank', event.target.value)} />
                </div>
              </div>

              <div className="flex justify-end gap-3 mt-6">
                <button type="button" className="btn btn-secondary" onClick={() => { setFile(null); setForm(initialForm); }}>
                  Clear
                </button>
                <button type="submit" className="btn btn-primary" disabled={isUploading}>
                  {isUploading ? 'Uploading...' : 'Upload Document'}
                </button>
              </div>
            </form>
          </div>
        </div>

        <div className="flex-col gap-6">
          <div className="card">
            <h2 className="section-title">Upload Status</h2>
            {uploads.map((item) => (
              <div className="upload-item" key={item.result.doc_id}>
                <div className="file-icon pdf"><span className="material-icons">description</span></div>
                <div className="upload-info">
                  <div className="flex justify-between mb-1">
                    <span className="upload-name">{item.result.file_name}</span>
                    <span className="text-xs font-bold text-primary">100%</span>
                  </div>
                  <div className="progress-track"><div className="progress-fill" style={{ width: '100%' }}></div></div>
                  <div className="upload-size mt-1">{formatFileSize(item.file.size)} - {item.result.approved ? 'Approved' : 'Pending approval'}</div>
                </div>
              </div>
            ))}
            {uploads.length === 0 && (
              <div className="empty-state">
                <span className="material-icons">upload_file</span>
                <div>No uploads in this browser session.</div>
              </div>
            )}
          </div>

          <div className="info-card amber-card">
            <h3 className="info-card-title flex items-center gap-2">
              <span className="material-icons" style={{ fontSize: '18px' }}>rule</span>
              Approval Rules
            </h3>
            <p className="info-card-text">
              Officers and senior clerks are auto-approved. Junior clerk uploads remain pending until an authorized role approves them.
            </p>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
