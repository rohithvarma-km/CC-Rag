import { useState } from 'react'
import type { Citation } from '@/lib/api'

export default function Citations({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null)
  if (citations.length === 0) return null
  return (
    <div className="mt-3 text-left" data-testid="citations">
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c, i) => (
          <button
            key={`${c.document_id}-${c.chunk_index}-${i}`}
            type="button"
            data-testid="citation-chip"
            aria-expanded={open === i}
            onClick={() => setOpen(open === i ? null : i)}
            className="max-w-full truncate rounded-full border border-border bg-secondary px-2.5 py-1 text-xs text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-expanded:border-primary/40 aria-expanded:text-foreground"
          >
            {c.filename} · {c.similarity.toFixed(2)}
          </button>
        ))}
      </div>
      {open !== null && citations[open] && (
        <p data-testid="citation-snippet" className="mt-2 max-w-2xl whitespace-pre-wrap rounded-xl border border-border bg-card p-3 text-xs leading-relaxed text-muted-foreground">
          {citations[open].snippet}
        </p>
      )}
    </div>
  )
}
