'use client';

import { useEffect, useMemo, useState } from 'react';
import AppLayout from '../components/AppLayout';
import { api, formatRole } from '../lib/api';

const emptyUser = {
  army_number: '',
  name: '',
  password: '123',
  role: 'trainee',
  rank_level: 6,
  hq_id: '',
  unit_id: '',
  branch_id: '',
  clerk_type: 'junior',
  task_category: '',
};

export default function UserManagementPage() {
  const [users, setUsers] = useState([]);
  const [hqs, setHqs] = useState([]);
  const [units, setUnits] = useState([]);
  const [branches, setBranches] = useState([]);
  const [userForm, setUserForm] = useState(emptyUser);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const selectedHqId = Number(userForm.hq_id) || null;
  const selectedUnitId = Number(userForm.unit_id) || null;
  const filteredUnits = selectedHqId ? units.filter((unit) => unit.hq_id === selectedHqId) : units;
  const filteredBranches = selectedUnitId ? branches.filter((branch) => branch.unit_id === selectedUnitId) : branches;

  const loadData = async () => {
    setError('');

    try {
      const [userList, hqList, unitList, branchList] = await Promise.all([
        api.listUsers(),
        api.listHq(),
        api.listUnits(),
        api.listBranches(),
      ]);

      setUsers(Array.isArray(userList) ? userList : []);
      setHqs(Array.isArray(hqList) ? hqList : []);
      setUnits(Array.isArray(unitList) ? unitList : []);
      setBranches(Array.isArray(branchList) ? branchList : []);
    } catch (err) {
      setError(err.message || 'Unable to load users');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const stats = useMemo(() => ({
    admins: users.filter((user) => ['super_admin', 'hq_admin', 'unit_admin'].includes(user.role)).length,
    officers: users.filter((user) => user.role === 'officer').length,
    clerks: users.filter((user) => user.role === 'clerk').length,
    trainees: users.filter((user) => user.role === 'trainee').length,
  }), [users]);

  const findHqName = (id) => hqs.find((hq) => hq.id === id)?.name || '-';
  const findUnitName = (id) => units.find((unit) => unit.id === id)?.name || '-';
  const findBranchName = (id) => branches.find((branch) => branch.id === id)?.name || '-';

  const updateUserForm = (key, value) => {
    setUserForm((current) => {
      const next = { ...current, [key]: value };

      if (key === 'hq_id') {
        next.unit_id = '';
        next.branch_id = '';
      }

      if (key === 'unit_id') {
        next.branch_id = '';
      }

      return next;
    });
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
      await loadData();
    } catch (err) {
      setError(err.message || 'User save failed');
    }
  };

  const editUser = (user) => {
    setEditingId(user.id);
    setUserForm({
      army_number: user.army_number || '',
      name: user.name || '',
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
      await loadData();
    } catch (err) {
      setError(err.message || 'Delete failed');
    }
  };

  return (
    <AppLayout
      title="User Management"
      subtitle="Manage Army personnel access with role, rank, and hierarchy-linked scope."
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
        <div className="table-wrapper animated-panel">
          <table className="table">
            <thead>
              <tr>
                <th>Personnel</th>
                <th>Role</th>
                <th>Hierarchy Scope</th>
                <th>Rank</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div className="flex items-center gap-3">
                      <div className="avatar avatar-green">{user.name?.charAt(0)?.toUpperCase() || 'U'}</div>
                      <div>
                        <strong>{user.name || 'Unnamed User'}</strong>
                        <div className="text-xs text-muted">{user.army_number}</div>
                      </div>
                    </div>
                  </td>
                  <td><span className="badge badge-admin">{formatRole(user.role)}</span></td>
                  <td className="text-muted">
                    {findHqName(user.hq_id)} / {findUnitName(user.unit_id)} / {findBranchName(user.branch_id)}
                  </td>
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

        <div className="card animated-panel">
          <h2 className="section-title">{editingId ? 'Edit Personnel' : 'Register Personnel'}</h2>
          <form onSubmit={submitUser}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Army Number</label>
                <input className="form-input" value={userForm.army_number} onChange={(event) => updateUserForm('army_number', event.target.value)} placeholder="IC-45821" required />
              </div>
              <div className="form-group">
                <label className="form-label">Name</label>
                <input className="form-input" value={userForm.name} onChange={(event) => updateUserForm('name', event.target.value)} placeholder="Name" required />
              </div>
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

            <div className="form-group">
              <label className="form-label">Headquarter</label>
              <select className="form-select" value={userForm.hq_id} onChange={(event) => updateUserForm('hq_id', event.target.value)}>
                <option value="">Select HQ...</option>
                {hqs.map((hq) => <option key={hq.id} value={hq.id}>{hq.name}</option>)}
              </select>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Unit</label>
                <select className="form-select" value={userForm.unit_id} onChange={(event) => updateUserForm('unit_id', event.target.value)} disabled={!userForm.hq_id}>
                  <option value="">Select Unit...</option>
                  {filteredUnits.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Branch</label>
                <select className="form-select" value={userForm.branch_id} onChange={(event) => updateUserForm('branch_id', event.target.value)} disabled={!userForm.unit_id}>
                  <option value="">Select Branch...</option>
                  {filteredBranches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
                </select>
              </div>
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
      </div>
    </AppLayout>
  );
}
