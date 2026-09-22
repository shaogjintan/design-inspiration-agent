"use client";

import { useRef, useState } from "react";
import { UploadedImage } from "@/lib/types";
import { fileToDataUrl, uid, cx } from "@/lib/utils";

export function ImageDropzone({
  images,
  onChange,
}: {
  images: UploadedImage[];
  onChange: (images: UploadedImage[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const next: UploadedImage[] = [];
    for (const file of Array.from(files)) {
      const dataUrl = await fileToDataUrl(file);
      next.push({ id: uid("img"), name: file.name, dataUrl });
    }
    onChange([...images, ...next]);
  }

  return (
    <div>
      <div className="flex flex-wrap gap-3 mb-3">
        {images.map((img) => (
          <div key={img.id} className="relative h-24 w-24 shrink-0 rounded-xl overflow-hidden border border-stone-200 group">
            <img src={img.dataUrl} alt={img.name} className="h-full w-full object-cover" />
            <button
              type="button"
              onClick={() => onChange(images.filter((i) => i.id !== img.id))}
              className="absolute top-1 right-1 h-5 w-5 rounded-full bg-black/60 text-white text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
              aria-label="Remove image"
            >
              ×
            </button>
          </div>
        ))}
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
            "h-24 w-24 shrink-0 rounded-xl border-2 border-dashed flex flex-col items-center justify-center text-stone-400 hover:text-stone-600 transition-colors",
            dragOver ? "border-amber-600 bg-amber-50" : "border-stone-300 hover:border-stone-400"
          )}
        >
          <span className="text-xl leading-none">+</span>
          <span className="text-[10px] mt-1">Add inspo</span>
        </button>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </div>
  );
}
