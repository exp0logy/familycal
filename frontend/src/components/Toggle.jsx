// ─────────────────────────────────────────────────────────────────────────────
// Toggle — iOS-style switch for boolean settings.
// ─────────────────────────────────────────────────────────────────────────────

import React from 'react';

/**
 * @param {{
 *   checked: boolean,
 *   onChange: (checked: boolean) => void,
 *   disabled?: boolean,
 *   label?: string,
 *   description?: string,
 *   size?: 'sm'|'md'|'lg',
 *   className?: string,
 * }} props
 */
const Toggle = ({
  checked,
  onChange,
  disabled = false,
  label,
  description,
  size = 'md',
  className = '',
}) => {
  // ── Size tokens ────────────────────────────────────────────────────────────
  const sizeTokens = {
    sm: { track: 'w-8 h-4',    thumb: 'w-3 h-3',    translate: 'translate-x-4',  padding: 'p-0.5' },
    md: { track: 'w-11 h-6',   thumb: 'w-4.5 h-4.5',translate: 'translate-x-5',  padding: 'p-[3px]' },
    lg: { track: 'w-14 h-7.5', thumb: 'w-6 h-6',    translate: 'translate-x-6.5',padding: 'p-[3px]' },
  };
  const { track, thumb, translate, padding } = sizeTokens[size];

  const handleToggle = () => {
    if (!disabled) onChange(!checked);
  };

  const handleKeyDown = (e) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      handleToggle();
    }
  };

  const switchEl = (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={handleToggle}
      onKeyDown={handleKeyDown}
      className={[
        `relative inline-flex flex-shrink-0 ${track} rounded-full ${padding}`,
        'cursor-pointer transition-colors duration-[200ms] ease-out',
        'focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-1',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        checked
          ? 'bg-accent-500 shadow-glow-sm'
          : 'bg-surface-4',
      ].join(' ')}
    >
      <span
        className={[
          `${thumb} bg-white rounded-full shadow-md`,
          'transform transition-transform duration-[200ms] ease-spring',
          'translate-x-0',
          checked ? translate : '',
        ].join(' ')}
        aria-hidden="true"
      />
    </button>
  );

  // If there's no label, just render the switch bare
  if (!label && !description) {
    return <span className={className}>{switchEl}</span>;
  }

  return (
    <label
      className={`flex items-center justify-between gap-4 cursor-pointer ${disabled ? 'opacity-40 cursor-not-allowed' : ''} ${className}`}
      onClick={handleToggle}
    >
      <span className="flex-1 min-w-0">
        {label && (
          <span className="block text-body text-text-primary font-medium">{label}</span>
        )}
        {description && (
          <span className="block text-body-sm text-text-secondary mt-0.5">{description}</span>
        )}
      </span>
      {/* Prevent the label click from double-firing */}
      <span onClick={(e) => e.stopPropagation()}>
        {switchEl}
      </span>
    </label>
  );
};

export default Toggle;
