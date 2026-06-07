// ─────────────────────────────────────────────────────────────────────────────
// Card — surface container with header, padding, and optional variants.
// ─────────────────────────────────────────────────────────────────────────────

import React from 'react';

/**
 * @param {{
 *   children: React.ReactNode,
 *   title?: React.ReactNode,
 *   subtitle?: string,
 *   actions?: React.ReactNode,
 *   variant?: 'default'|'elevated'|'glass'|'flat',
 *   padding?: 'none'|'sm'|'md'|'lg',
 *   className?: string,
 *   onClick?: () => void,
 * }} props
 */
const Card = ({
  children,
  title,
  subtitle,
  actions,
  variant = 'default',
  padding = 'md',
  className = '',
  onClick,
}) => {
  const variantClass = {
    default:  'card-base',
    elevated: 'card-elevated',
    glass:    'card-glass',
    flat:     'bg-surface-1 rounded-card border border-surface-4/30',
  }[variant];

  const paddingClass = {
    none: '',
    sm:   'p-3',
    md:   'p-5',
    lg:   'p-7',
  }[padding];

  const interactiveClass = onClick
    ? 'cursor-pointer hover:border-surface-5 transition-colors duration-[200ms] active:scale-[0.99] transition-transform'
    : '';

  const hasHeader = title || subtitle || actions;

  return (
    <div
      className={`${variantClass} overflow-hidden ${interactiveClass} ${className}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); } : undefined}
    >
      {hasHeader && (
        <div className={`flex items-start justify-between gap-3 ${padding !== 'none' ? paddingClass : 'p-5'} ${children ? 'pb-0' : ''}`}>
          {(title || subtitle) && (
            <div className="min-w-0">
              {title && (
                <h3 className="text-title text-text-primary font-semibold leading-tight truncate-1">
                  {title}
                </h3>
              )}
              {subtitle && (
                <p className="text-body-sm text-text-secondary mt-0.5">{subtitle}</p>
              )}
            </div>
          )}
          {actions && (
            <div className="flex items-center gap-2 flex-shrink-0">
              {actions}
            </div>
          )}
        </div>
      )}
      {children && (
        <div className={padding !== 'none' ? paddingClass : ''}>
          {children}
        </div>
      )}
    </div>
  );
};

export default Card;
