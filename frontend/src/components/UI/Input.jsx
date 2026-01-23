// frontend/src/components/UI/Input.jsx
import React from 'react';

function Input({
  label,
  type = 'text',
  value,
  onChange,
  error,
  required = false,
  placeholder = '',
  className = '',
  ...props
}) {
  return (
    <div className={`form-group ${className}`}>
      {label && (
        <label className="form-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className={`form-input ${error ? 'form-input-error' : ''}`}
        required={required}
        {...props}
      />
      {error && <span className="form-error">{error}</span>}
    </div>
  );
}

export default Input;