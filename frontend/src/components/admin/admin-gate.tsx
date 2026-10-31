'use client'

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react'

import { AdminAccessError, fetchAdminMe } from '@/lib/api/admin'
import {
  readAccessToken,
  signInWithGoogle,
  signOut,
} from '@/lib/supabase/client'

type GateState =
  | { kind: 'checking' }
  | { kind: 'signed_out' }
  | { kind: 'not_authorized' }
  | { kind: 'error' }
  | { kind: 'admin'; email: string }

const AdminEmailContext = createContext<string | null>(null)

/** The signed-in admin's email, confirmed by the backend. Null outside the gate. */
export function useAdminEmail(): string | null {
  return useContext(AdminEmailContext)
}

/**
 * Shows nothing from the admin panel until the backend confirms the signed-in user is
 * an admin. No session means a sign-in screen. A session that is not on the admin list
 * means "not authorized". There is no demo data and no fallback.
 */
export function AdminGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>({ kind: 'checking' })
  const [signInError, setSignInError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    async function check() {
      try {
        if (!(await readAccessToken())) {
          if (!ignore) setState({ kind: 'signed_out' })
          return
        }
        const me = await fetchAdminMe()
        if (!ignore) setState({ kind: 'admin', email: me.email })
      } catch (err: unknown) {
        if (ignore) return
        if (err instanceof AdminAccessError) {
          setState({ kind: err.code })
        } else {
          setState({ kind: 'error' })
        }
      }
    }
    void check()
    return () => {
      ignore = true
    }
  }, [])

  const startSignIn = useCallback(async () => {
    setSignInError(null)
    try {
      const result = await signInWithGoogle('/admin')
      if (result === 'not_configured') {
        setSignInError('Sign-in is not configured on this site.')
      }
    } catch {
      setSignInError('Sign-in could not start. Try again.')
    }
  }, [])

  const switchAccount = useCallback(async () => {
    await signOut()
    setState({ kind: 'signed_out' })
  }, [])

  if (state.kind === 'admin') {
    return (
      <AdminEmailContext.Provider value={state.email}>
        {children}
      </AdminEmailContext.Provider>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200 shadow-xs p-8 text-center space-y-4">
        <div className="w-12 h-12 mx-auto rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center font-bold text-white">
          BTU
        </div>
        {state.kind === 'checking' && (
          <p role="status" className="text-sm text-slate-500">
            Checking admin access...
          </p>
        )}
        {state.kind === 'signed_out' && (
          <>
            <h1 className="text-lg font-semibold text-slate-900">
              Admin sign-in required
            </h1>
            <p className="text-sm text-slate-500">
              Sign in with your BTU Google account to continue.
            </p>
            {signInError && (
              <p role="alert" className="text-xs text-rose-600">
                {signInError}
              </p>
            )}
            <button
              type="button"
              onClick={() => void startSignIn()}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition-colors"
            >
              Sign in with Google
            </button>
          </>
        )}
        {state.kind === 'not_authorized' && (
          <>
            <h1 className="text-lg font-semibold text-slate-900">
              Not authorized
            </h1>
            <p className="text-sm text-slate-500">
              This account is not on the admin list. Ask an admin to add your
              BTU email, or sign in with a different account.
            </p>
            <button
              type="button"
              onClick={() => void switchAccount()}
              className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-semibold hover:bg-slate-800 transition-colors"
            >
              Sign out
            </button>
          </>
        )}
        {state.kind === 'error' && (
          <>
            <h1 className="text-lg font-semibold text-slate-900">
              Could not check access
            </h1>
            <p className="text-sm text-slate-500">
              The server did not answer. Nothing is shown until it confirms you
              are an admin. Reload to try again.
            </p>
          </>
        )}
      </div>
    </div>
  )
}

export function AdminIdentity() {
  const email = useAdminEmail()
  const [busy, setBusy] = useState(false)
  if (!email) return null
  return (
    <div className="text-[11px] text-slate-400 space-y-1">
      <div>
        Signed in as{' '}
        <span className="text-slate-300 font-mono break-all">{email}</span>
      </div>
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          setBusy(true)
          void signOut().then(() => window.location.reload())
        }}
        className="text-slate-400 hover:text-white underline disabled:opacity-50"
      >
        Sign out
      </button>
    </div>
  )
}
