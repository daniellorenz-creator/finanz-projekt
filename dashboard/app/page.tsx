import { createClient } from '@/lib/supabase'
import Dashboard from '@/app/components/Dashboard'
import type { Transaction, Account, Category } from '@/lib/types'

export const dynamic = 'force-dynamic'

export default async function Home() {
  const supabase = createClient()

  const [txRes, accRes, catRes] = await Promise.all([
    supabase
      .from('transactions')
      .select(`
        id, started_at, completed_at, transaction_type, status,
        amount, fee, currency, description, source_file,
        accounts(name),
        categories(name)
      `)
      .eq('status', 'ABGESCHLOSSEN')
      .order('started_at', { ascending: false })
      .limit(10000),
    supabase.from('accounts').select('id, name, currency').order('name'),
    supabase.from('categories').select('id, name').order('name'),
  ])

  if (txRes.error) console.error('Transaktionen:', txRes.error.message)
  if (accRes.error) console.error('Konten:', accRes.error.message)
  if (catRes.error) console.error('Kategorien:', catRes.error.message)

  return (
    <Dashboard
      transactions={(txRes.data ?? []) as Transaction[]}
      accounts={(accRes.data ?? []) as Account[]}
      categories={(catRes.data ?? []) as Category[]}
    />
  )
}
