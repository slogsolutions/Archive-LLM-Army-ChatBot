'use client';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
const TOKEN_KEY = 'archive_access_token';
const USER_KEY = 'archive_current_user';

function getStoredToken() {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

function getStoredUser() {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function setSession(token, user) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearSession() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

async function readError(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join(', ');
    if (body.message) return body.message;
  } catch {
    return response.statusText;
  }

  return response.statusText || 'Request failed';
}

async function request(path, options = {}) {
  const token = options.token === undefined ? getStoredToken() : options.token;
  const headers = new Headers(options.headers || {});

  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }

  return response;
}

async function login(armyNumber, password) {
  const auth = await request('/auth/login', {
    method: 'POST',
    token: null,
    body: JSON.stringify({ army_number: armyNumber, password }),
  });

  const user = await request('/auth/me', { token: auth.access_token });
  setSession(auth.access_token, user);
  return user;
}

function normalizeUser(user, { includeBlankPassword = true } = {}) {
  const payload = {
    army_number: user.army_number,
    name: user.name,
    role: user.role,
    rank_level: Number(user.rank_level),
    hq_id: user.hq_id ? Number(user.hq_id) : null,
    unit_id: user.unit_id ? Number(user.unit_id) : null,
    branch_id: user.branch_id ? Number(user.branch_id) : null,
    clerk_type: user.role === 'clerk' ? user.clerk_type : null,
    task_category: user.role === 'clerk' ? user.task_category : null,
  };

  if (includeBlankPassword || user.password) {
    payload.password = user.password;
  }

  return payload;
}

function uploadDocument(payload) {
  const data = new FormData();
  data.append('file', payload.file);
  data.append('branch', payload.branch);
  data.append('document_type', payload.document_type);

  ['hq_id', 'unit_id', 'branch_id', 'section', 'year', 'min_visible_rank'].forEach((key) => {
    if (payload[key] !== undefined && payload[key] !== null && payload[key] !== '') {
      data.append(key, String(payload[key]));
    }
  });

  return request('/documents/upload', {
    method: 'POST',
    body: data,
  });
}

async function downloadDocument(id, fileName) {
  const response = await request(`/documents/download/${id}`, {
    method: 'GET',
  });
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName || `document-${id}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export const api = {
  baseUrl: API_BASE_URL,
  getToken: getStoredToken,
  getUser: getStoredUser,
  clearSession,
  login,
  me: () => request('/auth/me'),
  listHq: () => request('/hq/'),
  createHq: (payload) => request('/hq/create', { method: 'POST', body: JSON.stringify(payload) }),
  updateHq: (id, payload) => request(`/hq/update/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteHq: (id) => request(`/hq/delete/${id}`, { method: 'DELETE' }),
  listUnits: () => request('/unit/'),
  createUnit: (payload) => request('/unit/create', { method: 'POST', body: JSON.stringify(payload) }),
  updateUnit: (id, payload) => request(`/unit/update/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteUnit: (id) => request(`/unit/delete/${id}`, { method: 'DELETE' }),
  listBranches: () => request('/branch/'),
  createBranch: (payload) => request('/branch/create', { method: 'POST', body: JSON.stringify(payload) }),
  updateBranch: (id, payload) => request(`/branch/update/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteBranch: (id) => request(`/branch/delete/${id}`, { method: 'DELETE' }),
  listUsers: () => request('/users/'),
  createUser: (payload) => request('/users/create', { method: 'POST', body: JSON.stringify(normalizeUser(payload)) }),
  updateUser: (id, payload) => request(`/users/update/${id}`, { method: 'PUT', body: JSON.stringify(normalizeUser(payload, { includeBlankPassword: false })) }),
  deleteUser: (id) => request(`/users/delete/${id}`, { method: 'DELETE' }),
  listDocuments: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') q.set(k, v); });
    const qs = q.toString();
    return request(`/documents/${qs ? `?${qs}` : ''}`);
  },
  getDocument: (id) => request(`/documents/${id}`),
  approveDocument: (id) => request(`/documents/approve/${id}`, { method: 'POST' }),
  rejectDocument: (id, reason) => request(`/documents/reject/${id}?reason=${encodeURIComponent(reason)}`, { method: 'POST' }),
  approveDelete: (id) => request(`/documents/approve-delete/${id}`, { method: 'POST' }),
  requestDelete: (id) => request(`/documents/delete/${id}`, { method: 'DELETE' }),
  reindexDocument: (id) => request(`/documents/reindex/${id}`, { method: 'POST' }),
  indexDocumentText: (id) => request(`/documents/index-text/${id}`, { method: 'POST' }),
  updateDocumentText: (id, text) => request(`/documents/update-text/${id}?text=${encodeURIComponent(text)}`, { method: 'PUT' }),
  searchDocuments: (query, filters = {}) => {
    const q = new URLSearchParams({ query });
    Object.entries(filters).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') q.set(k, v); });
    return request(`/documents/search?${q.toString()}`);
  },
  listPendingApprovals: () => request('/documents/pending-approvals'),
  listPendingDeletions: () => request('/documents/pending-deletions'),
  uploadDocument,
  downloadDocument,
  downloadUrl: (id) => `${API_BASE_URL}/documents/download/${id}`,
};

export function formatRole(role) {
  return (role || '').replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatFileSize(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unit = 0;

  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }

  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}
