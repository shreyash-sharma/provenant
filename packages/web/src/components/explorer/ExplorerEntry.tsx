import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ContextTarget } from "@/lib/types";
import { CodeBlock } from "@/components/shared/CodeBlock";
import { ErrorBanner } from "@/components/shared/ErrorBanner";
import { FilePath } from "@/components/shared/FilePath";

export function ExplorerEntry({ entry }: { entry: ContextTarget }) {
  const docs = entry.docs;
  const markdown = docs?.content_md ?? docs?.documentation;
  const source = entry.source;

  return (
    <div className="space-y-4">
      {entry.error && <ErrorBanner message={entry.error} />}
      {entry.suggestions?.length ? (
        <Panel title="Suggestions">
          <div className="flex flex-wrap gap-2">
            {entry.suggestions.map((path) => (
              <span key={path} className="rounded-md border border-gray-800 bg-gray-950 px-2 py-1">
                <FilePath path={path} />
              </span>
            ))}
          </div>
        </Panel>
      ) : null}
      {docs?.summary && (
        <Panel title={docs.title || "Summary"}>
          <p className="text-sm leading-relaxed text-gray-300">{docs.summary}</p>
        </Panel>
      )}
      {docs?.symbols?.length ? (
        <Panel title="Symbols">
          <div className="space-y-2">
            {docs.symbols.slice(0, 20).map((symbol) => (
              <div
                key={`${symbol.kind}-${symbol.name}-${symbol.start_line ?? ""}`}
                className="grid grid-cols-[7rem_1fr_auto] gap-3 rounded-lg border border-gray-800 bg-gray-950 px-3 py-2 text-xs"
              >
                <span className="text-gray-500">{symbol.kind}</span>
                <span className="truncate font-mono text-gray-200">
                  {symbol.signature || symbol.name}
                </span>
                <span className="font-mono text-gray-600">
                  {symbol.start_line ? `L${symbol.start_line}` : ""}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}
      {docs?.files?.length ? (
        <Panel title="Files">
          <div className="space-y-2">
            {docs.files.slice(0, 30).map((file) => (
              <div key={file.path} className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2">
                <FilePath path={file.path} />
              </div>
            ))}
          </div>
        </Panel>
      ) : null}
      {markdown && (
        <Panel title="Wiki Page">
          <div className="prose-provenant text-sm">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children }) {
                  const match = /language-(\w+)/.exec(className || "");
                  return match ? (
                    <CodeBlock code={String(children).replace(/\n$/, "")} language={match[1]} />
                  ) : (
                    <code className="rounded bg-gray-800 px-1 py-0.5 text-xs text-brand-100">
                      {children}
                    </code>
                  );
                },
              }}
            >
              {markdown}
            </ReactMarkdown>
          </div>
        </Panel>
      )}
      {source?.error && <ErrorBanner message={source.error} />}
      {source?.body && (
        <Panel title={`Source ${source.start_line ? `L${source.start_line}` : ""}`}>
          <CodeBlock code={source.body} language={source.language || "text"} />
        </Panel>
      )}
      {entry.freshness && (
        <Panel title="Freshness">
          <div className="grid grid-cols-3 gap-3 text-xs">
            <Fact label="Status" value={entry.freshness.freshness_status} />
            <Fact label="Confidence" value={entry.freshness.confidence_score} />
            <Fact label="Stale" value={entry.freshness.is_stale ? "yes" : "no"} />
          </div>
        </Panel>
      )}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-gray-800 bg-gray-900 p-5">
      <p className="mb-3 text-xs font-medium uppercase tracking-wider text-gray-500">
        {title}
      </p>
      {children}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950 p-3">
      <p className="mb-1 text-gray-500">{label}</p>
      <p className="truncate font-mono text-gray-200">{String(value ?? "-")}</p>
    </div>
  );
}
