import { AlertCircle } from "lucide-react";

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-200">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
      <span>{message}</span>
    </div>
  );
}
