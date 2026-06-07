// ─────────────────────────────────────────────────────────────────────────────
// Modal — accessible dialog overlay with focus trap and keyboard dismissal.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import Icon from './Icon';
import Button from './Button';

/**
 * @param {{
 *   open: boolean,
 *   onClose: () => void,
 *   title?: string,
 *   children: React.ReactNode,
 *   footer?: React.ReactNode,
 *   size?: 'sm'|'md'|'lg'|'xl'|'full',
 *   showClose?: boolean,
 *   className?: string,
 * }} props
 */
const Modal = ({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  showClose = true,
  className = '',
}) => {
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);

  // ── Width map ──────────────────────────────────────────────────────────────
  const widthMap = {
    sm:   'max-w-sm',
    md:   'max-w-lg',
    lg:   'max-w-2xl',
    xl:   'max-w-4xl',
    full: 'max-w-[95vw]',
  };

  // ── Close on backdrop click ────────────────────────────────────────────────
  const handleBackdrop = useCallback((e) => {
    if (e.target === e.currentTarget) onClose();
  }, [onClose]);

  // ── Close on Escape ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // ── Focus first focusable child when opened ────────────────────────────────
  useEffect(() => {
    if (!open) return;
    // Give the animation a frame to render before focusing
    const raf = requestAnimationFrame(() => {
      const el = dialogRef.current;
      if (!el) return;
      const focusable = el.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      (focusable[0] ?? el)?.focus();
    });
    return () => cancelAnimationFrame(raf);
  }, [open]);

  // ── Trap scroll while open ─────────────────────────────────────────────────
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      onClick={handleBackdrop}
      aria-modal="true"
      role="dialog"
      aria-labelledby={title ? 'modal-title' : undefined}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm animate-fade-in" aria-hidden="true" />

      {/* Dialog panel */}
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={[
          'relative w-full card-elevated animate-scale-in',
          'flex flex-col max-h-[90dvh]',
          widthMap[size],
          className,
        ].join(' ')}
      >
        {/* Header */}
        {(title || showClose) && (
          <div className="flex items-center justify-between px-6 pt-6 pb-4 flex-shrink-0">
            {title && (
              <h2 id="modal-title" className="text-title-lg text-text-primary font-semibold">
                {title}
              </h2>
            )}
            {showClose && (
              <Button
                ref={closeButtonRef}
                variant="icon"
                size="sm"
                onClick={onClose}
                title="Close"
                aria-label="Close dialog"
                className="ml-auto"
                icon={<Icon name="close" className="w-4 h-4" />}
              />
            )}
          </div>
        )}

        {/* Body — scrollable */}
        <div className="flex-1 overflow-y-auto px-6 pb-2">
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-surface-4 flex-shrink-0">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
};

export default Modal;
