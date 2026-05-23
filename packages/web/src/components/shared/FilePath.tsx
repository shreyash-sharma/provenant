import { FileCode2 } from "lucide-react";
import { clsx } from "clsx";

export function FilePath({
  path,
  className,
}: {
  path: string;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex min-w-0 items-center gap-1.5 font-mono text-xs text-gray-400",
        className,
      )}
      title={path}
    >
      <FileCode2 className="h-3.5 w-3.5 shrink-0 text-gray-600" />
      <span className="truncate">{path}</span>
    </span>
  );
}
