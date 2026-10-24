import { describe, expect, it } from 'vitest'

import type { DemoUser } from '../api/types'
import { groupDemoUsers } from './RoleSwitcher'

const users: DemoUser[] = [
  { id: 1, name: 'Prof. Dana Rivera', sortable_name: 'Rivera, Dana', role_summary: 'Teacher' },
  { id: 4, name: 'Marcus Bell', sortable_name: 'Bell, Marcus', role_summary: 'Student' },
  { id: 2, name: 'Alex Kim', sortable_name: 'Kim, Alex', role_summary: 'Student' },
  { id: 3, name: 'Priya Natarajan', sortable_name: 'Natarajan, Priya', role_summary: 'Student' },
]

describe('groupDemoUsers', () => {
  it('puts teachers first and keeps every user when there is no query', () => {
    const groups = groupDemoUsers(users, '')
    expect(groups.map((g) => g.label)).toEqual(['Teachers', 'Students'])
    expect(groups[1].users.map((u) => u.id)).toEqual([4, 2, 3])
  })

  it('matches any part of the name, case-insensitively', () => {
    expect(groupDemoUsers(users, 'KIM')).toEqual([{ label: 'Students', users: [users[2]] }])
    expect(groupDemoUsers(users, 'riv')[0].users.map((u) => u.id)).toEqual([1])
  })

  it('drops groups with no matches and returns nothing when nobody matches', () => {
    expect(groupDemoUsers(users, 'priya').map((g) => g.label)).toEqual(['Students'])
    expect(groupDemoUsers(users, 'zzz')).toEqual([])
  })
})
