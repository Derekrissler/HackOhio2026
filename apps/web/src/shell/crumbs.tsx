import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export interface Crumb {
  label: string
  /** Course-relative path ('assignments/12'); omitted for the current page. */
  to?: string
}

const CrumbContext = createContext<{ crumbs: Crumb[]; setCrumbs: (c: Crumb[]) => void } | null>(null)

export function CrumbProvider({ children }: { children: ReactNode }) {
  const [crumbs, setCrumbs] = useState<Crumb[]>([])
  return <CrumbContext.Provider value={{ crumbs, setCrumbs }}>{children}</CrumbContext.Provider>
}

/** Extra breadcrumbs after the course tab, for detail pages. Cleared when the page unmounts. */
export function useCrumbs(crumbs: Crumb[]) {
  const ctx = useContext(CrumbContext)
  const key = JSON.stringify(crumbs)
  useEffect(() => {
    ctx?.setCrumbs(JSON.parse(key))
    return () => ctx?.setCrumbs([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
}

export function useCrumbTrail(): Crumb[] {
  return useContext(CrumbContext)?.crumbs ?? []
}
