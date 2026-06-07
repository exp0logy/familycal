// ─────────────────────────────────────────────────────────────────────────────
// OnScreenKeyboard — a self-contained touch keyboard for kiosk / touchscreen use.
//
// Mounted once at the app root. It auto-appears when a text field is focused via
// TOUCH (so it never gets in the way of mouse/desktop use), injects characters at
// the caret of the focused <input>/<textarea>, and fires native input events so
// React controlled components update correctly.
//
// No dependencies; works in any browser/OS regardless of Windows touch-keyboard
// settings.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Icon from './Icon';

// Input types that accept free text (and thus warrant the keyboard).
const TEXT_INPUT_TYPES = new Set([
  'text', 'search', 'email', 'url', 'tel', 'password', 'number', '',
]);

function isEditable(el) {
  if (!el || el.disabled || el.readOnly) return false;
  const tag = el.tagName;
  if (tag === 'TEXTAREA') return true;
  if (tag === 'INPUT') return TEXT_INPUT_TYPES.has((el.type || '').toLowerCase());
  return false;
}

// Set a value through the native setter + dispatch 'input' so React's onChange runs.
function setNativeValue(el, value) {
  const proto =
    el.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

// Some input types (number, email) don't support selection — guard against that.
function getSelection(el) {
  try {
    if (el.selectionStart != null) return [el.selectionStart, el.selectionEnd];
  } catch {
    /* selection unsupported */
  }
  const len = el.value.length;
  return [len, len];
}

function setCaret(el, pos) {
  try {
    el.setSelectionRange(pos, pos);
  } catch {
    /* selection unsupported (e.g. type=number) — ignore */
  }
}

function insertText(el, text) {
  const [start, end] = getSelection(el);
  const next = el.value.slice(0, start) + text + el.value.slice(end);
  setNativeValue(el, next);
  setCaret(el, start + text.length);
}

function deleteBack(el) {
  const [start, end] = getSelection(el);
  if (start === end) {
    if (start === 0) return;
    const next = el.value.slice(0, start - 1) + el.value.slice(end);
    setNativeValue(el, next);
    setCaret(el, start - 1);
  } else {
    const next = el.value.slice(0, start) + el.value.slice(end);
    setNativeValue(el, next);
    setCaret(el, start);
  }
}

// ── Layouts ───────────────────────────────────────────────────────────────────
// Each key: a string char, or a {k} control token.

const LETTER_ROWS = [
  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
  [{ k: 'shift' }, 'z', 'x', 'c', 'v', 'b', 'n', 'm', { k: 'back' }],
  [{ k: 'layout' }, ',', { k: 'space' }, '.', { k: 'enter' }],
];

const SYMBOL_ROWS = [
  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['@', '#', '$', '%', '&', '*', '-', '+', '(', ')'],
  ['/', ':', ';', "'", '"', '!', '?', '=', '_'],
  [{ k: 'shift', disabled: true }, '~', '\\', '|', '<', '>', '[', ']', { k: 'back' }],
  [{ k: 'layout' }, ',', { k: 'space' }, '.', { k: 'enter' }],
];

// ── Key button ─────────────────────────────────────────────────────────────────

const Key = ({ children, onTap, className = '', grow = false, ariaLabel, disabled }) => (
  <button
    type="button"
    // pointerDown + preventDefault keeps focus on the input (no blur) and gives
    // an instant, scroll-free response on touch.
    onPointerDown={(e) => {
      e.preventDefault();
      if (!disabled) onTap();
    }}
    disabled={disabled}
    aria-label={ariaLabel}
    style={{ touchAction: 'manipulation' }}
    className={[
      'flex items-center justify-center select-none rounded-lg',
      'h-12 sm:h-14 text-lg font-medium',
      'transition-colors duration-100 active:scale-[0.97]',
      disabled
        ? 'opacity-40 cursor-default'
        : 'bg-surface-3 text-text-primary hover:bg-surface-4 active:bg-accent-500 active:text-white',
      grow ? 'flex-1' : 'w-9 sm:w-11 flex-shrink-0',
      className,
    ].join(' ')}
  >
    {children}
  </button>
);

// ── Main component ─────────────────────────────────────────────────────────────

const OnScreenKeyboard = () => {
  const [visible, setVisible] = useState(false);
  const [layout, setLayout] = useState('letters'); // 'letters' | 'symbols'
  const [shift, setShift] = useState(false);
  const targetRef = useRef(null);
  const lastTouchRef = useRef(false);

  // Track whether the most recent pointer interaction was touch, so we only
  // pop the keyboard on a touchscreen (not for mouse users / dev).
  useEffect(() => {
    const onPointerDown = (e) => {
      lastTouchRef.current = e.pointerType === 'touch';
    };
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  }, []);

  // Show/hide based on focus.
  useEffect(() => {
    const onFocusIn = (e) => {
      if (isEditable(e.target) && lastTouchRef.current) {
        targetRef.current = e.target;
        setVisible(true);
        // Make sure the field isn't hidden behind the keyboard.
        setTimeout(() => {
          try {
            e.target.scrollIntoView({ block: 'center', behavior: 'smooth' });
          } catch {
            /* noop */
          }
        }, 50);
      } else if (!isEditable(e.target)) {
        // Focus moved to something non-editable (e.g. a button) — hide.
        setVisible(false);
        targetRef.current = null;
      }
    };
    const onFocusOut = () => {
      // Field blurred to nothing focusable — hide on the next tick unless focus
      // landed on another editable field.
      setTimeout(() => {
        if (!isEditable(document.activeElement)) {
          setVisible(false);
          targetRef.current = null;
        }
      }, 0);
    };
    document.addEventListener('focusin', onFocusIn);
    document.addEventListener('focusout', onFocusOut);
    return () => {
      document.removeEventListener('focusin', onFocusIn);
      document.removeEventListener('focusout', onFocusOut);
    };
  }, []);

  const press = useCallback(
    (token) => {
      const el = targetRef.current;
      if (!el) return;
      el.focus({ preventScroll: true });

      if (typeof token === 'string') {
        insertText(el, shift && layout === 'letters' ? token.toUpperCase() : token);
        return;
      }
      switch (token.k) {
        case 'back':
          deleteBack(el);
          break;
        case 'space':
          insertText(el, ' ');
          break;
        case 'shift':
          setShift((s) => !s);
          break;
        case 'layout':
          setLayout((l) => (l === 'letters' ? 'symbols' : 'letters'));
          break;
        case 'enter':
          if (el.tagName === 'TEXTAREA') {
            insertText(el, '\n');
          } else {
            // Fire Enter for any keydown handlers, then dismiss.
            el.dispatchEvent(
              new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true })
            );
            el.blur();
            setVisible(false);
            targetRef.current = null;
          }
          break;
        default:
          break;
      }
    },
    [shift, layout]
  );

  const close = useCallback(() => {
    const el = targetRef.current;
    if (el) el.blur();
    setVisible(false);
    targetRef.current = null;
  }, []);

  if (!visible) return null;

  const rows = layout === 'letters' ? LETTER_ROWS : SYMBOL_ROWS;

  const renderKey = (key, idx) => {
    if (typeof key === 'string') {
      const label = shift && layout === 'letters' ? key.toUpperCase() : key;
      return (
        <Key key={idx} onTap={() => press(key)} ariaLabel={label}>
          {label}
        </Key>
      );
    }
    switch (key.k) {
      case 'shift':
        return (
          <Key
            key={idx}
            onTap={() => press(key)}
            grow
            disabled={key.disabled}
            ariaLabel="Shift"
            className={shift ? '!bg-accent-500 !text-white' : ''}
          >
            <Icon name="chevron-up" className="w-5 h-5" />
          </Key>
        );
      case 'back':
        return (
          <Key key={idx} onTap={() => press(key)} grow ariaLabel="Backspace">
            ⌫
          </Key>
        );
      case 'layout':
        return (
          <Key key={idx} onTap={() => press(key)} grow ariaLabel="Toggle symbols" className="text-base">
            {layout === 'letters' ? '?123' : 'ABC'}
          </Key>
        );
      case 'space':
        return (
          <Key key={idx} onTap={() => press(key)} grow ariaLabel="Space" className="!flex-[4]">
            space
          </Key>
        );
      case 'enter':
        return (
          <Key key={idx} onTap={() => press(key)} grow ariaLabel="Enter">
            ⏎
          </Key>
        );
      default:
        return null;
    }
  };

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-[60] bg-surface-1/95 backdrop-blur-md border-t border-surface-4/60 shadow-card-lg animate-slide-up"
      role="group"
      aria-label="On-screen keyboard"
    >
      <div className="mx-auto max-w-4xl px-2 py-2 sm:px-4 sm:py-3">
        {/* Top bar with close */}
        <div className="flex justify-end mb-1.5">
          <button
            type="button"
            onPointerDown={(e) => {
              e.preventDefault();
              close();
            }}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md text-body-sm text-text-muted hover:text-text-primary hover:bg-surface-3/60 transition-colors"
            aria-label="Close keyboard"
            style={{ touchAction: 'manipulation' }}
          >
            Hide
            <Icon name="chevron-down" className="w-4 h-4" />
          </button>
        </div>

        {/* Rows */}
        <div className="flex flex-col gap-1.5">
          {rows.map((row, r) => (
            <div key={r} className="flex justify-center gap-1.5">
              {row.map((key, i) => renderKey(key, i))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default OnScreenKeyboard;
