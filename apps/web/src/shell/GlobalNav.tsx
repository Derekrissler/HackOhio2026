import {
  Avatar,
  CloseButton,
  Heading,
  IconCoursesLine,
  IconDashboardLine,
  Link,
  List,
  SideNavBar,
  SideNavBarItem,
  Text,
  Tray,
  View,
} from '@instructure/ui'
import { useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

import { useCourses, useMe } from '../api/hooks'
import RoleSwitcher from './RoleSwitcher'
import { useRouterLink } from './useRouterLink'

type TrayName = 'account' | 'courses'

export default function GlobalNav() {
  const [openTray, setOpenTray] = useState<TrayName | null>(null)
  const { pathname } = useLocation()
  const link = useRouterLink()
  const { data: me } = useMe()
  const close = () => setOpenTray(null)

  return (
    <>
      <SideNavBar
        label="Global navigation"
        toggleLabel={{ expandedLabel: 'Minimize navigation', minimizedLabel: 'Expand navigation' }}
      >
        <SideNavBarItem
          icon={<Avatar name={me?.name ?? ''} size="x-small" />}
          label="Account"
          onClick={() => setOpenTray('account')}
          selected={openTray === 'account'}
        />
        <SideNavBarItem
          icon={<IconDashboardLine />}
          label="Dashboard"
          href="/"
          onClick={link('/')}
          selected={openTray === null && pathname === '/'}
        />
        <SideNavBarItem
          icon={<IconCoursesLine />}
          label="Courses"
          onClick={() => setOpenTray('courses')}
          selected={openTray === 'courses' || (openTray === null && pathname.startsWith('/courses'))}
        />
      </SideNavBar>

      <NavTray label="Account" open={openTray === 'account'} onClose={close}>
        <Heading level="h2" margin="0 0 medium">
          {me?.name ?? 'Account'}
        </Heading>
        <RoleSwitcher onSwitch={close} />
        <View as="p" margin="small 0 0">
          <Text size="small" color="secondary">
            Demo mode: there is no login. Pick a seeded user to see the app as them.
          </Text>
        </View>
      </NavTray>

      <NavTray label="Courses" open={openTray === 'courses'} onClose={close}>
        <Heading level="h2" margin="0 0 medium">
          Courses
        </Heading>
        <CourseLinks onNavigate={close} />
      </NavTray>
    </>
  )
}

function NavTray({
  label,
  open,
  onClose,
  children,
}: {
  label: string
  open: boolean
  onClose: () => void
  children: ReactNode
}) {
  return (
    <Tray label={label} open={open} onDismiss={onClose} placement="start" size="small" shouldCloseOnDocumentClick>
      <View as="div" padding="medium">
        <CloseButton placement="end" offset="small" screenReaderLabel={`Close ${label}`} onClick={onClose} />
        {children}
      </View>
    </Tray>
  )
}

function CourseLinks({ onNavigate }: { onNavigate: () => void }) {
  const { data: courses, isError } = useCourses()
  const link = useRouterLink()

  if (isError) return <Text color="danger">Could not load courses.</Text>
  if (!courses) return <Text>Loading…</Text>
  if (courses.length === 0) return <Text>You are not enrolled in any courses.</Text>

  return (
    <List isUnstyled itemSpacing="small">
      {courses.map((course) => {
        const to = `/courses/${course.id}`
        return (
          <List.Item key={course.id}>
            <Link
              href={to}
              onClick={(event) => {
                link(to)(event)
                onNavigate()
              }}
            >
              {course.name}
            </Link>
            <Text as="div" size="small" color="secondary">
              {course.code} · {course.term}
            </Text>
          </List.Item>
        )
      })}
    </List>
  )
}
