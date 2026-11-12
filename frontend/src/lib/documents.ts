import { useCallback, useEffect, useState } from 'react'
import { supabase } from './supabase'
import { createDocument, deleteDocument, ingestDocument, listDocuments, type DocumentRow } from './api'

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024
const ALLOWED_EXT = ['.txt', '.md']

export function validateFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!ALLOWED_EXT.some((e) => name.endsWith(e))) return 'Only .txt and .md files are supported.'
  if (file.size === 0) return 'File is empty.'
  if (file.size > MAX_UPLOAD_BYTES) return 'File is larger than 5 MB.'
  return null
}

export async function uploadDocument(file: File): Promise<DocumentRow> {
  const problem = validateFile(file)
  if (problem) throw new Error(problem)
  const doc = await createDocument(file.name, file.size)
  try {
    const { error } = await supabase.storage.from('documents').upload(doc.storage_path, file, {
      contentType: file.type || 'text/plain',
    })
    if (error) throw new Error(`Upload failed: ${error.message}`)
    await ingestDocument(doc.id)
  } catch (e) {
    await deleteDocument(doc.id).catch(() => {})
    throw e
  }
  return doc
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
