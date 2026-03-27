import { useState, useEffect, useCallback } from 'react';
import { Users, Search, Shield, Loader2 } from 'lucide-react';
import { Badge } from '@/components/common/Badge';
import { Avatar } from '@/components/common/Avatar';
import { Button } from '@/components/common/Button';
import type { User, UserRole } from '@/types';
import { listUsers, changeUserRole } from '@/api/users';

const roleBadgeVariant: Record<UserRole, 'danger' | 'primary' | 'purple' | 'success'> = {
  owner: 'danger',
  developer: 'primary',
  pm_lead: 'purple',
  ai_agent: 'success',
};

const allRoles: UserRole[] = ['owner', 'developer', 'pm_lead', 'ai_agent'];

export function UserManagement() {
  const [searchQuery, setSearchQuery] = useState('');
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listUsers();
      setUsers(data);
    } catch {
      setError('Failed to load users. You may not have permission.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleRoleChange = async (userId: string, newRole: UserRole) => {
    try {
      const updated = await changeUserRole(userId, newRole);
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
    } catch {
      setError('Failed to update role.');
    } finally {
      setEditingUserId(null);
    }
  };

  const filteredUsers = users.filter(
    (u) =>
      u.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div>
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-100">
            <Users className="h-5 w-5 text-brand-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
            <p className="text-sm text-gray-500">
              Manage team members and their roles
            </p>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="mb-4 relative w-80">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Search users..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="input pl-10"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-brand-500" />
          <span className="ml-2 text-sm text-gray-500">Loading users...</span>
        </div>
      )}

      {/* Table */}
      {!loading && (
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  User
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Email
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Role
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredUsers.map((user) => (
                <tr key={user.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <Avatar name={user.full_name} size="md" />
                      <span className="text-sm font-medium text-gray-900">
                        {user.full_name}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-sm text-gray-500">{user.email}</span>
                  </td>
                  <td className="px-6 py-4">
                    {editingUserId === user.id ? (
                      <select
                        defaultValue={user.role}
                        className="input w-40 text-sm"
                        onChange={(e) => handleRoleChange(user.id, e.target.value as UserRole)}
                        onBlur={() => setEditingUserId(null)}
                        autoFocus
                      >
                        {allRoles.map((role) => (
                          <option key={role} value={role}>
                            {role.replace('_', ' ')}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Badge variant={roleBadgeVariant[user.role]}>
                        <Shield className="h-3 w-3 mr-1" />
                        {user.role.replace('_', ' ')}
                      </Badge>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setEditingUserId(editingUserId === user.id ? null : user.id)
                      }
                    >
                      Edit Role
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filteredUsers.length === 0 && (
            <div className="px-6 py-12 text-center text-sm text-gray-400">
              No users found matching your search.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
