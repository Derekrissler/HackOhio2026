import { canvas } from '@instructure/ui'
import type { CSSProperties } from 'react'

const c = canvas.colors.contrasts

/** InstUI canvas-theme tokens as CSS variables, for the few layout styles in shell.css. */
export const themeVars = {
  '--brand': canvas['ic-brand-primary'],
  '--text': canvas['ic-brand-font-color-dark'],
  '--text-muted': c.grey5782,
  '--border': c.grey1424,
  '--surface': c.white1010,
  '--surface-muted': c.grey1111,
  '--success': c.green4570,
  '--success-bg': c.green1212,
  '--font': canvas.typography.fontFamily,
} as CSSProperties

/** Course-card hero colours, taken from the theme's contrast palette. */
export const courseColors = [c.blue4570, c.green4570, c.violet4570, c.sea4570, c.orange4570]
