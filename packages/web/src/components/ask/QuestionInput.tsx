"use client";

import { Send } from "lucide-react";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";

export function QuestionInput({
  value,
  onChange,
  onSubmit,
  loading,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
}) {
  return (
    <div className="flex gap-2">
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
            onSubmit();
          }
        }}
        placeholder="Ask about architecture, ownership, risk, or where code lives"
        className="min-h-24 flex-1 resize-y rounded-lg border border-gray-700 bg-gray-900 px-4 py-3 text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
      />
      <button
        onClick={onSubmit}
        disabled={loading || !value.trim()}
        className="flex h-11 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white transition hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {loading ? <LoadingSpinner size={4} /> : <Send className="h-4 w-4" />}
        Ask
      </button>
    </div>
  );
}
