// ─────────────────────────────────────────────────────────────────────────────
// TextInput — labelled input field with optional prefix icon and error state.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useId } from 'react';

/**
 * @param {{
 *   label?: string,
 *   description?: string,
 *   error?: string,
 *   icon?: React.ReactNode,
 *   iconRight?: React.ReactNode,
 *   type?: string,
 *   value: string,
 *   onChange: (e: React.ChangeEvent<HTMLInputElement>) => void,
 *   placeholder?: string,
 *   disabled?: boolean,
 *   required?: boolean,
 *   autoFocus?: boolean,
 *   className?: string,
 *   inputClassName?: string,
 *   name?: string,
 *   id?: string,
 * }} props
 */
const TextInput = ({
  label,
  description,
  error,
  icon,
  iconRight,
  type = 'text',
  value,
  onChange,
  placeholder,
  disabled = false,
  required = false,
  autoFocus = false,
  className = '',
  inputClassName = '',
  name,
  id: idProp,
  ...rest
}) => {
  const generatedId = useId();
  const id = idProp ?? generatedId;

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {label && (
        <label htmlFor={id} className="text-body-sm font-medium text-text-secondary flex items-center gap-1">
          {label}
          {required && <span className="text-error text-caption">*</span>}
        </label>
      )}

      <div className="relative flex items-center">
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none">
            {icon}
          </span>
        )}

        <input
          id={id}
          name={name}
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          autoFocus={autoFocus}
          className={[
            'w-full input-base',
            icon ? 'pl-10' : '',
            iconRight ? 'pr-10' : '',
            error ? 'border-error focus:border-error focus:ring-error/50' : '',
            disabled ? 'opacity-50 cursor-not-allowed' : '',
            inputClassName,
          ].join(' ')}
          {...rest}
        />

        {iconRight && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">
            {iconRight}
          </span>
        )}
      </div>

      {description && !error && (
        <p className="text-caption text-text-muted">{description}</p>
      )}

      {error && (
        <p className="text-caption text-error flex items-center gap-1" role="alert">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5 flex-shrink-0">
            <circle cx="12" cy="12" r="10" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4M12 16h.01" />
          </svg>
          {error}
        </p>
      )}
    </div>
  );
};

export default TextInput;
