import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import Citations from '@/components/chat/Citations'
import { createThread, listMessages, streamChat, type Message } from '@/lib/api'
import { useThreads } from '@/lib/threads'

export default function Chat() {
  const { activeThreadId: active, setActiveThreadId, refresh } = useThreads()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const [searching, setSearching] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  // Id of a thread this page just created lazily; its optimistic messages must not be overwritten by a load.
  const skipLoad = useRef<string | null>(null)

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  useEffect(() => {
    if (active && skipLoad.current === active) { skipLoad.current = null; return }
    if (!active) { setMessages([]); return }
    let alive = true
    setError('')
    listMessages(active).then((m) => { if (alive) setMessages(m) }).catch((e) => { if (alive) setError(String(e)) })
    return () => { alive = false }
  }, [active])

  async function send(e: React.FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || streaming) return
    let id = active
    if (!id) { id = (await createThread()).id; skipLoad.current = id; setActiveThreadId(id) }
    setInput(''); setError(''); setStreaming(true)
    const userId = crypto.randomUUID()
    const pendingId = `pending-${crypto.randomUUID()}`
    setMessages((m) => [...m, { id: userId, role: 'user', content: text }, { id: pendingId, role: 'assistant', content: '' }])
    // The server persists nothing on failure, so roll back only the optimistic bubbles (by temp id) and restore the text.
    const rollback = (msg: string) => {
      setMessages((m) => m.filter((x) => x.id !== userId && x.id !== pendingId))
      setInput(text)
      setError(msg)
    }
    try {
      await streamChat(id, text, (ev) => {
        if (ev.type === 'tool') setSearching(true)
        else if (ev.type === 'delta') {
          setSearching(false)
          setMessages((m) => m.map((x) => (x.id === pendingId ? { ...x, content: x.content + ev.text } : x)))
        } else if (ev.type === 'done') {
          setSearching(false)
          setMessages((m) => m.map((x) => (x.id === pendingId ? { ...x, id: crypto.randomUUID(), citations: ev.citations } : x)))
        } else {
          setSearching(false)
          rollback(ev.message)
        }
      })
    } catch (err) {
      rollback(String(err))
    } finally {
      setSearching(false)
      setStreaming(false)
      refresh().catch(() => {})
    }
  }

  return (
    <div className="flex h-full flex-col">
      <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
        <div className="flex-1 overflow-y-auto">
          <div className={`mx-auto w-full max-w-3xl space-y-6 px-4 py-8 sm:px-6 ${messages.length === 0 ? 'flex h-full flex-col items-center justify-center space-y-0' : ''}`}>
            {messages.length === 0 && (
              <div className="text-center">
                <h1 className="text-4xl text-foreground">How can I help you today?</h1>
                <p className="mt-3 text-muted-foreground">Ask a question about your documents.</p>
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={m.role === 'user' ? 'flex justify-end' : ''}>
                {m.role === 'user' ? (
                  <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-user-bubble px-4 py-2.5 text-left leading-relaxed text-foreground">
                    {m.content}
                  </div>
                ) : (
                  <div className="min-w-0 max-w-full">
                    <div className="whitespace-pre-wrap break-words text-left leading-7 text-foreground">
                      {m.content || (streaming && m.id.startsWith('pending-') ? '…' : '')}
                    </div>
                    {m.citations && m.citations.length > 0 && <Citations citations={m.citations} />}
                  </div>
                )}
              </div>
            ))}
            <div ref={bottom} />
          </div>
        </div>
        <div className="mx-auto w-full max-w-3xl px-4 pb-4 sm:px-6">
          {searching && (
            <p className="mb-2 flex animate-pulse items-center gap-2 text-sm text-muted-foreground" data-testid="searching-indicator">
              <Search className="size-4" aria-hidden="true" />
              Searching documents…
            </p>
          )}
          {error && <p className="mb-2 text-sm text-destructive">{error}</p>}
          <form onSubmit={send} className="flex items-center gap-2 rounded-2xl border border-input bg-card p-2 pl-4 transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/25">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message"
              disabled={streaming}
              className="h-10 border-0 bg-transparent px-0 text-base shadow-none focus-visible:border-0 focus-visible:ring-0 disabled:bg-transparent dark:bg-transparent"
            />
            <Button type="submit" size="icon" aria-label="Send" disabled={streaming || !input.trim()} className="size-9 shrink-0 rounded-full bg-primary text-primary-foreground hover:bg-primary/90">
              <ArrowUp className="size-4" aria-hidden="true" />
            </Button>
          </form>
        </div>
      </main>
    </div>
  )
}
