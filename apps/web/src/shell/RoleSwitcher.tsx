import { SimpleSelect, Text } from '@instructure/ui'

import { useDemoUsers } from '../api/hooks'
import { useDemoUser } from './demoUser'

/** Demo stand-in for login: picks which seeded user the app acts as. */
export default function RoleSwitcher({ onSwitch }: { onSwitch?: () => void }) {
  const { userId, setUserId } = useDemoUser()
  const { data: users, isError } = useDemoUsers()

  if (isError) return <Text color="danger">Could not load demo users. Is the API running?</Text>
  if (!users) return <Text>Loading users…</Text>

  return (
    <SimpleSelect
      renderLabel="Viewing as"
      value={String(userId)}
      onChange={(_event, { value }) => {
        setUserId(Number(value))
        onSwitch?.()
      }}
    >
      {users.map((user) => (
        <SimpleSelect.Option key={user.id} id={`demo-user-${user.id}`} value={String(user.id)}>
          {`${user.name} (${user.role_summary})`}
        </SimpleSelect.Option>
      ))}
    </SimpleSelect>
  )
}
