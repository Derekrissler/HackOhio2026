/** The API sends naive UTC timestamps ("2026-09-12T03:59:00"); treat them as UTC. */
export function parseUtc(value: string): Date {
  return new Date(/(Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`)
}

const dayFormat = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' })
const timeFormat = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' })
const weekdayFormat = new Intl.DateTimeFormat('en-US', { weekday: 'short', month: 'short', day: 'numeric' })

/** Canvas style: "Sep 11 at 11:59pm". */
export function formatDateTime(value: string | null): string {
  if (!value) return 'No due date'
  const d = parseUtc(value)
  return `${dayFormat.format(d)} at ${timeFormat.format(d).replace(' ', '').toLowerCase()}`
}

export function formatDay(value: string): string {
  return weekdayFormat.format(parseUtc(value))
}

export function formatPoints(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

export function formatPercent(value: number | null): string {
  return value === null ? '–' : `${value.toFixed(2)}%`
}

export function isPast(value: string | null, now = new Date()): boolean {
  return value !== null && parseUtc(value) < now
}
