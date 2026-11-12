import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { supabase } from '@/lib/supabase'
import { createThread, deleteThread, listMessages, listThreads, streamChat, type Message, type Thread } from '@/lib/api'

export default function Chat() {
  const [threads, setThreads] = useState<Thread[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const bottom = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => setThreads(await listThreads()), [])
  useEffect(() => { refresh().catch((e) => setError(String(e))) }, [refresh])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  async function select(id: string) {
    setActive(id); setError('')
    setMessages(await listMessages(id))
  }

  async function newThread() {
    const t = await createThread()
    await refresh()
    await select(t.id)
  }

  async function remove(id: string) {
    await deleteThread(id)
    if (active === id) { setActive(null); setMessages([]) }
    await refresh()
  }

  async function send(e: React.FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || streaming) return
    let id = active
    if (!id) { id = (await createThread()).id; setActive(id) }
    setInput(''); setError(''); setStreaming(true)
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'user', content: text }, { id: 'pending', role: 'assistant', content: '' }])
    // The server persists nothing on failure, so roll back the optimistic bubbles and restore the text.
    const rollback = (msg: string) => {
      setMessages((m) => m.slice(0, -2))
      setInput(text)
      setError(msg)
    }
    try {
      await streamChat(id, text, (ev) => {
        if (ev.type === 'delta')
          setMessages((m) => m.map((x) => (x.id === 'pending' ? { ...x, content: x.content + ev.text } : x)))
        else if (ev.type === 'done')
          setMessages((m) => m.map((x) => (x.id === 'pending' ? { ...x, id: crypto.randomUUID(), citations: ev.citations } : x)))
        else rollback(ev.message)
      })
    } catch (err) {
      rollback(String(err))
    } finally {
      setStreaming(false)
      refresh()
    }
  }

  return (
    <div className="flex h-screen">
      <aside className="flex w-64 flex-col border-r p-3">
        <Button onClick={newThread} className="mb-3">New chat</Button>
        <div className="flex-1 space-y-1 overflow-y-auto">
          {threads.map((t) => (
            <div key={t.id} className={`group flex items-center rounded px-2 py-1 text-sm ${t.id === active ? 'bg-muted' : ''}`}>
              <button className="flex-1 truncate text-left" onClick={() => select(t.id)}>{t.title}</button>
              <button aria-label="Delete thread" className="opacity-0 group-hover:opacity-100" onClick={() => remove(t.id)}>✕</button>
            </div>
          ))}
        </div>
        <Button variant="outline" onClick={() => supabase.auth.signOut()}>Sign out</Button>
      </aside>
      <main className="flex flex-1 flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-6">
          {messages.length === 0 && <p className="text-center text-muted-foreground">Ask a question about your documents.</p>}
          {messages.map((m) => (
            <div key={m.id} className={m.role === 'user' ? 'text-right' : ''}>
              <div className={`inline-block max-w-2xl whitespace-pre-wrap rounded-lg px-3 py-2 text-left ${m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}>
                {m.content || (streaming && m.id === 'pending' ? '…' : '')}
              </div>
              {m.citations && m.citations.length > 0 && (
                <p className="mt-1 text-xs text-muted-foreground">Sources: {m.citations.join(', ')}</p>
              )}
            </div>
          ))}
          <div ref={bottom} />
        </div>
        {error && <p className="px-6 text-sm text-red-600">{error}</p>}
        <form onSubmit={send} className="flex gap-2 border-t p-4">
          <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type a message" disabled={streaming} />
          <Button type="submit" disabled={streaming || !input.trim()}>Send</Button>
        </form>
      </main>
    </div>
  )
}
