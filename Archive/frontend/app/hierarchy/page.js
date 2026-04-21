'use client';

import { useEffect, useMemo, useState } from 'react';
import AppLayout from '../components/AppLayout';
import { api } from '../lib/api';

const emptyForm = {
  hqName: '',
  unitName: '',
  unitHqId: '',
  branchName: '',
  branchDescription: '',
  branchUnitId: '',
};

export default function HierarchyPage() {
  const [hqs, setHqs] = useState([]);
  const [units, setUnits] = useState([]);
  const [branches, setBranches] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState({ type: '', id: null });
  const [activeHqId, setActiveHqId] = useState('');
  const [activeUnitId, setActiveUnitId] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const loadHierarchy = async () => {
    setError('');

    try {
      const [hqList, unitList, branchList] = await Promise.all([
        api.listHq(),
        api.listUnits(),
        api.listBranches(),
      ]);

      setHqs(Array.isArray(hqList) ? hqList : []);
      setUnits(Array.isArray(unitList) ? unitList : []);
      setBranches(Array.isArray(branchList) ? branchList : []);
    } catch (err) {
      setError(err.message || 'Unable to load hierarchy');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadHierarchy();
  }, []);

  const visibleUnits = useMemo(() => {
    const id = Number(activeHqId);
    return id ? units.filter((unit) => unit.hq_id === id) : units;
  }, [activeHqId, units]);

  const visibleBranches = useMemo(() => {
    const id = Number(activeUnitId);
    return id ? branches.filter((branch) => branch.unit_id === id) : branches;
  }, [activeUnitId, branches]);

  const unitChoicesForBranch = useMemo(() => {
    const hqId = Number(form.unitHqId || activeHqId);
    return hqId ? units.filter((unit) => unit.hq_id === hqId) : units;
  }, [activeHqId, form.unitHqId, units]);

  const updateForm = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const createHq = async (event) => {
    event.preventDefault();
    setMessage('');
    setError('');

    try {
      if (editing.type === 'hq') {
        await api.updateHq(editing.id, { name: form.hqName });
        setMessage('HQ updated');
      } else {
        await api.createHq({ name: form.hqName });
        setMessage('HQ created');
      }
      setForm((current) => ({ ...current, hqName: '' }));
      setEditing({ type: '', id: null });
      await loadHierarchy();
    } catch (err) {
      setError(err.message || 'HQ creation failed');
    }
  };

  const createUnit = async (event) => {
    event.preventDefault();
    setMessage('');
    setError('');

    try {
      const payload = { name: form.unitName, hq_id: Number(form.unitHqId) };
      if (editing.type === 'unit') {
        await api.updateUnit(editing.id, payload);
        setMessage('Unit updated');
      } else {
        await api.createUnit(payload);
        setMessage('Unit created and linked to HQ');
      }
      setForm((current) => ({ ...current, unitName: '', unitHqId: '' }));
      setEditing({ type: '', id: null });
      await loadHierarchy();
    } catch (err) {
      setError(err.message || 'Unit creation failed');
    }
  };

  const createBranch = async (event) => {
    event.preventDefault();
    setMessage('');
    setError('');

    try {
      const payload = {
        name: form.branchName,
        description: form.branchDescription,
        unit_id: Number(form.branchUnitId),
      };

      if (editing.type === 'branch') {
        await api.updateBranch(editing.id, payload);
        setMessage('Branch updated');
      } else {
        await api.createBranch(payload);
        setMessage('Branch created and linked to Unit');
      }
      setForm((current) => ({ ...current, branchName: '', branchDescription: '', branchUnitId: '' }));
      setEditing({ type: '', id: null });
      await loadHierarchy();
    } catch (err) {
      setError(err.message || 'Branch creation failed');
    }
  };

  const editHq = (hq) => {
    setEditing({ type: 'hq', id: hq.id });
    setForm((current) => ({ ...current, hqName: hq.name }));
  };

  const editUnit = (unit) => {
    setEditing({ type: 'unit', id: unit.id });
    setForm((current) => ({ ...current, unitName: unit.name, unitHqId: unit.hq_id || '' }));
  };

  const editBranch = (branch) => {
    setEditing({ type: 'branch', id: branch.id });
    setForm((current) => ({
      ...current,
      branchName: branch.name,
      branchDescription: branch.description || '',
      branchUnitId: branch.unit_id || '',
    }));
  };

  const clearEdit = () => {
    setEditing({ type: '', id: null });
    setForm(emptyForm);
  };

  const removeItem = async (type, id) => {
    setMessage('');
    setError('');

    try {
      if (type === 'hq') await api.deleteHq(id);
      if (type === 'unit') await api.deleteUnit(id);
      if (type === 'branch') await api.deleteBranch(id);
      setMessage(`${type.toUpperCase()} deleted`);
      clearEdit();
      await loadHierarchy();
    } catch (err) {
      setError(err.message || 'Delete failed');
    }
  };

  return (
    <AppLayout title="Hierarchy" subtitle="Create and inspect the HQ, Unit, and Branch structure used by RBAC.">
      {error && <div className="form-error mb-4">{error}</div>}
      {message && <div className="form-success mb-4">{message}</div>}

      <div className="hierarchy-grid">
        <div className="card animated-panel">
          <h2 className="section-title">{editing.type === 'hq' ? 'Edit Headquarter' : 'Create Headquarter'}</h2>
          <form onSubmit={createHq}>
            <div className="form-group">
              <label className="form-label">HQ Name</label>
              <input className="form-input" value={form.hqName} onChange={(event) => updateForm('hqName', event.target.value)} placeholder="2STC" required />
            </div>
            <div className="form-actions">
              {editing.type === 'hq' && <button type="button" className="btn btn-secondary" onClick={clearEdit}>Cancel</button>}
              <button className="btn btn-primary" style={{ justifyContent: 'center' }}>{editing.type === 'hq' ? 'Update HQ' : 'Add HQ'}</button>
            </div>
          </form>
        </div>

        <div className="card animated-panel">
          <h2 className="section-title">{editing.type === 'unit' ? 'Edit Unit' : 'Create Unit'}</h2>
          <form onSubmit={createUnit}>
            <div className="form-group">
              <label className="form-label">Parent HQ</label>
              <select className="form-select" value={form.unitHqId} onChange={(event) => updateForm('unitHqId', event.target.value)} required>
                <option value="">Select HQ...</option>
                {hqs.map((hq) => <option key={hq.id} value={hq.id}>{hq.name}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Unit Name</label>
              <input className="form-input" value={form.unitName} onChange={(event) => updateForm('unitName', event.target.value)} placeholder="3TTR" required />
            </div>
            <div className="form-actions">
              {editing.type === 'unit' && <button type="button" className="btn btn-secondary" onClick={clearEdit}>Cancel</button>}
              <button className="btn btn-primary" style={{ justifyContent: 'center' }}>{editing.type === 'unit' ? 'Update Unit' : 'Add Unit'}</button>
            </div>
          </form>
        </div>

        <div className="card animated-panel">
          <h2 className="section-title">{editing.type === 'branch' ? 'Edit Branch' : 'Create Branch'}</h2>
          <form onSubmit={createBranch}>
            <div className="form-group">
              <label className="form-label">Parent Unit</label>
              <select className="form-select" value={form.branchUnitId} onChange={(event) => updateForm('branchUnitId', event.target.value)} required>
                <option value="">Select Unit...</option>
                {unitChoicesForBranch.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}
              </select>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Branch Name</label>
                <input className="form-input" value={form.branchName} onChange={(event) => updateForm('branchName', event.target.value)} placeholder="A" required />
              </div>
              <div className="form-group">
                <label className="form-label">Description</label>
                <input className="form-input" value={form.branchDescription} onChange={(event) => updateForm('branchDescription', event.target.value)} placeholder="Admin Branch" />
              </div>
            </div>
            <div className="form-actions">
              {editing.type === 'branch' && <button type="button" className="btn btn-secondary" onClick={clearEdit}>Cancel</button>}
              <button className="btn btn-primary" style={{ justifyContent: 'center' }}>{editing.type === 'branch' ? 'Update Branch' : 'Add Branch'}</button>
            </div>
          </form>
        </div>
      </div>

      <div className="hierarchy-browser animated-panel">
        <div className="hierarchy-column">
          <div className="hierarchy-header">
            <span>Headquarters</span>
            <strong>{isLoading ? '...' : hqs.length}</strong>
          </div>
          {hqs.map((hq) => (
            <div
              key={hq.id}
              className={`hierarchy-node ${Number(activeHqId) === hq.id ? 'active' : ''}`}
            >
              <button className="hierarchy-node-main" onClick={() => { setActiveHqId(String(hq.id)); setActiveUnitId(''); }}>
                <span>{hq.name}</span>
                <small>ID {hq.id}</small>
              </button>
              <div className="node-actions">
                <button type="button" className="node-action" onClick={() => editHq(hq)}>Edit</button>
                <button type="button" className="node-action danger" onClick={() => removeItem('hq', hq.id)}>Delete</button>
              </div>
            </div>
          ))}
        </div>

        <div className="hierarchy-column">
          <div className="hierarchy-header">
            <span>Units</span>
            <strong>{visibleUnits.length}</strong>
          </div>
          {visibleUnits.map((unit) => (
            <div
              key={unit.id}
              className={`hierarchy-node ${Number(activeUnitId) === unit.id ? 'active' : ''}`}
            >
              <button className="hierarchy-node-main" onClick={() => setActiveUnitId(String(unit.id))}>
                <span>{unit.name}</span>
                <small>{hqs.find((h) => h.id === unit.hq_id)?.name || `HQ ${unit.hq_id}`}</small>
              </button>
              <div className="node-actions">
                <button type="button" className="node-action" onClick={() => editUnit(unit)}>Edit</button>
                <button type="button" className="node-action danger" onClick={() => removeItem('unit', unit.id)}>Delete</button>
              </div>
            </div>
          ))}
        </div>

        <div className="hierarchy-column">
          <div className="hierarchy-header">
            <span>Branches</span>
            <strong>{visibleBranches.length}</strong>
          </div>
          {visibleBranches.map((branch) => (
            <div key={branch.id} className="hierarchy-node static">
              <div className="hierarchy-node-main">
                <span>{branch.name}</span>
                <small>{branch.description || units.find((u) => u.id === branch.unit_id)?.name || `Unit ${branch.unit_id}`}</small>
              </div>
              <div className="node-actions">
                <button type="button" className="node-action" onClick={() => editBranch(branch)}>Edit</button>
                <button type="button" className="node-action danger" onClick={() => removeItem('branch', branch.id)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppLayout>
  );
}
