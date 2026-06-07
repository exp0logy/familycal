// ─────────────────────────────────────────────────────────────────────────────
// Icon — inline SVG icon set.
// Usage: <Icon name="calendar" className="w-5 h-5 text-text-secondary" />
// All paths are 24×24 viewBox, 2px stroke, rounded caps/joins.
// ─────────────────────────────────────────────────────────────────────────────

import React from 'react';

// Icon path registry.  Keys are the icon name strings used in <Icon name="…"/>.
const ICONS = {
  // Navigation / UI
  home: (
    <path
      strokeLinecap="round" strokeLinejoin="round"
      d="M3 12l9-9 9 9M5 10v9a1 1 0 001 1h4v-5h4v5h4a1 1 0 001-1v-9"
    />
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path
        strokeLinecap="round" strokeLinejoin="round"
        d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"
      />
    </>
  ),
  'chevron-right': (
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" />
  ),
  'chevron-left': (
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 18l-6-6 6-6" />
  ),
  'chevron-down': (
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" />
  ),
  'chevron-up': (
    <path strokeLinecap="round" strokeLinejoin="round" d="M18 15l-6-6-6 6" />
  ),
  close: (
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  ),
  check: (
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  ),
  plus: (
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14M5 12h14" />
  ),
  trash: (
    <path
      strokeLinecap="round" strokeLinejoin="round"
      d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"
    />
  ),
  edit: (
    <path
      strokeLinecap="round" strokeLinejoin="round"
      d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"
    />
  ),
  refresh: (
    <path
      strokeLinecap="round" strokeLinejoin="round"
      d="M4 4v5h5M20 20v-5h-5M20.49 9A9 9 0 115.64 5.64M3.51 15A9 9 0 0018.36 18.36"
    />
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="8" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35" />
    </>
  ),
  'arrow-left': (
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 12H5M12 19l-7-7 7-7" />
  ),
  'external-link': (
    <path
      strokeLinecap="round" strokeLinejoin="round"
      d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"
    />
  ),
  // Content
  calendar: (
    <>
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 2v4M8 2v4M3 10h18" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2" />
    </>
  ),
  cloud: (
    <path
      strokeLinecap="round" strokeLinejoin="round"
      d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z"
    />
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="5" />
      <path
        strokeLinecap="round" strokeLinejoin="round"
        d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"
      />
    </>
  ),
  image: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 15l-5-5L5 21" />
    </>
  ),
  photos: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 15l-5-5L5 21" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M1 17h4" opacity="0" />
    </>
  ),
  // People / Profiles
  user: (
    <>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </>
  ),
  users: (
    <>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" />
    </>
  ),
  // System / Status
  wifi: (
    <>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 12.55a11 11 0 0114.08 0" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M1.42 9a16 16 0 0121.16 0" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.53 16.11a6 6 0 016.95 0" />
      <circle cx="12" cy="20" r="1" />
    </>
  ),
  'wifi-off': (
    <>
      <path strokeLinecap="round" strokeLinejoin="round" d="M1 1l22 22M16.72 11.06A10.94 10.94 0 0119 12.55M5 12.55a10.94 10.94 0 015.17-2.39M10.71 5.05A16 16 0 0122.56 9M1.42 9a15.91 15.91 0 014.7-2.88M8.53 16.11a6 6 0 016.95 0" />
      <circle cx="12" cy="20" r="1" />
    </>
  ),
  warning: (
    <>
      <path strokeLinecap="round" strokeLinejoin="round" d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4M12 17h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4M12 16h.01" />
    </>
  ),
  // Connectivity
  link: (
    <path
      strokeLinecap="round" strokeLinejoin="round"
      d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"
    />
  ),
  'link-off': (
    <path
      strokeLinecap="round" strokeLinejoin="round"
      d="M18.84 12.25l1.72-1.71a4.91 4.91 0 010-6.92A4.92 4.92 0 0113.49 7l-1.72 1.71M5.17 11.75l-1.72 1.71a4.91 4.91 0 000 6.92 4.92 4.92 0 006.92 0l1.72-1.71M1 1l22 22"
    />
  ),
  google: (
    // Simplified Google "G" mark as SVG path
    <path
      strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5"
      d="M20.64 12.2c0-.638-.057-1.252-.164-1.84H12v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
      fill="currentColor" stroke="none"
    />
  ),
  plugin: (
    <path
      strokeLinecap="round" strokeLinejoin="round"
      d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"
    />
  ),
  'map-pin': (
    <>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
      <circle cx="12" cy="10" r="3" />
    </>
  ),
};

/**
 * @param {{ name: string, className?: string, 'aria-label'?: string }} props
 */
const Icon = ({ name, className = 'w-5 h-5', 'aria-label': ariaLabel, ...rest }) => {
  const paths = ICONS[name];
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel ? undefined : 'true'}
      role={ariaLabel ? 'img' : undefined}
      {...rest}
    >
      {paths ?? (
        // Unknown icon: render a question-mark circle as fallback
        <>
          <circle cx="12" cy="12" r="10" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3M12 17h.01" />
        </>
      )}
    </svg>
  );
};

export default Icon;
