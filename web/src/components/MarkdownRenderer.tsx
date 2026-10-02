'use client'

import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownRendererProps {
  content: string
}

function fixOl(text: string): string {
  let n = 0
  return text.split('\n').map(line => {
    // Reset counter only on headings (new section = new numbered list)
    if (/^#{1,6}\s/.test(line)) {
      n = 0
      return line
    }
    // Renumber consecutive "1. " items within the same section (across blank lines is fine)
    if (/^1\. /.test(line)) {
      n++
      return line.replace(/^1\. /, `${n}. `)
    }
    return line
  }).join('\n')
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      components={{
        h2: ({ children }) => (
          <h2 className="text-base font-display font-bold text-insurance-blue dark:text-insurance-gold mt-4 mb-2 first:mt-0">
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm font-display font-semibold text-slate-800 dark:text-slate-200 mt-3 mb-1.5">
            {children}
          </h3>
        ),
        p: ({ children }) => (
          <p className="mb-2 last:mb-0">{children}</p>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-slate-800 dark:text-slate-100">
            {children}
          </strong>
        ),
        em: ({ children }) => (
          <em className="italic text-slate-500 dark:text-slate-400">
            {children}
          </em>
        ),
        ul: ({ children }) => (
          <ul className="list-disc list-outside pl-5 mb-2 space-y-1 marker:text-slate-400">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal list-outside pl-5 mb-2 space-y-1 marker:text-slate-400">{children}</ol>
        ),
        li: ({ children }) => (
          <li className="text-sm [&>ul]:mt-1 [&>ol]:mt-1 [&>ul]:mb-1 [&>ol]:mb-1">{children}</li>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto -mx-1 my-2 rounded-lg border border-slate-200/60 dark:border-slate-700/50">
            <table className="min-w-full text-xs">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-xs font-semibold text-slate-600 dark:text-slate-300">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-3 py-2 text-left whitespace-nowrap">{children}</th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-2 border-t border-slate-200/60 dark:border-slate-700/50 whitespace-nowrap">{children}</td>
        ),
        pre: ({ children }) => (
          <pre className="bg-slate-50 dark:bg-slate-800 rounded-lg p-3 my-2 overflow-x-auto text-xs font-mono text-slate-700 dark:text-slate-300">
            {children}
          </pre>
        ),
        code: ({ className, children }) => {
          if (className) {
            return <code className="font-mono">{children}</code>
          }
          return (
            <code className="bg-slate-100 dark:bg-slate-800 text-insurance-blue dark:text-insurance-gold text-xs px-1.5 py-0.5 rounded font-mono">
              {children}
            </code>
          )
        },
        hr: () => <hr className="border-slate-200 dark:border-slate-700 my-3" />,
        a: ({ href, children }) => (
          <a
            href={href}
            className="text-insurance-blue dark:text-insurance-gold underline underline-offset-2"
            target="_blank"
            rel="noopener noreferrer"
          >
            {children}
          </a>
        ),
      }}
    >
      {fixOl(content)}
    </Markdown>
  )
}
