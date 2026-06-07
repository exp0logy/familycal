// ─────────────────────────────────────────────────────────────────────────────
// Button — primary interactive action element.
// Variants: primary | secondary | ghost | danger | icon
// ─────────────────────────────────────────────────────────────────────────────

import React from 'react';
import Spinner from './Spinner';

/**
 * @param {{
 *   children?: React.ReactNode,
 *   variant?: 'primary'|'secondary'|'ghost'|'danger'|'icon',
 *   size?: 'sm'|'md'|'lg',
 *   loading?: boolean,
 *   disabled?: boolean,
 *   icon?: React.ReactNode,
 *   iconRight?: React.ReactNode,
 *   className?: string,
 *   type?: 'button'|'submit'|'reset',
 *   onClick?: (e: React.MouseEvent) => void,
 *   title?: string,
 * }} props
 */
const Button = ({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  icon,
  iconRight,
  className = '',
  type = 'button',
  onClick,
  title,
  ...rest
}) => {
  // ── Variant styles ────────────────────────────────────────────────────────

  const variantStyles = {
    primary: [
      'bg-accent-500 text-white',
      'hover:bg-accent-600 active:bg-accent-700',
      'shadow-glow-sm hover:shadow-glow',
      'border border-accent-600',
    ].join(' '),

    secondary: [
      'bg-surface-3 text-text-primary',
      'hover:bg-surface-4 active:bg-surface-5',
      'border border-surface-4 hover:border-surface-5',
    ].join(' '),

    ghost: [
      'bg-transparent text-text-secondary',
      'hover:bg-surface-3 hover:text-text-primary active:bg-surface-4',
      'border border-transparent',
    ].join(' '),

    danger: [
      'bg-error/10 text-error',
      'hover:bg-error hover:text-white active:bg-red-700',
      'border border-error/30 hover:border-error',
    ].join(' '),

    icon: [
      'bg-transparent text-text-secondary',
      'hover:bg-surface-3 hover:text-text-primary active:bg-surface-4',
      'border border-transparent rounded-full',
    ].join(' '),
  };

  // ── Size styles ────────────────────────────────────────────────────────────

  const sizeStyles = {
    sm: variant === 'icon' ? 'w-8 h-8 p-0' : 'h-8 px-3 text-body-sm gap-1.5',
    md: variant === 'icon' ? 'w-10 h-10 p-0' : 'h-10 px-4 text-body gap-2',
    lg: variant === 'icon' ? 'w-12 h-12 p-0' : 'h-12 px-6 text-body-lg gap-2.5',
  };

  const isDisabled = disabled || loading;

  return (
    <button
      type={type}
      disabled={isDisabled}
      title={title}
      onClick={onClick}
      className={[
        'inline-flex items-center justify-center font-medium rounded-lg',
        'transition-all duration-[200ms] ease-out',
        'focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-1',
        'select-none cursor-pointer',
        'disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none',
        variantStyles[variant],
        sizeStyles[size],
        className,
      ].join(' ')}
      {...rest}
    >
      {loading ? (
        <Spinner size={size === 'sm' ? 'sm' : 'sm'} />
      ) : icon ? (
        <span className="flex-shrink-0">{icon}</span>
      ) : null}

      {children && (
        <span className={loading || icon ? '' : ''}>
          {children}
        </span>
      )}

      {iconRight && !loading && (
        <span className="flex-shrink-0">{iconRight}</span>
      )}
    </button>
  );
};

export default Button;
