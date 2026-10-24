import { Breadcrumb, BreadcrumbLink } from '@instructure/ui'
import { useLocation } from 'react-router-dom'

import type { Course } from '../api/types'
import { COURSE_TABS } from './courseTabs'
import { useCrumbTrail, type Crumb } from './crumbs'
import { useRouterLink } from './useRouterLink'

export default function Breadcrumbs({ course }: { course: Course }) {
  const { pathname } = useLocation()
  const link = useRouterLink()
  const home = `/courses/${course.id}`
  const segment = pathname.split('/')[3] ?? ''
  const tab = segment ? COURSE_TABS.find((t) => t.path === segment) : undefined

  const trail: Crumb[] = [{ label: course.code, to: '' }]
  if (tab) trail.push({ label: tab.label, to: tab.path })
  trail.push(...useCrumbTrail())

  // Breadcrumb draws a separator after every child but the last, so pass no `false` children.
  return (
    <Breadcrumb label="You are here:">
      {trail.map((crumb, i) => {
        const last = i === trail.length - 1
        const to = `${home}/${crumb.to ?? ''}`.replace(/\/$/, '')
        return last || crumb.to === undefined ? (
          <BreadcrumbLink key={i} isCurrentPage={last}>
            {crumb.label}
          </BreadcrumbLink>
        ) : (
          <BreadcrumbLink key={i} href={to} onClick={link(to)}>
            {crumb.label}
          </BreadcrumbLink>
        )
      })}
    </Breadcrumb>
  )
}
