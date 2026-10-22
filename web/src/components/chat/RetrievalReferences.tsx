'use client'

import type { RetrievalCitation } from '@/lib/chatTypes'


function metric(citation: RetrievalCitation): string {
  if (citation.mode === 'vector') {
    return `${Math.round(citation.vector.similarity * 100)}% match`
  }
  const count = citation.keyword.matched_terms.length
  return `${count} matched ${count === 1 ? 'term' : 'terms'}`
}

function Detail({ label, value }: { label: string; value?: string | number | null }) {
  if (value === undefined || value === null || value === '') return null
  return (
    <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-2 py-1">
      <dt className="text-[10px] font-medium uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">{label}</dt>
      <dd className="break-words text-[11px] text-slate-700 dark:text-slate-300">{value}</dd>
    </div>
  )
}

function ReferenceCard({ citation }: { citation: RetrievalCitation }) {
  return (
    <details className="group overflow-hidden rounded-xl border border-slate-200/80 bg-slate-50/70 transition-all open:col-span-full open:bg-white open:shadow-lg dark:border-slate-700/80 dark:bg-slate-900/45 dark:open:bg-slate-900/80">
      <summary className="flex min-h-[82px] cursor-pointer list-none items-start gap-3 p-3.5 outline-none hover:bg-white/80 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-insurance-gold/50 dark:hover:bg-slate-800/70 [&::-webkit-details-marker]:hidden">
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ring-1 ${
          citation.mode === 'vector'
            ? 'bg-violet-500/10 text-violet-600 ring-violet-500/20 dark:text-violet-300'
            : 'bg-sky-500/10 text-sky-600 ring-sky-500/20 dark:text-sky-300'
        }`}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6M8 13h8M8 17h5" />
          </svg>
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-semibold text-slate-800 dark:text-slate-100" title={citation.file_name}>
            {citation.file_name}
          </span>
          <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span className={`rounded-md px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.08em] ${
              citation.mode === 'vector'
                ? 'bg-violet-500/10 text-violet-600 dark:text-violet-300'
                : 'bg-sky-500/10 text-sky-600 dark:text-sky-300'
            }`}>{citation.mode}</span>
            <span className="text-[10px] font-medium text-slate-500 dark:text-slate-400">{metric(citation)}</span>
          </span>
          {citation.section_title && (
            <span className="mt-1 block truncate text-[10px] text-slate-400 dark:text-slate-500">
              {citation.section_title}
            </span>
          )}
        </span>
        <svg className="mt-1 shrink-0 text-slate-400 transition-transform group-open:rotate-180" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </summary>

      <div className="border-t border-slate-200/70 px-4 pb-4 pt-3 dark:border-slate-700/70">
        <dl className="grid gap-x-6 sm:grid-cols-2">
          <Detail label="File" value={citation.file_name} />
          <Detail label="Method" value={citation.mode === 'vector' ? 'Vector similarity' : 'Keyword matching'} />
          <Detail label="Knowledge base" value={citation.knowledge_base} />
          <Detail label="Tool" value={citation.tool} />
          <Detail label="Chunk" value={citation.chunk_index} />
          <Detail label="Section" value={citation.section_title} />
          <Detail label="Pages" value={citation.page_range?.join('–')} />
          <Detail label="Lines" value={citation.line_range?.join('–')} />
          <Detail label="Source path" value={citation.source_path} />
          <Detail label="Heading path" value={citation.heading_path?.join(' / ')} />
          <Detail label="Tokens" value={citation.token_count} />
          {citation.mode === 'vector' ? (
            <>
              <Detail label="Similarity" value={`${(citation.vector.similarity * 100).toFixed(1)}%`} />
              <Detail label="Distance" value={citation.vector.distance.toFixed(6)} />
              <Detail label="Result rank" value={citation.vector.rank} />
              <Detail label="Embedding" value={citation.vector.embedding_model} />
            </>
          ) : (
            <>
              <Detail label="Query terms" value={citation.keyword.query_terms.join(', ')} />
              <Detail label="Matched terms" value={citation.keyword.matched_terms.join(', ') || 'No literal term recorded'} />
            </>
          )}
        </dl>
        <div className="mt-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-400 dark:text-slate-500">Retrieved content</p>
          <div className="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200/70 bg-slate-50/80 p-3 text-[11px] leading-relaxed text-slate-600 dark:border-slate-700/70 dark:bg-slate-950/50 dark:text-slate-300">
            {citation.content_excerpt}
          </div>
        </div>
      </div>
    </details>
  )
}


export function RetrievalReferences({ citations }: { citations: RetrievalCitation[] }) {
  if (!citations.length) return null
  return (
    <section className="mt-4 border-t border-slate-200/70 pt-3 dark:border-slate-700/70" aria-label="Retrieved references">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">References</span>
          <span className="rounded-full bg-slate-200/70 px-1.5 py-0.5 text-[9px] font-semibold text-slate-500 dark:bg-slate-700 dark:text-slate-300">{citations.length}</span>
        </div>
        <span className="text-[9px] text-slate-400 dark:text-slate-500">Click a source to inspect</span>
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(190px,1fr))] gap-2.5">
        {citations.map((citation, index) => (
          <ReferenceCard key={`${citation.citation_id}-${index}`} citation={citation} />
        ))}
      </div>
    </section>
  )
}
