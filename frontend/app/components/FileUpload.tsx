"use client";

import { useCallback, useRef, useState } from "react";

interface FileUploadProps {
  label: string;
  hint?: string;
  file: File | null;
  onFileSelected: (file: File | null) => void;
}

export default function FileUpload({
  label,
  hint,
  file,
  onFileSelected,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validateAndSet = useCallback(
    (selected: File | null) => {
      if (!selected) {
        onFileSelected(null);
        return;
      }
      const name = selected.name.toLowerCase();
      if (!name.endsWith(".pdf") && !name.endsWith(".txt")) {
        setError("Only PDF or TXT files are supported.");
        onFileSelected(null);
        return;
      }
      if (selected.size > 10 * 1024 * 1024) {
        setError("File exceeds the 10 MB limit.");
        onFileSelected(null);
        return;
      }
      setError(null);
      onFileSelected(selected);
    },
    [onFileSelected]
  );

  return (
    <div>
      <label className="mb-1.5 block text-sm font-semibold text-slate-700">
        {label}
      </label>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            inputRef.current?.click();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          validateAndSet(event.dataTransfer.files?.[0] ?? null);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition ${
          dragActive
            ? "border-indigo-500 bg-indigo-50"
            : "border-slate-300 bg-white hover:border-indigo-400 hover:bg-indigo-50/40"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt"
          className="hidden"
          onChange={(event) =>
            validateAndSet(event.target.files?.[0] ?? null)
          }
        />
        {file ? (
          <>
            <span className="text-sm font-medium text-emerald-600">
              ✓ {file.name}
            </span>
            <span className="mt-1 text-xs text-slate-400">Click to replace</span>
          </>
        ) : (
          <>
            <span className="text-sm font-medium text-slate-600">
              Click or drop your file here
            </span>
            <span className="mt-1 text-xs text-slate-400">
              {hint ?? "PDF or TXT, up to 10 MB"}
            </span>
          </>
        )}
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
