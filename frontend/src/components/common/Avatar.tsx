import { clsx } from 'clsx';

interface AvatarProps {
  src?: string | null;
  name: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeClasses = {
  sm: 'h-6 w-6 text-[10px]',
  md: 'h-8 w-8 text-xs',
  lg: 'h-10 w-10 text-sm',
};

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function hashColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = [
    'bg-brand-500',
    'bg-emerald-500',
    'bg-amber-500',
    'bg-rose-500',
    'bg-cyan-500',
    'bg-violet-500',
    'bg-pink-500',
    'bg-teal-500',
  ];
  return colors[Math.abs(hash) % colors.length];
}

export function Avatar({ src, name, size = 'md', className }: AvatarProps) {
  if (src) {
    return (
      <img
        src={src}
        alt={name}
        className={clsx(
          'rounded-full object-cover ring-2 ring-white',
          sizeClasses[size],
          className,
        )}
      />
    );
  }

  return (
    <div
      className={clsx(
        'inline-flex items-center justify-center rounded-full font-semibold text-white ring-2 ring-white',
        hashColor(name),
        sizeClasses[size],
        className,
      )}
      title={name}
    >
      {getInitials(name)}
    </div>
  );
}
