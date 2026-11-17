import { useCallback, useEffect, useState } from 'react'
import { supabase } from './supabase'
import {
  createDocument,
  deleteDocument,
  ingestDocument,
  listDocuments,
  type DocumentRow,
  type UploadAction,
} from './api'

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024
const ALLOWED_EXT = ['.txt', '.md']

export function validateFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!ALLOWED_EXT.some((e) => name.endsWith(e))) return 'Only .txt and .md files are supported.'
  if (file.size === 0) return 'File is empty.'
  if (file.size > MAX_UPLOAD_BYTES) return 'File is larger than 5 MB.'
  return null
}

// SHA-256 of the file bytes as lowercase hex. Needs a secure context (https or localhost).
export async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}

export type UploadOutcome = { action: UploadAction; document: DocumentRow }

export async function uploadDocument(file: File): Promise<UploadOutcome> {
  const problem = validateFile(file)
  if (problem) throw new Error(problem)
  const hash = await sha256Hex(file)
  const { action, document: doc } = await createDocument(file.name, file.size, hash)
  // Identical content already ingested (or in flight): nothing to upload or embed.
  if (action === 'unchanged') return { action, document: doc }
  try {
    const { error } = await supabase.storage.from('documents').upload(doc.storage_path, file, {
      contentType: file.type || 'text/plain',
      upsert: true, // updated/retry reuse the same storage object
    })
    if (error) throw new Error(`Upload failed: ${error.message}`)
    await ingestDocument(doc.id)
  } catch (e) {
    // Only remove a row we just created. An existing document keeps its row; a failed re-upload can be retried.
    if (action === 'created') await deleteDocument(doc.id).catch(() => {})
    throw e
  }
  return { action, document: doc }
}

const byNewest = (a: DocumentRow, b: DocumentRow) => b.created_at.localeCompare(a.created_at)

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(async () => {
    try {
      setDocuments((await listDocuments()).sort(byNewest))
      setError('')
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let channel: ReturnType<typeof supabase.channel> | null = null
    ;(async () => {
      const { data } = await supabase.auth.getSession()
      const uid = data.session?.user.id
      if (cancelled) return
      await refetch()
      if (!uid || cancelled) return
      channel = supabase
        .channel(`documents-${uid}-${crypto.randomUUID()}`)
        .on(
          'postgres_changes',
          { event: '*', schema: 'public', table: 'documents', filter: `user_id=eq.${uid}` },
          (payload) => {
            if (payload.eventType === 'DELETE') {
              const id = (payload.old as Partial<DocumentRow>).id
              setDocuments((d) => d.filter((x) => x.id !== id))
            } else {
              const row = payload.new as DocumentRow
              setDocuments((d) => [row, ...d.filter((x) => x.id !== row.id)].sort(byNewest))
            }
          },
        )
        .subscribe((status) => {
          if (status === 'SUBSCRIBED') refetch()
        })
      if (cancelled) supabase.removeChannel(channel)
    })()
    return () => {
      cancelled = true
      if (channel) supabase.removeChannel(channel)
    }
  }, [refetch])

  return { documents, loading, error, refetch }
}
