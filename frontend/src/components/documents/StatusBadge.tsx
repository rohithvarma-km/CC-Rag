import { Badge } from '@/components/ui/badge'
import type { DocumentStatus } from '@/lib/api'

const styles: Record<DocumentStatus, string> = {
  pending: 'bg-stone-200/70 text-stone-700 dark:bg-stone-500/20 dark:text-stone-300',
  processing: 'bg-amber-100 text-amber-800 animate-pulse dark:bg-amber-500/20 dark:text-amber-200',
  completed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200',
  failed: 'bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-200',
}

export default function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <Badge variant="secondary" className={`h-6 px-2.5 capitalize ${styles[status]}`} data-testid="status-badge" data-status={status}>
      {status}
    </Badge>
  )
}
