import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Link } from 'react-router-dom';

const base =
  'inline-flex items-center justify-center gap-1.5 rounded-input px-4 py-2 text-15 font-medium transition-opacity duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-60';

export const primaryClass = `${base} bg-seal text-white hover:opacity-90`;
export const secondaryClass = `${base} border border-line text-ink hover:border-ink-2`;

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary';
};

export function Button({ variant = 'secondary', className = '', ...rest }: ButtonProps) {
  const cls = variant === 'primary' ? primaryClass : secondaryClass;
  return <button {...rest} className={`${cls} ${className}`} />;
}

export function LinkButton({
  to,
  variant = 'secondary',
  className = '',
  children,
}: {
  to: string;
  variant?: 'primary' | 'secondary';
  className?: string;
  children: ReactNode;
}) {
  const cls = variant === 'primary' ? primaryClass : secondaryClass;
  return (
    <Link to={to} className={`${cls} ${className}`}>
      {children}
    </Link>
  );
}

export function Card({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`rounded-card border border-line bg-white ${className}`}>{children}</div>;
}

export function ErrorNote({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-card border border-line bg-white p-6">
      <p className="text-15 text-danger">{message}</p>
      {onRetry && (
        <Button className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
