"use client";

import { useRef, useState } from "react";
import { fileToDataUrl, uid } from "@/lib/utils";
import { UploadedImage } from "@/lib/types";
import { cx } from "@/lib/utils";

export function ImageUploadBox({
  image,
  onChange,
  label = "Upload floor plan",
  hint = "PNG, JPG — drag & drop or click to browse",
}: {
  image: UploadedImage | null;
  onChange: (image: UploadedImage | null) => void;
  label?: string;
  hint?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    const dataUrl = await fileToDataUrl(file);
    onChange({ id: uid("img"), name: file.name, dataUrl });
  }

  if (image) {
    return (
      <div className="relative overflow-hidden rounded-2xl border border-stone-200 bg-white">
        <img src={image.dataUrl} alt={image.name} className="w-full max-h-96 object-contain bg-stone-50" />
        <div className="flex items-center justify-between px-4 py-2 border-t border-stone-100 text-xs text-stone-500">
          <span className="truncate">{image.name}</span>
          <div className="flex gap-3 shrink-0">
            <button
              type="button"
              className="text-stone-500 hover:text-stone-900"
              onClick={() => inputRef.current?.click()}
            >
              Replace
            </button>
            <button
              type="button"
              className="text-red-500 hover:text-red-700"
              onClick={() => onChange(null)}
            >
              Remove
            </button>
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleFiles(e.dataTransfer.files);
      }}
      className={cx(
        "w-full rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors",
        dragOver ? "border-amber-600 bg-amber-50" : "border-stone-300 hover:border-stone-400 bg-white"
      )}
    >
      <div className="text-3xl mb-2">🗺️</div>
      <p className="font-medium text-stone-800">{label}</p>
      <p className="text-xs text-stone-400 mt-1">{hint}</p>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </button>
  );
}
