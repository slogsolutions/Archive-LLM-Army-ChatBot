'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '../lib/api';
import Sidebar from './Sidebar';

export default function AppLayout({ children, title, subtitle, actions }) {
  const router = useRouter();
  const [user, setUser] = useState(null);

  useEffect(() => {
    const token = api.getToken();
    const storedUser = api.getUser();

    if (!token) {
      router.push('/');
      return;
    }

    setUser(storedUser);
    api.me()
      .then(setUser)
      .catch(() => {
        api.clearSession();
        router.push('/');
      });
  }, [router]);

  return (
    <div className="app-shell">
      <Sidebar user={user} />
      <div className="main-content">
        <header className="topbar">
          <div>
            <div className="topbar-title">{title}</div>
            {subtitle && <div className="topbar-breadcrumb">{subtitle}</div>}
          </div>
          <div className="topbar-actions">
            <button className="topbar-badge" title="Notifications">
              <span className="material-icons">notifications_none</span>
              <span className="badge-dot" />
            </button>
            <button className="topbar-badge" title="Help">
              <span className="material-icons">help_outline</span>
            </button>
            {actions}
          </div>
        </header>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
