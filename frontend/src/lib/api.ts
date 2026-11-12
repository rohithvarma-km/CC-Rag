import { supabase } from './supabase'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Thread = { id: string; title: string; updated_at: string }
export type Message = { id: string; role: 'user' | 'assistant'; content: string; citations?: string[] }

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

export type StreamEvent =
  | { type: 'delta'; text: string }
  | { type: 'done'; citations: string[]; title: string }
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
