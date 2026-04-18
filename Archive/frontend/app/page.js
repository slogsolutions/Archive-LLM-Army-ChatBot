'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from './lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('super@army.com');
  const [password, setPassword] = useState('123');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async (event) => {
    event.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await api.login(email, password);
      router.push('/dashboard');
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-panel">
        <div>
          <h1 className="login-brand">Army Archive</h1>
          <p className="login-tagline">Secure records, approvals, and searchable document intelligence.</p>
        </div>
        <div className="login-decorations">
          <span className="login-dec-chip">
            <span className="material-icons" style={{ fontSize: '14px' }}>verified_user</span>
            RBAC Secure
          </span>
          <span className="login-dec-chip">
            <span className="material-icons" style={{ fontSize: '14px' }}>inventory_2</span>
            Archive Flow
          </span>
        </div>
      </div>
      <div className="login-form-panel">
        <h2 className="login-form-title">Welcome Back</h2>
        <p className="login-form-sub">Use your Army Archive credentials to continue.</p>

        <form onSubmit={handleLogin}>
          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input
              type="email"
              className="form-input"
              placeholder="super@army.com"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input
              type="password"
              className="form-input"
              placeholder="Password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {error && <div className="form-error mb-4">{error}</div>}
          <button type="submit" className="btn btn-primary w-full" style={{ justifyContent: 'center' }} disabled={isLoading}>
            {isLoading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div className="login-footer">Army Archive System</div>
      </div>
    </div>
  );
}
