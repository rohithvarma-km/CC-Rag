import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { FileText, LogOut, MessageSquare, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { supabase } from '@/lib/supabase'
import { ThreadsProvider, useThreads } from '@/lib/threads'

const link = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring ${isActive ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground'}`

const titleCase = (s: string) => s.replace(/[._-]+/g, ' ').trim().split(/\s+/).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')

function useProfile() {
  const [profile, setProfile] = useState({ name: '', email: '' })
  useEffect(() => {
    let alive = true
    supabase.auth.getUser().then(({ data }) => {
      const u = data.user
      if (!alive || !u) return
      const email = u.email ?? ''
      const meta = (u.user_metadata ?? {}) as Record<string, unknown>
      const raw = (meta.full_name as string) || (meta.name as string) || ''
      setProfile({ name: raw || titleCase(email.split('@')[0] ?? ''), email })
    })
    return () => { alive = false }
  }, [])
  return profile
}

function Profile() {
  const { name, email } = useProfile()
  const initials = (name || email || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
  return (
    <div className="flex items-center gap-2.5 border-t border-sidebar-border pt-3">
      <div aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground">{initials}</div>
      <div className="min-w-0 flex-1 leading-tight">
        <p className="truncate text-sm font-medium text-foreground" data-testid="profile-name">{name}</p>
        <p className="truncate text-xs text-muted-foreground" data-testid="profile-email">{email}</p>
      </div>
      <Button variant="ghost" size="icon" aria-label="Sign out" title="Sign out" className="size-8 shrink-0 rounded-full text-muted-foreground" onClick={() => supabase.auth.signOut()}>
        <LogOut className="size-4" aria-hidden="true" />
      </Button>
    </div>
  )
}

function Sidebar() {
  const { threads, activeThreadId, selectThread, newThread, removeThread } = useThreads()
  return (
    <aside className="flex max-h-60 w-full shrink-0 flex-col gap-3 border-b border-sidebar-border bg-sidebar p-3 text-sidebar-foreground md:max-h-none md:w-64 md:border-b-0 md:border-r">
      <span className="px-2 font-serif text-xl tracking-tight text-foreground" style={{ fontFamily: 'var(--font-serif-stack)' }}>Agentic RAG</span>
      <Button variant="outline" onClick={() => newThread()} className="h-9 w-full justify-start gap-2 rounded-xl px-3 text-sm">
        <Plus className="size-4" aria-hidden="true" />
        New chat
      </Button>
      <nav className="flex gap-1 md:flex-col" aria-label="Main">
        <NavLink to="/" end className={link}><MessageSquare className="size-4" aria-hidden="true" />Chat</NavLink>
        <NavLink to="/ingestion" className={link}><FileText className="size-4" aria-hidden="true" />Documents</NavLink>
      </nav>
      <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {threads.map((t) => (
          <div key={t.id} className={`group flex items-center rounded-lg px-1 text-sm transition-colors ${t.id === activeThreadId ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'hover:bg-sidebar-accent/60'}`}>
            <button className="min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => selectThread(t.id)}>{t.title}</button>
            <button aria-label="Delete thread" className="rounded-md px-1.5 py-1 text-muted-foreground opacity-0 outline-none transition-opacity hover:text-destructive focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100" onClick={() => removeThread(t.id)}>✕</button>
          </div>
        ))}
      </div>
      <Profile />
    </aside>
  )
}

export default function AppLayout() {
  return (
    <ThreadsProvider>
      <div className="flex h-screen flex-col bg-background md:flex-row">
        <Sidebar />
        <div className="min-h-0 min-w-0 flex-1">
          <Outlet />
        </div>
      </div>
    </ThreadsProvider>
  )
}
