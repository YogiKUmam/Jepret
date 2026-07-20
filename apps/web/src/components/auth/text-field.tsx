"use client";

import type { InputHTMLAttributes } from "react";

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export function TextField({ label, error, id, ...props }: TextFieldProps) {
  const describedBy = error ? `${id}-error` : undefined;
  return (
    <div className="mt-4">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className="mt-1 min-h-11 w-full rounded-xl border border-[var(--border)] bg-white px-4"
        {...props}
      />
      {error ? (
        <p
          id={describedBy}
          role="alert"
          className="mt-1 text-sm text-[var(--destructive)]"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
