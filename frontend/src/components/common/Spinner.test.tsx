import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Spinner, FullPageSpinner } from './Spinner';

describe('Spinner', () => {
  it('renders an svg element', () => {
    const { container } = render(<Spinner />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
  });

  it('has animate-spin class', () => {
    const { container } = render(<Spinner />);
    const svg = container.querySelector('svg')!;
    expect(svg.classList.toString()).toContain('animate-spin');
  });

  it('applies medium size by default', () => {
    const { container } = render(<Spinner />);
    const svg = container.querySelector('svg')!;
    const classes = svg.classList.toString();
    expect(classes).toContain('h-6');
    expect(classes).toContain('w-6');
  });

  it('applies small size variant', () => {
    const { container } = render(<Spinner size="sm" />);
    const svg = container.querySelector('svg')!;
    const classes = svg.classList.toString();
    expect(classes).toContain('h-4');
    expect(classes).toContain('w-4');
  });

  it('applies large size variant', () => {
    const { container } = render(<Spinner size="lg" />);
    const svg = container.querySelector('svg')!;
    const classes = svg.classList.toString();
    expect(classes).toContain('h-10');
    expect(classes).toContain('w-10');
  });

  it('accepts additional className', () => {
    const { container } = render(<Spinner className="text-red-500" />);
    const svg = container.querySelector('svg')!;
    expect(svg.classList.toString()).toContain('text-red-500');
  });

  it('has brand color class', () => {
    const { container } = render(<Spinner />);
    const svg = container.querySelector('svg')!;
    expect(svg.classList.toString()).toContain('text-brand-600');
  });
});

describe('FullPageSpinner', () => {
  it('renders a spinner inside a full-page container', () => {
    const { container } = render(<FullPageSpinner />);
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain('min-h-screen');
    expect(wrapper.className).toContain('flex');

    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
  });

  it('renders with large spinner size', () => {
    const { container } = render(<FullPageSpinner />);
    const svg = container.querySelector('svg')!;
    const classes = svg.classList.toString();
    expect(classes).toContain('h-10');
    expect(classes).toContain('w-10');
  });
});
