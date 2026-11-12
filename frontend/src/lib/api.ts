import { supabase } from './supabase'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Thread = { id: string; title: string; updated_at: string }
export type Citation = { document_id: string; filename: string; chunk_index: number; snippet: string; similarity: number }
export type Message = { id: string; role: 'user' | 'assistant'; content: string; citations?: Citation[] }
export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'failed'
export type DocumentRow = {
  id: string
  filename: string
  status: DocumentStatus
  error: string | null
  chunk_count: number
  size_bytes: number
  storage_path: string
  created_at: string
  updated_at: string
}

async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  return { Authorization: `Bearer ${data.session?.access_token ?? ''}`, 'Content-Type': 'application/json' }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...(await authHeaders()), ...init.headers } })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.status === 204 ? (undefined as T) : res.json()
}

export const listThreads = () => req<Thread[]>('/threads')
export const createThread = () => req<Thread>('/threads', { method: 'POST', body: JSON.stringify({}) })
export const deleteThread = (id: string) => req<void>(`/threads/${id}`, { method: 'DELETE' })
export const listMessages = (id: string) => req<Message[]>(`/threads/${id}/messages`)

export const listDocuments = () => req<DocumentRow[]>('/documents')
export const createDocument = (filename: string, size_bytes: number) =>
  req<DocumentRow>('/documents', { method: 'POST', body: JSON.stringify({ filename, size_bytes }) })
export const ingestDocument = (id: string) => req<void>(`/documents/${id}/ingest`, { method: 'POST' })
export const deleteDocument = (id: string) => req<void>(`/documents/${id}`, { method: 'DELETE' })

export type StreamEvent =
  | { type: 'tool'; name: string }
  | { type: 'delta'; text: string }
  | { type: 'done'; citations: Citation[]; title: string }
  | { type: 'error'; message: string }

// SSE over fetch (EventSource can't send the auth header).
export async function streamChat(id: string, message: string, onEvent: (e: StreamEvent) => void) {
  const res = await fetch(`${API}/threads/${id}/chat`, {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ message }),
  })
  if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop() ?? ''
    for (const p of parts) if (p.startsWith('data: ')) onEvent(JSON.parse(p.slice(6)))
  }
}
