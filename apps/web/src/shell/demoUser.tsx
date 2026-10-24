import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

const STORAGE_KEY = 'demoUserId'
const COOKIE = 'demo_user'
const DEFAULT_USER_ID = 1

/** PDF iframes can't send the X-Demo-User header, so the API also accepts this cookie. */
function writeCookie(id: number) {
  document.cookie = `${COOKIE}=${id}; path=/; SameSite=Strict`
}

interface DemoUserContextValue {
  userId: number
  setUserId: (id: number) => void
}

const DemoUserContext = createContext<DemoUserContextValue | null>(null)

function readStoredUserId(): number {
  try {
    const stored = Number(localStorage.getItem(STORAGE_KEY))
    return Number.isInteger(stored) && stored > 0 ? stored : DEFAULT_USER_ID
  } catch {
    return DEFAULT_USER_ID
  }
}

export function DemoUserProvider({
  children,
  initialUserId,
}: {
  children: ReactNode
  initialUserId?: number
}) {
  const [userId, setUserIdState] = useState(() => {
    const id = initialUserId ?? readStoredUserId()
    writeCookie(id)
    return id
  })

  const setUserId = useCallback((id: number) => {
    writeCookie(id)
    setUserIdState(id)
    try {
      localStorage.setItem(STORAGE_KEY, String(id))
    } catch {
      // Storage unavailable (private mode): the choice lasts for this tab only.
    }
  }, [])

  return <DemoUserContext.Provider value={{ userId, setUserId }}>{children}</DemoUserContext.Provider>
}

export function useDemoUser(): DemoUserContextValue {
  const value = useContext(DemoUserContext)
  if (!value) throw new Error('useDemoUser must be used inside <DemoUserProvider>')
  return value
}
