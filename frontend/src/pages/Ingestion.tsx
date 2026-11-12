import { useState } from 'react'
import DocumentTable from '@/components/documents/DocumentTable'
import DropZone from '@/components/documents/DropZone'
import { deleteDocument, ingestDocument, type DocumentRow } from '@/lib/api'
import { uploadDocument, useDocuments, validateFile } from '@/lib/documents'

export default function Ingestion() {
  const { documents, loading, error: loadError, refetch } = useDocuments()
  const [errors, setErrors] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  async function onFiles(files: File[]) {
    const errs: string[] = []
    const ok: File[] = []
    for (const f of files) {
      const problem = validateFile(f)
      if (problem) errs.push(`${f.name}: ${problem}`)
      else ok.push(f)
    }
    setErrors(errs)
    if (!ok.length) return
    setBusy(true)
    for (const f of ok) {
      try {
        await uploadDocument(f)
      } catch (e) {
        errs.push(`${f.name}: ${e instanceof Error ? e.message : String(e)}`)
        setErrors([...errs])
      }
    }
    setBusy(false)
    refetch()
  }

  async function onRetry(d: DocumentRow) {
    try {
      await ingestDocument(d.id)
      setErrors([])
    } catch (e) {
      setErrors([`${d.filename}: ${e instanceof Error ? e.message : String(e)}`])
    }
    refetch()
  }

  async function onDelete(d: DocumentRow) {
    if (!window.confirm(`Delete "${d.filename}" and its chunks?`)) return
    try {
      await deleteDocument(d.id)
      setErrors([])
    } catch (e) {
      setErrors([`${d.filename}: ${e instanceof Error ? e.message : String(e)}`])
    }
    refetch()
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-6 px-4 py-10 sm:px-6">
        <div className="space-y-1.5">
          <h1 className="text-3xl">Documents</h1>
          <p className="text-sm text-muted-foreground">Upload text and Markdown files. They are split into chunks so the assistant can search them when you chat.</p>
        </div>
        <DropZone onFiles={onFiles} busy={busy} />
        {errors.length > 0 && (
          <ul role="alert" data-testid="upload-error" className="space-y-1 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        )}
        {loadError && <p className="text-sm text-destructive">{loadError}</p>}
        {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : <DocumentTable documents={documents} onRetry={onRetry} onDelete={onDelete} />}
      </div>
    </div>
  )
}
