import { FilePath } from "@/components/shared/FilePath";

export function CitationList({ citations }: { citations: string[] }) {
  if (!citations.length) return null;

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
        Citations
      </p>
      <div className="flex flex-wrap gap-2">
        {citations.map((path) => (
          <span
            key={path}
            className="max-w-full rounded-md border border-gray-800 bg-gray-950 px-2 py-1"
          >
            <FilePath path={path} />
          </span>
        ))}
      </div>
    </div>
  );
}
