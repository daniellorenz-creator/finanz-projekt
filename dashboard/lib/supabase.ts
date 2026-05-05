import { createClient as createSupabaseClient } from '@supabase/supabase-js'

export function createClient() {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_ANON_KEY
  if (!url || !key) {
    throw new Error('SUPABASE_URL und SUPABASE_ANON_KEY fehlen in .env.local')
  }
  return createSupabaseClient(url, key)
}
