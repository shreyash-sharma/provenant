"use client";

import { FilePath } from "@/components/shared/FilePath";

export function RiskTable({
  files,
  selected,
  onSelect,
}: {
  files: { path: string }[];
  selected: string | null;
  onSelect: (path: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-800">
      <div className="border-b border-gray-800 bg-gray-900 px-3 py-2 text-xs uppercase tracking-wider text-gray-500">
        {files.length} indexed files
      </div>
      <div className="max-h-[calc(100vh-12rem)] overflow-y-auto bg-gray-950">
        {files.map((file) => (
          <button
            key={file.path}
            onClick={() => onSelect(file.path)}
            className={
              selected === file.path
                ? "block w-full bg-brand-600 px-3 py-2 text-left"
                : "block w-full px-3 py-2 text-left hover:bg-gray-900"
            }
          >
            <FilePath
              path={file.path}
              className={selected === file.path ? "text-white" : undefined}
            />
          </button>
        ))}
      </div>
    </div>
  );
}
