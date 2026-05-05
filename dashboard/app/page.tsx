import { createClient } from '@/lib/supabase'
import Dashboard from '@/app/components/Dashboard'
import type { Transaction, Account, Category } from '@/lib/types'

export const dynamic = 'force-dynamic'

async function fetchAllTransactions(supabase: ReturnType<typeof createClient>): Promise<Transaction[]> {
  const pageSize = 1000
  let page = 0
  const all: Transaction[] = []

  while (true) {
    const { data, error } = await supabase
      .from('transactions')
      .select(`
        id, started_at, completed_at, transaction_type, status,
        amount, fee, currency, description, source_file,
        accounts(name),
        categories(name)
      `)
      .order('started_at', { ascending: false })
      .range(page * pageSize, (page + 1) * pageSize - 1)

    if (error) { console.error('Transaktionen:', error.message); break }
    if (!data || data.length === 0) break

    all.push(...(data as unknown as Transaction[]))
    if (data.length < pageSize) break
    page++
  }

  return all
}

export default async function Home() {
  const supabase = createClient()

  const [transactions, accRes, catRes] = await Promise.all([
    fetchAllTransactions(supabase),
    supabase.from('accounts').select('id, name, currency').order('name'),
    supabase.from('categories').select('id, name').order('name'),
  ])

  if (accRes.error) console.error('Konten:', accRes.error.message)
  if (catRes.error) console.error('Kategorien:', catRes.error.message)

  return (
    <Dashboard
      transactions={transactions}
      accounts={(accRes.data ?? []) as unknown as Account[]}
      categories={(catRes.data ?? []) as unknown as Category[]}
    />
  )
}
