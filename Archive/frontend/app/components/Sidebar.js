'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { api, formatRole } from '../lib/api';

// Roles that can see each nav item. Omit a role to hide that item from them.
const NAV_RBAC = {
  '/dashboard': ['super_admin', 'hq_admin', 'unit_admin', 'officer', 'clerk', 'trainee'],
  '/archive':   ['super_admin', 'hq_admin', 'unit_admin', 'officer', 'clerk', 'trainee'],
  '/uploads':   ['super_admin', 'hq_admin', 'unit_admin', 'officer', 'clerk'],
  '/hierarchy': ['super_admin', 'hq_admin', 'unit_admin', 'officer'],
  '/users':     ['super_admin', 'hq_admin', 'unit_admin'],
};

const navItems = [
  { href: '/dashboard', icon: 'dashboard',     label: 'Dashboard' },
  { href: '/archive',   icon: 'inventory_2',   label: 'Archive' },
  { href: '/uploads',   icon: 'cloud_upload',  label: 'Uploads' },
  { href: '/hierarchy', icon: 'account_tree',  label: 'Hierarchy' },
  { href: '/users',     icon: 'group',         label: 'User Management' },
];

export default function Sidebar({ user }) {
  const pathname = usePathname();
  const router   = useRouter();

  const handleLogout = () => {
    api.clearSession();
    router.push('/');
  };

  const initial = user?.name?.charAt(0)?.toUpperCase() || user?.army_number?.charAt(0)?.toUpperCase() || 'A';
  const role = user?.role || '';

  const visibleItems = navItems.filter(item => NAV_RBAC[item.href]?.includes(role));

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-name">Army Archive</div>
        <div className="sidebar-logo-sub">Management System</div>
      </div>

      <nav className="sidebar-nav">
        {visibleItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href === '/archive' && pathname.startsWith('/archive'));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-item ${isActive ? 'active' : ''}`}
            >
              <span className="material-icons">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-avatar">{initial}</div>
        <div>
          <div className="sidebar-user-name">{user?.name || 'Loading...'}</div>
          <div className="sidebar-user-number">{user?.army_number || ''}</div>
          <div className="sidebar-user-role">{formatRole(user?.role || 'User')}</div>
        </div>
        <button className="sidebar-logout" onClick={handleLogout} title="Sign out">
          <span className="material-icons">logout</span>
          <span className="sidebar-logout-label">Sign out</span>
        </button>
      </div>
    </aside>
  );
}
