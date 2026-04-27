'use client'

import { useState, useMemo } from 'react'
import dynamic from 'next/dynamic'
import type { Transaction, Account, Category } from '@/lib/types'
import TransactionTable from './TransactionTable'

const MonthlyChart = dynamic(() => import('./MonthlyChart'), { ssr: false })

interface Props {
  transactions: Transaction[]
  accounts: Account[]
  categories: Category[]
}

export default function Dashboard({ transactions, accounts, categories }: Props) {
  const [filterAccount, setFilterAccount]     = useState('')
  const [filterCategory, setFilterCategory]   = useState('')
  const [filterDateFrom, setFilterDateFrom]   = useState('')
  const [filterDateTo, setFilterDateTo]       = useState('')
  const [filterSearch, setFilterSearch]       = useState('')

  const hasFilter = filterAccount || filterCategory || filterDateFrom || filterDateTo || filterSearch

  const filtered = useMemo(() => {
    return transactions.filter(tx => {
      if (filterAccount  && tx.accounts?.name  !== filterAccount)  return false
      if (filterCategory && tx.categories?.name !== filterCategory) return false
      if (filterDateFrom && tx.started_at < filterDateFrom)         return false
      if (filterDateTo   && tx.started_at > filterDateTo + 'T23:59:59') return false
      if (filterSearch) {
        const q = filterSearch.toLowerCase()
        if (!(tx.description ?? '').toLowerCase().includes(q)) return false
      }
      return true
    })
  }, [transactions, filterAccount, filterCategory, filterDateFrom, filterDateTo, filterSearch])

  function reset() {
    setFilterAccount(''); setFilterCategory('')
    setFilterDateFrom(''); setFilterDateTo(''); setFilterSearch('')
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-800">Finanz-Dashboard</h1>
        <p className="text-gray-500 mt-1">{transactions.length.toLocaleString('de-CH')} Transaktionen geladen</p>
      </div>

      {/* Summary Cards */}
      <SummaryCards transactions={filtered} />

      {/* Filter */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4 text-gray-700">Filter</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1 uppercase tracking-wide">Konto</label>
            <select
              value={filterAccount}
              onChange={e => setFilterAccount(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white"
            >
              <option value="">Alle Konten</option>
              {accounts.map(a => (
                <option key={a.id} value={a.name}>{a.name} ({a.currency})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1 uppercase tracking-wide">Kategorie</label>
            <select
              value={filterCategory}
              onChange={e => setFilterCategory(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white"
            >
              <option value="">Alle Kategorien</option>
              {categories.map(c => (
                <option key={c.id} value={c.name}>{c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1 uppercase tracking-wide">Von</label>
            <input
              type="date"
              value={filterDateFrom}
              onChange={e => setFilterDateFrom(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1 uppercase tracking-wide">Bis</label>
            <input
              type="date"
              value={filterDateTo}
              onChange={e => setFilterDateTo(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1 uppercase tracking-wide">Suche</label>
            <input
              type="text"
              placeholder="Beschreibung..."
              value={filterSearch}
              onChange={e => setFilterSearch(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>
        {hasFilter && (
          <button
            onClick={reset}
            className="mt-3 text-sm text-blue-600 hover:text-blue-800 underline"
          >
            Filter zurücksetzen
          </button>
        )}
      </div>

      {/* Monthly Chart */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-700">Monatliche Übersicht</h2>
          {!filterAccount && (
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">Alle Währungen gemischt</span>
          )}
        </div>
        <MonthlyChart transactions={filtered} />
      </div>

      {/* Transaction Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">
          Transaktionen{' '}
          <span className="text-gray-400 font-normal text-base">
            ({filtered.length.toLocaleString('de-CH')})
          </span>
        </h2>
        <TransactionTable transactions={filtered} />
      </div>
    </div>
  )
}

function SummaryCards({ transactions }: { transactions: Transaction[] }) {
  // Group by currency for accurate multi-currency display
  const byCurrency = useMemo(() => {
    const map: Record<string, { einnahmen: number; ausgaben: number }> = {}
    for (const tx of transactions) {
      const cur = tx.currency
      if (!map[cur]) map[cur] = { einnahmen: 0, ausgaben: 0 }
      const amt = Number(tx.amount)
      if (amt > 0) map[cur].einnahmen += amt
      else map[cur].ausgaben += Math.abs(amt)
    }
    return map
  }, [transactions])

  const currencies = Object.keys(byCurrency).sort()
  const total = transactions.length

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 col-span-2 sm:col-span-1">
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Transaktionen</p>
        <p className="text-2xl font-bold text-gray-800 mt-1">{total.toLocaleString('de-CH')}</p>
      </div>
      {currencies.slice(0, 3).map(cur => {
        const { einnahmen, ausgaben } = byCurrency[cur]
        const saldo = einnahmen - ausgaben
        return (
          <div key={cur} className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Saldo {cur}</p>
            <p className={`text-2xl font-bold mt-1 ${saldo >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {saldo >= 0 ? '+' : ''}{fmt(saldo)}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              +{fmt(einnahmen)} / -{fmt(ausgaben)}
            </p>
          </div>
        )
      })}
    </div>
  )
}

function fmt(n: number) {
  return n.toLocaleString('de-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
