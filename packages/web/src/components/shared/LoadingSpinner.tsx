import { Loader2 } from "lucide-react";

export function LoadingSpinner({ size = 5 }: { size?: number }) {
  return (
    <Loader2
      className="animate-spin text-brand-500"
      style={{ width: `${size * 0.25}rem`, height: `${size * 0.25}rem` }}
      aria-label="Loading"
    />
  );
}
