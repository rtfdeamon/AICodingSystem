import { NavLink } from 'react-router-dom';
import {
  KanbanSquare,
  BarChart3,
  Users,
  Settings,
  Info,
} from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { clsx } from 'clsx';

const navItems = [
  { to: '/board', label: 'Board', icon: KanbanSquare },
  { to: '/dashboard', label: 'Dashboard', icon: BarChart3, roles: ['pm_lead'] },
  {
    to: '/admin/users',
    label: 'Users',
    icon: Users,
    roles: ['pm_lead'],
  },
];

export function Sidebar() {
  const { user } = useAuth();

  const filteredNav = navItems.filter(
    (item) => !item.roles || (user && item.roles.includes(user.role)),
  );

  return (
    <aside className="flex h-full w-64 flex-col border-r border-gray-200 bg-white">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-gray-200 px-6">
        <img
          src="/logo-devbot.webp"
          alt="Dev-bot"
          className="h-9 w-9 rounded-lg object-contain"
        />
        <div>
          <h1 className="text-sm font-bold text-gray-900 leading-tight">
            AI Coding
          </h1>
          <p className="text-[10px] font-medium text-gray-500 uppercase tracking-wider">
            Pipeline
          </p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {filteredNav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-brand-50 text-brand-700'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
              )
            }
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-gray-200 p-4 space-y-1">
        <NavLink
          to="/about"
          className={({ isActive }) =>
            clsx(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-brand-50 text-brand-700'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700',
            )
          }
        >
          <Info className="h-5 w-5" />
          About
        </NavLink>
        <NavLink
          to="/settings"
          className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors"
        >
          <Settings className="h-5 w-5" />
          Settings
        </NavLink>
      </div>
    </aside>
  );
}
