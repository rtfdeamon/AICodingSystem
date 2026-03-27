import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from './LoginPage';

const mockLogin = vi.fn();
const mockClearError = vi.fn();
const mockNavigate = vi.fn();

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    login: mockLogin,
    isLoading: false,
    error: mockError,
    clearError: mockClearError,
    user: null,
    isAuthenticated: false,
    logout: vi.fn(),
    register: vi.fn(),
    token: null,
  }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('@/api/client', () => ({
  default: { get: vi.fn() },
}));

let mockError: string | null = null;

function renderLoginPage() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockError = null;
  });

  it('renders "Welcome back" heading', () => {
    renderLoginPage();
    expect(screen.getByText('Welcome back')).toBeInTheDocument();
  });

  it('shows email input field', () => {
    renderLoginPage();
    const emailInput = screen.getByLabelText('Email');
    expect(emailInput).toBeInTheDocument();
    expect(emailInput).toHaveAttribute('type', 'email');
  });

  it('shows password input field', () => {
    renderLoginPage();
    const passwordInput = screen.getByLabelText('Password');
    expect(passwordInput).toBeInTheDocument();
    expect(passwordInput).toHaveAttribute('type', 'password');
  });

  it('shows "Sign In" button', () => {
    renderLoginPage();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('shows "Continue with GitHub" button', () => {
    renderLoginPage();
    expect(
      screen.getByRole('button', { name: /continue with github/i }),
    ).toBeInTheDocument();
  });

  it('shows link to register page', () => {
    renderLoginPage();
    const link = screen.getByRole('link', { name: /sign up/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/register');
  });

  it('toggles password visibility when eye icon button is clicked', () => {
    renderLoginPage();
    const passwordInput = screen.getByLabelText('Password');
    expect(passwordInput).toHaveAttribute('type', 'password');

    // The toggle button is inside the password field's container
    // It's a button with type="button" that is not Sign In or GitHub
    const buttons = screen.getAllByRole('button');
    const toggleButton = buttons.find(
      (btn) =>
        btn.getAttribute('type') === 'button' &&
        !btn.textContent?.includes('Sign In') &&
        !btn.textContent?.includes('Continue with GitHub'),
    );
    expect(toggleButton).toBeDefined();

    fireEvent.click(toggleButton!);
    expect(passwordInput).toHaveAttribute('type', 'text');

    fireEvent.click(toggleButton!);
    expect(passwordInput).toHaveAttribute('type', 'password');
  });

  it('shows error message when error is set in auth store', () => {
    mockError = 'Invalid credentials';
    renderLoginPage();
    expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
  });

  it('calls clearError when typing in email input while error exists', () => {
    mockError = 'Some error';
    renderLoginPage();
    const emailInput = screen.getByLabelText('Email');
    fireEvent.change(emailInput, { target: { value: 'a' } });
    expect(mockClearError).toHaveBeenCalled();
  });

  it('submits form with email and password', async () => {
    mockLogin.mockResolvedValue(undefined);
    renderLoginPage();

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@example.com' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'password123');
  });

  it('shows subtitle text', () => {
    renderLoginPage();
    expect(
      screen.getByText('Sign in to the AI Coding Pipeline'),
    ).toBeInTheDocument();
  });
});
