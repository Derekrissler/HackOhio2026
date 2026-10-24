import { Heading, View } from '@instructure/ui'

import { themeVars } from './theme'

export default function App() {
  return (
    <View as="main" padding="medium" style={themeVars}>
      <Heading level="h1">Dashboard</Heading>
    </View>
  )
}
