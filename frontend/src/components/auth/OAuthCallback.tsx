import { useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { setToken, setRefreshToken } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { FullPageSpinner } from '@/components/common/Spinner';

export function OAuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const loadUser = useAuthStore((s) => s.loadUser);

  const error = useMemo(() => {
    const errorParam = searchParams.get('error');
    if (errorParam) return errorParam;
    if (!searchParams.get('access_token')) return 'No access token received';
    return '';
  }, [searchParams]);

  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => navigate('/login'), 3000);
      return () => clearTimeout(timer);
    }

    const accessToken = searchParams.get('access_token');
    const refreshToken = searchParams.get('refresh_token');

    if (accessToken) {
      setToken(accessToken);
      if (refreshToken) {
        setRefreshToken(refreshToken);
      }
      loadUser().then(() => {
        navigate('/board');
      });
    }
  }, [error, searchParams, navigate, loadUser]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <p className="text-lg font-semibold text-red-600">
            Authentication Error
          </p>
          <p className="mt-2 text-sm text-gray-500">{error}</p>
          <p className="mt-2 text-xs text-gray-400">Redirecting to login...</p>
        </div>
      </div>
    );
  }

  return <FullPageSpinner />;
}
