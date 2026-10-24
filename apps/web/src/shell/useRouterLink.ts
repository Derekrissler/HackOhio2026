import type { MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'

/**
 * Click handler for InstUI components that render a plain `href`: navigates client-side,
 * but leaves modified clicks (new tab, new window) to the browser.
 */
export function useRouterLink() {
  const navigate = useNavigate()
  // MouseEvent<unknown>: InstUI types some click events with its own props as the target.
  return (to: string) => (event: MouseEvent<unknown>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
    event.preventDefault()
    navigate(to)
  }
}
