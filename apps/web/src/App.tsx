import { Route, Routes } from 'react-router-dom'

import PlaceholderPage from './pages/PlaceholderPage'
import AppLayout from './shell/AppLayout'
import CourseLayout from './shell/CourseLayout'
import { COURSE_TABS } from './shell/courseTabs'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<PlaceholderPage title="Dashboard" phase={3} />} />
        <Route path="courses/:courseId" element={<CourseLayout />}>
          {COURSE_TABS.map((tab) =>
            tab.path === '' ? (
              <Route key="home" index element={<PlaceholderPage title={tab.label} phase={tab.phase} />} />
            ) : (
              <Route
                key={tab.path}
                path={tab.path}
                element={<PlaceholderPage title={tab.label} phase={tab.phase} />}
              />
            ),
          )}
        </Route>
        <Route path="*" element={<PlaceholderPage title="Page not found" phase={2} />} />
      </Route>
    </Routes>
  )
}
