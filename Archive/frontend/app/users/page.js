'use client';

import { useEffect, useMemo, useState } from 'react';
import AppLayout from '../components/AppLayout';
import { api, formatRole } from '../lib/api';

const emptyUser = {
  email: '',
  password: '123',
  role: 'trainee',
  rank_level: 6,
  hq_id: '',
  unit_id: '',
  branch_id: '',
  clerk_type: 'junior',
  task_category: '',
};

const emptyStructure = {
  hqName: '',
  unitName: '',
  unitHqId: '',
  branchName: '',
  branchDescription: '',
  branchUnitId: '',
};

export default function UserManagementPage() {
  const [users, setUsers] = useState([]);
  const [userForm, setUserForm] = useState(emptyUser);
  const [structureForm, setStructureForm] = useState(emptyStructure);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const loadUsers = async () => {
    setError('');

    try {
      const data = await api.listUsers();
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || 'Unable to load users');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const stats = useMemo(() => ({
    admins: users.filter((user) => ['super_admin', 'hq_admin', 'unit_admin'].includes(user.role)).length,
    officers: users.filter((user) => user.role === 'officer').length,
    clerks: users.filter((user) => user.role === 'clerk').length,
    trainees: users.filter((user) => user.role === 'trainee').length,
  }), [users]);

  const updateUserForm = (key, value) => {
    setUserForm((current) => ({ ...current, [key]: value }));
  };

  const submitUser = async (event) => {
    event.preventDefault();
    setError('');
    setMessage('');

    try {
      if (editingId) {
        await api.updateUser(editingId, userForm);
        setMessage('User updated');
      } else {
        await api.createUser(userForm);
        setMessage('User created');
      }

      setUserForm(emptyUser);
      setEditingId(null);
      await loadUsers();
    } catch (err) {
      setError(err.message || 'User save failed');
    }
  };

  const editUser = (user) => {
    setEditingId(user.id);
    setUserForm({
      email: user.email || '',
      password: '',
      role: user.role || 'trainee',
      rank_level: user.rank_level || 6,
      hq_id: user.hq_id || '',
      unit_id: user.unit_id || '',
      branch_id: user.branch_id || '',
      clerk_type: user.clerk_type || 'junior',
      task_category: user.task_category || '',
    });
  };

  const deleteUser = async (id) => {
    setError('');
    setMessage('');

    try {
      await api.deleteUser(id);
      setMessage('User deleted');
      await loadUsers();
    } catch (err) {
      setError(err.message || 'Delete failed');
    }
  };

  const createStructure = async (event) => {
    event.preventDefault();
    setError('');
    setMessage('');

    try {
      if (structureForm.hqName) {
        await api.createHq({ name: structureForm.hqName });
      }
      if (structureForm.unitName) {
        await api.createUnit({ name: structureForm.unitName, hq_id: Number(structureForm.unitHqId) });
      }
      if (structureForm.branchName) {
        await api.createBranch({
          name: structureForm.branchName,
          description: structureForm.branchDescription,
          unit_id: Number(structureForm.branchUnitId),
        });
      }
      setStructureForm(emptyStructure);
      setMessage('Hierarchy item created');
    } catch (err) {
      setError(err.message || 'Hierarchy save failed');
    }
  };

  return (
    <AppLayout
      title="Manage System Access"
      subtitle="Create HQs, units, branches, and users with backend rank and scope checks."
    >
      {error && <div className="form-error mb-4">{error}</div>}
      {message && <div className="form-success mb-4">{message}</div>}

      <div className="stats-grid mb-8">
        <div className="stat-card primary"><div className="stat-label">Admins</div><div className="stat-value">{isLoading ? '...' : stats.admins}</div></div>
        <div className="stat-card warning"><div className="stat-label">Officers</div><div className="stat-value">{isLoading ? '...' : stats.officers}</div></div>
        <div className="stat-card success"><div className="stat-label">Clerks</div><div className="stat-value">{isLoading ? '...' : stats.clerks}</div></div>
        <div className="stat-card danger"><div className="stat-label">Trainees</div><div className="stat-value">{isLoading ? '...' : stats.trainees}</div></div>
      </div>

      <div className="two-col mt-4">
        <div className="table-wrapper">
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Scope</th>
                <th>Rank</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div className="flex items-center gap-3">
                      <div className="avatar avatar-green">{user.email?.charAt(0)?.toUpperCase() || 'U'}</div>
                      <div>
                        <strong>{user.email}</strong>
                        <div className="text-xs text-muted">ID {user.id}</div>
                      </div>
                    </div>
                  </td>
                  <td><span className="badge badge-admin">{formatRole(user.role)}</span></td>
                  <td className="text-muted">HQ {user.hq_id || '-'} / Unit {user.unit_id || '-'} / Branch {user.branch_id || '-'}</td>
                  <td>{user.rank_level}</td>
                  <td>
                    <div className="flex gap-2">
                      <button className="btn btn-ghost btn-sm" type="button" onClick={() => editUser(user)}>Edit</button>
                      <button className="btn btn-danger btn-sm" type="button" onClick={() => deleteUser(user.id)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!isLoading && users.length === 0 && (
            <div className="empty-state">
              <span className="material-icons">group</span>
              <div>No users visible for this account.</div>
            </div>
          )}
        </div>

        <div className="flex-col gap-6">
          <div className="card">
            <h2 className="section-title">{editingId ? 'Edit User' : 'Create User'}</h2>
            <form onSubmit={submitUser}>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input type="email" className="form-input" value={userForm.email} onChange={(event) => updateUserForm('email', event.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">Password</label>
                <input type="password" className="form-input" value={userForm.password} onChange={(event) => updateUserForm('password', event.target.value)} placeholder={editingId ? 'Leave blank to keep current' : 'Password'} required={!editingId} />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Role</label>
                  <select className="form-select" value={userForm.role} onChange={(event) => updateUserForm('role', event.target.value)}>
                    <option value="hq_admin">HQ Admin</option>
                    <option value="unit_admin">Unit Admin</option>
                    <option value="officer">Officer</option>
                    <option value="clerk">Clerk</option>
                    <option value="trainee">Trainee</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Rank Level</label>
                  <input type="number" min="1" max="6" className="form-input" value={userForm.rank_level} onChange={(event) => updateUserForm('rank_level', event.target.value)} required />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">HQ ID</label>
                  <input type="number" className="form-input" value={userForm.hq_id} onChange={(event) => updateUserForm('hq_id', event.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Unit ID</label>
                  <input type="number" className="form-input" value={userForm.unit_id} onChange={(event) => updateUserForm('unit_id', event.target.value)} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Branch ID</label>
                <input type="number" className="form-input" value={userForm.branch_id} onChange={(event) => updateUserForm('branch_id', event.target.value)} />
              </div>
              {userForm.role === 'clerk' && (
                <>
                  <div className="form-group">
                    <label className="form-label">Clerk Type</label>
                    <select className="form-select" value={userForm.clerk_type} onChange={(event) => updateUserForm('clerk_type', event.target.value)}>
                      <option value="junior">Junior</option>
                      <option value="senior">Senior</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Task Category</label>
                    <input className="form-input" value={userForm.task_category} onChange={(event) => updateUserForm('task_category', event.target.value)} placeholder="ration, training..." />
                  </div>
                </>
              )}
              <div className="flex justify-end gap-3">
                <button type="button" className="btn btn-secondary" onClick={() => { setEditingId(null); setUserForm(emptyUser); }}>Clear</button>
                <button type="submit" className="btn btn-primary">{editingId ? 'Update User' : 'Create User'}</button>
              </div>
            </form>
          </div>

          <div className="card">
            <h2 className="section-title">Create Hierarchy</h2>
            <form onSubmit={createStructure}>
              <div className="form-group">
                <label className="form-label">HQ Name</label>
                <input className="form-input" value={structureForm.hqName} onChange={(event) => setStructureForm((current) => ({ ...current, hqName: event.target.value }))} placeholder="2STC" />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Unit Name</label>
                  <input className="form-input" value={structureForm.unitName} onChange={(event) => setStructureForm((current) => ({ ...current, unitName: event.target.value }))} placeholder="3TTR" />
                </div>
                <div className="form-group">
                  <label className="form-label">HQ ID</label>
                  <input type="number" className="form-input" value={structureForm.unitHqId} onChange={(event) => setStructureForm((current) => ({ ...current, unitHqId: event.target.value }))} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Branch Name</label>
                  <input className="form-input" value={structureForm.branchName} onChange={(event) => setStructureForm((current) => ({ ...current, branchName: event.target.value }))} placeholder="A" />
                </div>
                <div className="form-group">
                  <label className="form-label">Unit ID</label>
                  <input type="number" className="form-input" value={structureForm.branchUnitId} onChange={(event) => setStructureForm((current) => ({ ...current, branchUnitId: event.target.value }))} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Branch Description</label>
                <input className="form-input" value={structureForm.branchDescription} onChange={(event) => setStructureForm((current) => ({ ...current, branchDescription: event.target.value }))} placeholder="Admin Branch" />
              </div>
              <button type="submit" className="btn btn-primary w-full" style={{ justifyContent: 'center' }}>Create Hierarchy Items</button>
            </form>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
