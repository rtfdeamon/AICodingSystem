import apiClient from '@/api/client';
import { useTodoAssistantStore } from '@/stores/todoAssistantStore';

/** Results of verification checks — true = OK, false = still broken */
export type VerificationResults = Record<string, boolean>;

/**
 * Runs verification checks and returns results keyed by checkKey.
 * Used by store.verifyAll() to auto-resolve or reopen items.
 */
export async function runVerificationChecks(): Promise<VerificationResults> {
  const results: VerificationResults = {};

  // Check API health
  try {
    await apiClient.get('/health', { timeout: 5000 });
    results['env:api-health'] = true;
  } catch {
    results['env:api-health'] = false;
  }

  // Check GitHub OAuth
  try {
    const resp = await apiClient.get('/auth/github/url', { timeout: 5000 });
    results['oauth:github-url'] = !!resp.data?.url;
  } catch {
    results['oauth:github-url'] = false;
  }

  // Check env vars
  results['env:api-url'] = !!import.meta.env.VITE_API_URL;
  results['env:ws-url'] = !!import.meta.env.VITE_WS_URL;

  // Check registration endpoint reachability
  try {
    // OPTIONS or lightweight probe — we don't want to actually register
    await apiClient.options('/auth/register', { timeout: 5000 });
    results['auth:register'] = true;
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    // 405 Method Not Allowed is fine — means endpoint exists
    results['auth:register'] = status === 405 || status === 422;
  }

  return results;
}

/**
 * Runs environment diagnostics and reports issues to the TODO assistant.
 * Called once on app startup.
 */
export async function runEnvDiagnostics() {
  const { addTodo } = useTodoAssistantStore.getState();

  // 1. Check API connectivity
  try {
    await apiClient.get('/health', { timeout: 5000 });
  } catch {
    addTodo({
      severity: 'critical',
      source: 'auto:env',
      title: 'Backend API недоступен',
      detail: `Не удалось подключиться к API (${apiClient.defaults.baseURL}). Регистрация, логин и все серверные операции не будут работать. Убедитесь, что backend запущен.`,
      identifier: 'env:api-health',
      checkKey: 'env:api-health',
    });
  }

  // 2. Check GitHub OAuth endpoint
  try {
    await apiClient.get('/auth/github/url', { timeout: 5000 });
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    const isNetworkError = !status;

    addTodo({
      severity: status === 501 ? 'warning' : 'critical',
      source: 'auto:oauth',
      title: 'Continue with GitHub не работает',
      detail: isNetworkError
        ? 'Backend недоступен — GitHub OAuth URL не получен. Кнопка "Continue with GitHub" не сработает.'
        : status === 501
          ? 'GitHub OAuth не сконфигурирован (GITHUB_CLIENT_ID не задан). Задайте на backend для активации.'
          : status === 404
            ? 'Эндпоинт /auth/github/url не найден (404). GitHub OAuth не сконфигурирован на backend.'
            : `Ошибка ${status} при запросе GitHub OAuth URL. Проверьте GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET на backend.`,
      identifier: 'oauth:github-url',
      checkKey: 'oauth:github-url',
    });
  }

  // 3. Check WebSocket URL
  const wsUrl = import.meta.env.VITE_WS_URL;
  if (!wsUrl) {
    addTodo({
      severity: 'warning',
      source: 'auto:ws',
      title: 'WebSocket URL не настроен',
      detail: 'Переменная окружения VITE_WS_URL не задана. Realtime-обновления (Kanban, уведомления) могут не работать.',
      identifier: 'env:ws-url',
      checkKey: 'env:ws-url',
    });
  }

  // 4. Check VITE_API_URL
  const apiUrl = import.meta.env.VITE_API_URL;
  if (!apiUrl) {
    addTodo({
      severity: 'warning',
      source: 'auto:env',
      title: 'VITE_API_URL не задан',
      detail: 'Используется fallback /api/v1. Если backend на другом хосте/порте — настройте .env файл с VITE_API_URL.',
      identifier: 'env:api-url',
      checkKey: 'env:api-url',
    });
  }
}

/**
 * Installs an Axios response interceptor that auto-logs API errors to the TODO store.
 */
export function installApiErrorInterceptor() {
  const seenErrors = new Set<string>();

  apiClient.interceptors.response.use(
    (res) => res,
    (error) => {
      const { addTodo } = useTodoAssistantStore.getState();
      const url: string = error?.config?.url || 'unknown';
      const method: string = (error?.config?.method || 'GET').toUpperCase();
      const status: number | undefined = error?.response?.status;
      const message: string = error?.response?.data?.detail || error?.response?.data?.message || error?.message || 'Unknown error';

      // Deduplicate by method+url+status within session
      const key = `${method}:${url}:${status ?? 'network'}`;
      if (seenErrors.has(key)) return Promise.reject(error);
      seenErrors.add(key);

      // Don't log auth refresh failures (handled by interceptor in client.ts)
      if (url.includes('/auth/refresh')) return Promise.reject(error);
      // Don't log health checks (already handled by diagnostics)
      if (url.includes('/health')) return Promise.reject(error);
      // Don't log github/url checks (already handled by diagnostics)
      if (url.includes('/auth/github/url')) return Promise.reject(error);

      const severity = status && status >= 500 ? 'critical' : 'warning';

      addTodo({
        severity,
        source: 'auto:api',
        title: `API ошибка: ${method} ${url}`,
        detail: status
          ? `HTTP ${status}: ${message}`
          : `Сетевая ошибка: ${message}. Проверьте что backend запущен и доступен.`,
        identifier: `api:${method}:${url}`,
      });

      return Promise.reject(error);
    },
  );
}
