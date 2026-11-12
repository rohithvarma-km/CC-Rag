import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { supabase } from '@/lib/supabase'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setError(''); setInfo('')
    const { data, error } =
      mode === 'in'
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password })
    if (error) setError(error.message)
    else if (mode === 'up' && !data.session) setInfo('Check your email to confirm your account.')
    setBusy(false)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl border border-border bg-card p-8">
        <h1 className="mb-2 text-center text-3xl">{mode === 'in' ? 'Sign in' : 'Create account'}</h1>
        <Input type="email" className="h-10 rounded-xl px-3" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <Input type="password" className="h-10 rounded-xl px-3" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
        {error && <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</p>}
        {info && <p className="text-sm text-emerald-700 dark:text-emerald-300">{info}</p>}
        <Button type="submit" className="h-10 w-full rounded-xl text-sm" disabled={busy}>{mode === 'in' ? 'Sign in' : 'Sign up'}</Button>
        <button type="button" className="block w-full text-center text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline" onClick={() => { setMode(mode === 'in' ? 'up' : 'in'); setError(''); setInfo('') }}>
          {mode === 'in' ? 'Need an account? Sign up' : 'Have an account? Sign in'}
        </button>
      </form>
    </div>
  )
}
