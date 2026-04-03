import { useState, FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { useAuth } from '@/hooks/useAuth';
import { useTodoAssistantStore } from '@/stores/todoAssistantStore';

export function RegisterPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState('');
  const { register, isLoading, error, clearError } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLocalError('');

    if (password !== confirmPassword) {
      setLocalError('Passwords do not match');
      return;
    }
    if (password.length < 8) {
      setLocalError('Password must be at least 8 characters');
      return;
    }

    try {
      await register(email, password, name);
      navigate('/board');
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      const data = (err as { response?: { data?: { detail?: string; message?: string } } })?.response?.data;
      const detail = data?.detail || data?.message || 'Registration failed';
      // Don't add TODO for user-level errors like "email already exists"
      if (status === 409 || detail.toLowerCase().includes('already exists')) {
        // Store already shows the error — no need for TODO
      } else {
        useTodoAssistantStore.getState().addTodo({
          severity: status ? 'warning' : 'critical',
          source: 'auto:api',
          title: 'Регистрация не работает',
          detail: status
            ? `HTTP ${status}: ${detail}. Проверьте backend /auth/register.`
            : `Сетевая ошибка — backend недоступен. Запустите backend сервер.`,
          identifier: 'auth:register-fail',
          checkKey: 'auth:register',
        });
        useTodoAssistantStore.getState().open();
      }
    }
  };

  const displayError = localError || error;

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-secondary px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="mb-8 text-center">
          <img
            src="/logo-devbot.webp"
            alt="Dev-bot"
            className="mx-auto mb-4 h-14 w-14 rounded-2xl object-contain"
          />
          <h1 className="text-2xl font-bold text-gray-900">Create account</h1>
          <p className="mt-1 text-sm text-gray-500">
            Get started with the AI Coding Pipeline
          </p>
        </div>

        {/* Form */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-4">
            {displayError && (
              <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
                {displayError}
              </div>
            )}

            <div>
              <label
                htmlFor="name"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Full Name
              </label>
              <input
                id="name"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jane Smith"
                className="input"
                autoComplete="name"
              />
            </div>

            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (error) clearError();
                }}
                placeholder="you@company.com"
                className="input"
                autoComplete="email"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  className="input pr-10"
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            <div>
              <label
                htmlFor="confirmPassword"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Confirm Password
              </label>
              <input
                id="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Repeat your password"
                className="input"
                autoComplete="new-password"
              />
            </div>

            <Button
              type="submit"
              loading={isLoading}
              className="w-full"
            >
              Create Account
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-gray-500">
            Already have an account?{' '}
            <Link to="/login" className="font-medium text-brand-600 hover:text-brand-700">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
