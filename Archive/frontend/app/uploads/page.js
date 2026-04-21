'use client';

import { useEffect, useRef, useState } from 'react';
import AppLayout from '../components/AppLayout';
import { api, formatFileSize } from '../lib/api';

const initialForm = {
  branch: '',
  document_type: '',
  hq_id: '',
  unit_id: '',
  branch_id: '',
  section: '',
  year: new Date().getFullYear(),
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

  // Hierarchy data
  const [hqs, setHqs] = useState([]);
  const [units, setUnits] = useState([]);
  const [branches, setBranches] = useState([]);
  const [hierarchyLoading, setHierarchyLoading] = useState(true);

  // Cascading filters
  const selectedHqId = Number(form.hq_id) || null;
  const selectedUnitId = Number(form.unit_id) || null;
  const filteredUnits = selectedHqId ? units.filter((u) => u.hq_id === selectedHqId) : units;
  const filteredBranches = selectedUnitId ? branches.filter((b) => b.unit_id === selectedUnitId) : branches;

  useEffect(() => {
    const user = api.getUser();

    Promise.all([api.listHq(), api.listUnits(), api.listBranches()])
      .then(([hqList, unitList, branchList]) => {
        setHqs(Array.isArray(hqList) ? hqList : []);
        setUnits(Array.isArray(unitList) ? unitList : []);
        setBranches(Array.isArray(branchList) ? branchList : []);

        // Pre-fill user's own hierarchy scope
        if (user) {
          setForm((current) => ({
            ...current,
            hq_id: user.hq_id ? String(user.hq_id) : current.hq_id,
            unit_id: user.unit_id ? String(user.unit_id) : current.unit_id,
            branch_id: user.branch_id ? String(user.branch_id) : current.branch_id,
          }));
        }
      })
      .catch(() => {/* hierarchy load failure is non-fatal */})
      .finally(() => setHierarchyLoading(false));
  }, []);

  const updateForm = (key, value) => {
    setForm((current) => {
      const next = { ...current, [key]: value };
      if (key === 'hq_id') { next.unit_id = ''; next.branch_id = ''; }
      if (key === 'unit_id') { next.branch_id = ''; }
      return next;
    });
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
      const payload = {
        ...form,
        file,
        year: form.year ? Number(form.year) : undefined,
        min_visible_rank: Number(form.min_visible_rank),
      };

      // Resolve branch name from selected branch_id when branch text field is empty
      if (!payload.branch && payload.branch_id) {
        const found = branches.find((b) => b.id === Number(payload.branch_id));
        if (found) payload.branch = found.name;
      }

      const result = await api.uploadDocument(payload);
      setUploads((current) => [{ file, result }, ...current]);
      setMessage(result.message || `Uploaded ${result.file_name}`);
      setFile(null);
      setForm((current) => ({ ...initialForm, hq_id: current.hq_id, unit_id: current.unit_id }));
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
              {file ? `${formatFileSize(file.size)} ready to upload` : 'PDF, image, office, or CSV files supported.'}
            </div>
          </div>

          <div className="card">
            <h2 className="section-title flex items-center gap-2">
              <span className="material-icons text-primary" style={{ fontSize: '20px' }}>edit_note</span>
              Document Information
            </h2>

            <form onSubmit={submit}>
              {/* Hierarchy scope */}
              <div className="form-group">
                <label className="form-label">Headquarter</label>
                <select
                  className="form-select"
                  value={form.hq_id}
                  onChange={(event) => updateForm('hq_id', event.target.value)}
                  disabled={hierarchyLoading}
                >
                  <option value="">Select HQ...</option>
                  {hqs.map((hq) => <option key={hq.id} value={hq.id}>{hq.name}</option>)}
                </select>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Unit</label>
                  <select
                    className="form-select"
                    value={form.unit_id}
                    onChange={(event) => updateForm('unit_id', event.target.value)}
                    disabled={!form.hq_id || hierarchyLoading}
                  >
                    <option value="">Select Unit...</option>
                    {filteredUnits.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Branch</label>
                  <select
                    className="form-select"
                    value={form.branch_id}
                    onChange={(event) => {
                      updateForm('branch_id', event.target.value);
                      const found = branches.find((b) => b.id === Number(event.target.value));
                      if (found) updateForm('branch', found.name);
                    }}
                    disabled={!form.unit_id || hierarchyLoading}
                  >
                    <option value="">Select Branch...</option>
                    {filteredBranches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </div>
              </div>

              {/* Document details */}
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Branch Label <span className="text-xs text-muted">(auto-filled)</span></label>
                  <input
                    className="form-input"
                    value={form.branch}
                    onChange={(event) => updateForm('branch', event.target.value)}
                    placeholder="A, Q, G..."
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Document Type</label>
                  <input
                    className="form-input"
                    value={form.document_type}
                    onChange={(event) => updateForm('document_type', event.target.value)}
                    placeholder="ration, training, personnel..."
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Section</label>
                  <input
                    className="form-input"
                    value={form.section}
                    onChange={(event) => updateForm('section', event.target.value)}
                    placeholder="e.g. Part-I, Part-II"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Year</label>
                  <input
                    type="number"
                    min="2000"
                    max="2100"
                    className="form-input"
                    value={form.year}
                    onChange={(event) => updateForm('year', event.target.value)}
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Minimum Visible Rank</label>
                <select
                  className="form-select"
                  value={form.min_visible_rank}
                  onChange={(event) => updateForm('min_visible_rank', event.target.value)}
                >
                  <option value={1}>1 - Super Admin only</option>
                  <option value={2}>2 - HQ Admin+</option>
                  <option value={3}>3 - Unit Admin+</option>
                  <option value={4}>4 - Officer+</option>
                  <option value={5}>5 - Clerk+</option>
                  <option value={6}>6 - All (including Trainee)</option>
                </select>
              </div>

              <div className="flex justify-end gap-3 mt-6">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => { setFile(null); setForm(initialForm); }}
                >
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
            {uploads.map((item, idx) => (
              <div className="upload-item" key={idx} style={{ overflow: 'hidden' }}>
                <div className="file-icon pdf" style={{ flexShrink: 0 }}><span className="material-icons">description</span></div>
                <div className="upload-info" style={{ minWidth: 0, flex: 1 }}>
                  <div className="flex justify-between mb-1" style={{ gap: '8px' }}>
                    <span
                      className="upload-name"
                      style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}
                      title={item.result.file_name}
                    >
                      {item.result.file_name}
                    </span>
                    <span className="text-xs font-bold text-primary" style={{ flexShrink: 0 }}>100%</span>
                  </div>
                  <div className="progress-track"><div className="progress-fill" style={{ width: '100%' }}></div></div>
                  <div className="upload-size mt-1">
                    {formatFileSize(item.file.size)} &mdash; {item.result.approved ? 'Approved & queued for OCR' : 'Pending officer approval'}
                  </div>
                </div>
              </div>
            ))}
            {uploads.length === 0 && (
              <div className="empty-state">
                <span className="material-icons">upload_file</span>
                <div>No uploads in this session.</div>
              </div>
            )}
          </div>

          <div className="info-card amber-card">
            <h3 className="info-card-title flex items-center gap-2">
              <span className="material-icons" style={{ fontSize: '18px' }}>rule</span>
              Approval Rules
            </h3>
            <p className="info-card-text">
              Officer and senior clerk uploads are auto-approved and immediately queued for OCR. Junior clerk uploads wait for an officer to approve before any processing begins.
            </p>
          </div>

          <div className="info-card">
            <h3 className="info-card-title">Supported Formats</h3>
            <p className="info-card-text">PDF, JPG/PNG (OCR), DOCX, XLSX, CSV, PPTX, TXT — max 20 MB per file.</p>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
