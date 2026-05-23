"use client";

import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

export function CodeBlock({
  code,
  language = "text",
}: {
  code: string;
  language?: string;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-800 bg-gray-900">
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          background: "transparent",
          fontSize: "12px",
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
