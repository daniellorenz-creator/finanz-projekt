export type Transaction = {
  id: string
  started_at: string
  completed_at: string | null
  transaction_type: string
  status: string
  amount: number
  fee: number
  currency: string
  description: string | null
  source_file: string | null
  accounts: { name: string } | null
  categories: { name: string } | null
}

export type Account = {
  id: string
  name: string
  currency: string
}

export type Category = {
  id: string
  name: string
}
