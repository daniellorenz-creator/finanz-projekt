import { createClient as createSupabaseClient } from '@supabase/supabase-js'

export function createClient() {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_KEY
  if (!url || !key) {
    throw new Error('SUPABASE_URL und SUPABASE_SERVICE_KEY fehlen in .env.local')
  }
  return createSupabaseClient(url, key)
}
