// ─────────────────────────────────────────────────────────────────────────────
// StatusDot — small colored indicator for connection/sync status.
// ─────────────────────────────────────────────────────────────────────────────

import React from 'react';

const STATUS_STYLES = {
  ok:           'bg-ok',
  syncing:      'bg-info animate-pulse',
  error:        'bg-error',
  warn:         'bg-warn',
  warning:      'bg-warn',
  unconfigured: 'bg-text-muted',
  disconnected: 'bg-text-muted',
  connected:    'bg-ok',
  connecting:   'bg-info animate-pulse',
};

/**
 * @param {{
 *   status: 'ok'|'syncing'|'error'|'warn'|'unconfigured'|'disconnected'|'connected'|'connecting',
 *   size?: 'sm'|'md'|'lg',
 *   className?: string
 * }} props
 */
const StatusDot = ({ status, size = 'md', className = '' }) => {
  const sizeMap = { sm: 'w-1.5 h-1.5', md: 'w-2.5 h-2.5', lg: 'w-3.5 h-3.5' };
  const style = STATUS_STYLES[status] ?? 'bg-text-muted';

  return (
    <span
      className={`inline-block rounded-full flex-shrink-0 ${sizeMap[size]} ${style} ${className}`}
      aria-label={`Status: ${status}`}
      role="status"
    />
  );
};

export default StatusDot;
