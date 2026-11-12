/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { createThread, deleteThread, listThreads, type Thread } from '@/lib/api'

type ThreadsCtx = {
  threads: Thread[]
  activeThreadId: string | null
  /** Set the active id without navigating (used by Chat when it lazily creates a thread). */
  setActiveThreadId: (id: string | null) => void
  selectThread: (id: string) => void
  newThread: () => Promise<void>
  removeThread: (id: string) => Promise<void>
  refresh: () => Promise<void>
  error: string
}

const Ctx = createContext<ThreadsCtx | null>(null)

export function ThreadsProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [threads, setThreads] = useState<Thread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => setThreads(await listThreads()), [])
  useEffect(() => { refresh().catch((e) => setError(String(e))) }, [refresh])

  const selectThread = useCallback((id: string) => { setActiveThreadId(id); navigate('/') }, [navigate])

  const newThread = useCallback(async () => {
    const t = await createThread()
    await refresh()
    setActiveThreadId(t.id)
    navigate('/')
  }, [refresh, navigate])

  const removeThread = useCallback(async (id: string) => {
    await deleteThread(id)
    setActiveThreadId((a) => (a === id ? null : a))
    await refresh()
  }, [refresh])

  const value = useMemo(
    () => ({ threads, activeThreadId, setActiveThreadId, selectThread, newThread, removeThread, refresh, error }),
    [threads, activeThreadId, selectThread, newThread, removeThread, refresh, error],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useThreads() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useThreads must be used within ThreadsProvider')
  return c
}
