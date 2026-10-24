import { Outlet } from 'react-router-dom'

import { themeVars } from '../theme'
import GlobalNav from './GlobalNav'

export default function AppLayout() {
  return (
    <div className="app" style={themeVars}>
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <GlobalNav />
      <main id="content" className="app-main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
