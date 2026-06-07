// ─────────────────────────────────────────────────────────────────────────────
// Spinner — animated loading indicator.
// ─────────────────────────────────────────────────────────────────────────────

import React from 'react';

/**
 * @param {{ size?: 'sm'|'md'|'lg'|'xl', className?: string }} props
 */
const Spinner = ({ size = 'md', className = '' }) => {
  const sizeMap = {
    sm:  'w-4 h-4',
    md:  'w-6 h-6',
    lg:  'w-10 h-10',
    xl:  'w-16 h-16',
  };
  const strokeMap = {
    sm:  '2.5',
    md:  '2.5',
    lg:  '2',
    xl:  '1.5',
  };

  return (
    <svg
      className={`${sizeMap[size]} animate-spin text-accent-500 ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Loading"
      role="status"
    >
      {/* Track ring */}
      <circle
        cx="12" cy="12" r="10"
        stroke="currentColor"
        strokeOpacity="0.15"
        strokeWidth={strokeMap[size]}
      />
      {/* Spinning arc */}
      <path
        d="M12 2a10 10 0 019.391 6.598"
        stroke="currentColor"
        strokeWidth={strokeMap[size]}
        strokeLinecap="round"
      />
    </svg>
  );
};

export default Spinner;
