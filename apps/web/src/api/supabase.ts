import { createClient } from '@supabase/supabase-js'

/** This client only authenticates. Result reads go through the guarded API. */
export function createAnalyticsClient() {
  const url = import.meta.env.VITE_SUPABASE_URL
  const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
  if (!url || !key || !key.startsWith('sb_publishable_')) return null
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: true, detectSessionInUrl: false },
  })
}
