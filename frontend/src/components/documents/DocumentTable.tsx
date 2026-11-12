import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { DocumentRow } from '@/lib/api'
import StatusBadge from './StatusBadge'

const STALE_MS = 10 * 60 * 1000

function isStale(d: DocumentRow, now = Date.now()) {
  return d.status === 'processing' && now - new Date(d.updated_at).getTime() > STALE_MS
}

function formatSize(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

type Props = {
  documents: DocumentRow[]
  onRetry: (d: DocumentRow) => void
  onDelete: (d: DocumentRow) => void
}

export default function DocumentTable({ documents, onRetry, onDelete }: Props) {
  if (documents.length === 0)
    return <p className="rounded-2xl border border-border bg-card py-10 text-center text-sm text-muted-foreground" data-testid="no-documents">No documents yet.</p>
  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-card">
    <Table data-testid="documents-table">
      <TableHeader>
        <TableRow>
          <TableHead>Filename</TableHead>
          <TableHead>Size</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Chunks</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {documents.map((d) => (
          <TableRow key={d.id} data-testid="document-row" data-status={d.status}>
            <TableCell className="max-w-[18rem] truncate font-medium text-foreground">{d.filename}</TableCell>
            <TableCell>{formatSize(d.size_bytes)}</TableCell>
            <TableCell>
              <div className="flex flex-col items-start gap-1">
                <StatusBadge status={d.status} />
                {d.status === 'failed' && d.error && (
                  <span className="max-w-md whitespace-normal text-xs text-destructive" data-testid="document-error">{d.error}</span>
                )}
              </div>
            </TableCell>
            <TableCell>{d.chunk_count}</TableCell>
            <TableCell className="space-x-2 whitespace-nowrap text-right">
              {(d.status === 'failed' || isStale(d)) && (
                <Button size="sm" variant="outline" className="rounded-full" aria-label={`Retry ${d.filename}`} onClick={() => onRetry(d)}>Retry</Button>
              )}
              <Button size="sm" variant="destructive" className="rounded-full" aria-label={`Delete ${d.filename}`} onClick={() => onDelete(d)}>Delete</Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
    </div>
  )
}
