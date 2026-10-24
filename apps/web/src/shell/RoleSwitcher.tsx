import { Select, Text } from '@instructure/ui'
import { useState } from 'react'

import { useDemoUsers } from '../api/hooks'
import type { DemoUser } from '../api/types'
import { useDemoUser } from './demoUser'

export interface UserGroup {
  label: 'Teachers' | 'Students'
  users: DemoUser[]
}

/** Users matching `query` (case-insensitive, any part of the name), teachers first; empty groups dropped. */
export function groupDemoUsers(users: DemoUser[], query: string): UserGroup[] {
  const q = query.trim().toLowerCase()
  const match = (u: DemoUser) => !q || u.name.toLowerCase().includes(q) || u.sortable_name.toLowerCase().includes(q)
  const groups: UserGroup[] = [
    { label: 'Teachers', users: users.filter((u) => u.role_summary === 'Teacher' && match(u)) },
    { label: 'Students', users: users.filter((u) => u.role_summary === 'Student' && match(u)) },
  ]
  return groups.filter((g) => g.users.length > 0)
}

const optionId = (u: DemoUser) => `demo-user-${u.id}`

/** Demo stand-in for login: a searchable picker of every seeded user, grouped by role. */
export default function RoleSwitcher({ onSwitch }: { onSwitch?: () => void }) {
  const { userId, setUserId } = useDemoUser()
  const { data: users, isError } = useDemoUsers()
  const current = users?.find((u) => u.id === userId)
  const [query, setQuery] = useState<string | null>(null) // null = not typing; show the current name
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState<string | undefined>()

  if (isError) return <Text color="danger">Could not load demo users. Is the API running?</Text>
  if (!users) return <Text>Loading users…</Text>

  const groups = groupDemoUsers(users, query ?? '')
  const close = () => {
    setOpen(false)
    setQuery(null)
    setHighlighted(undefined)
  }

  return (
    <Select
      renderLabel="Viewing as"
      assistiveText="Type a name to filter. Use the arrow keys to move through the list."
      placeholder="Search users"
      inputValue={query ?? current?.name ?? ''}
      isShowingOptions={open}
      onInputChange={(_e, value) => {
        setQuery(value)
        setOpen(true)
      }}
      onRequestShowOptions={() => setOpen(true)}
      onRequestHideOptions={close}
      onRequestHighlightOption={(_e, { id }) => setHighlighted(id)}
      onRequestSelectOption={(_e, { id }) => {
        const user = users.find((u) => optionId(u) === id)
        close()
        if (user && user.id !== userId) {
          setUserId(user.id)
          onSwitch?.()
        }
      }}
    >
      {groups.length === 0 ? (
        <Select.Option id="demo-user-none" isDisabled>No users match “{query}”</Select.Option>
      ) : (
        groups.map((g) => (
          <Select.Group key={g.label} renderLabel={g.label}>
            {g.users.map((u) => (
              <Select.Option key={u.id} id={optionId(u)} isHighlighted={highlighted === optionId(u)}
                isSelected={u.id === userId}>
                {u.name}
              </Select.Option>
            ))}
          </Select.Group>
        ))
      )}
    </Select>
  )
}
