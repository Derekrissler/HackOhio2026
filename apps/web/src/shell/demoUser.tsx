import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

const STORAGE_KEY = 'demoUserId'
const DEFAULT_USER_ID = 1

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
  const [userId, setUserIdState] = useState(() => initialUserId ?? readStoredUserId())

  const setUserId = useCallback((id: number) => {
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
