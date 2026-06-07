// ─────────────────────────────────────────────────────────────────────────────
// ColorPicker — swatchboard + hex input for choosing profile/event colors.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState } from 'react';
import { PALETTE, parseHex } from '../lib/color';
import Icon from './Icon';

/**
 * @param {{
 *   value: string,              hex color string
 *   onChange: (hex: string) => void,
 *   label?: string,
 *   className?: string,
 * }} props
 */
const ColorPicker = ({ value, onChange, label, className = '' }) => {
  const [hexInput, setHexInput] = useState(value ?? '');

  // Sync the text input when value changes externally
  const handleSwatchClick = (color) => {
    setHexInput(color);
    onChange(color);
  };

  const handleHexChange = (e) => {
    const raw = e.target.value;
    setHexInput(raw);
    const candidate = raw.startsWith('#') ? raw : `#${raw}`;
    if (parseHex(candidate)) {
      onChange(candidate);
    }
  };

  // Normalise displayed hex value
  const displayValue = hexInput.startsWith('#') ? hexInput : `#${hexInput}`;

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      {label && (
        <span className="text-body-sm font-medium text-text-secondary">{label}</span>
      )}

      {/* Swatch grid */}
      <div className="grid grid-cols-6 gap-2" role="listbox" aria-label="Color palette">
        {PALETTE.map((color) => {
          const isSelected = value?.toLowerCase() === color.toLowerCase();
          return (
            <button
              key={color}
              type="button"
              role="option"
              aria-selected={isSelected}
              title={color}
              onClick={() => handleSwatchClick(color)}
              className={[
                'w-9 h-9 rounded-lg transition-all duration-[150ms]',
                'focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-2',
                isSelected
                  ? 'ring-2 ring-white ring-offset-2 ring-offset-surface-2 scale-110'
                  : 'hover:scale-105 hover:ring-1 hover:ring-white/30',
              ].join(' ')}
              style={{ backgroundColor: color }}
            >
              {isSelected && (
                <Icon
                  name="check"
                  className="w-4 h-4 mx-auto"
                  style={{ color: '#fff', filter: 'drop-shadow(0 1px 1px rgba(0,0,0,0.5))' }}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* Hex input + preview */}
      <div className="flex items-center gap-2">
        {/* Color preview swatch */}
        <span
          className="w-9 h-9 rounded-lg border border-surface-4 flex-shrink-0"
          style={{ backgroundColor: value ?? '#6366f1' }}
          aria-hidden="true"
        />

        {/* Hex text input */}
        <div className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted text-body-sm select-none">
            #
          </span>
          <input
            type="text"
            value={displayValue.replace('#', '')}
            onChange={handleHexChange}
            maxLength={7}
            placeholder="6366f1"
            spellCheck={false}
            className="w-full input-base pl-7 font-mono text-body-sm uppercase"
            aria-label="Hex color value"
          />
        </div>
      </div>
    </div>
  );
};

export default ColorPicker;
