'use client'

import { useState, useMemo, useEffect } from 'react'
import dynamic from 'next/dynamic'
import type { Transaction, Account, Category } from '@/lib/types'
import TransactionTable from './TransactionTable'
import FixkostenCard from './FixkostenCard'

const MonthlyChart = dynamic(() => import('./MonthlyChart'), { ssr: false })

interface Props {
  transactions: Transaction[]
  accounts: Account[]
  categories: Category[]
}

export default function Dashboard({ transactions, accounts, categories }: Props) {
  const [filterAccount, setFilterAccount]         = useState('')
  const [filterCategory, setFilterCategory]       = useState('')
  const [filterDateFrom, setFilterDateFrom]       = useState('')
  const [filterDateTo, setFilterDateTo]           = useState('')
  const [filterSearch, setFilterSearch]           = useState('')
  const [hideInternal, setHideInternal]           = useState(false)
  const [internalKeywords, setInternalKeywords]   = useState('Daniel Lorenz')
  const [schuldenKeywords, setSchuldenKeywords]   = useState('Rebekka Gerdes')
  const [fixkostenByMonth, setFixkostenByMonth]   = useState<Record<string, number>>({})
  const [drillMonth, setDrillMonth]               = useState<string | null>(null)

  useEffect(() => {
    const keywords = localStorage.getItem('schuldenKeywords')
    if (keywords) setSchuldenKeywords(keywords)
  }, [])

  function updateSchuldenKeywords(val: string) {
    setSchuldenKeywords(val)
    localStorage.setItem('schuldenKeywords', val)
  }

  const schuldenKeywordList = useMemo(() =>
    schuldenKeywords.split(',').map(k => k.trim().toLowerCase()).filter(Boolean)
  , [schuldenKeywords])

  const INTERNAL_TYPES = ['Transfer', 'Umtausch']

  const hasFilter = filterAccount || filterCategory || filterDateFrom || filterDateTo || filterSearch || hideInternal

  const internalKeywordList = useMemo(() =>
    internalKeywords.split(',').map(k => k.trim().toLowerCase()).filter(Boolean)
  , [internalKeywords])

  const filtered = useMemo(() => {
    return transactions.filter(tx => {
      if (hideInternal) {
        if (INTERNAL_TYPES.includes(tx.transaction_type)) return false
        const desc = (tx.description ?? '').toLowerCase()
        if (internalKeywordList.some(kw => desc.includes(kw))) return false
      }
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
  }, [transactions, filterAccount, filterCategory, filterDateFrom, filterDateTo, filterSearch, hideInternal, internalKeywordList])

  const drillTransactions = useMemo(() => {
    if (!drillMonth) return []
    return filtered.filter(tx => tx.started_at.startsWith(drillMonth))
  }, [filtered, drillMonth])

  const drillMonthLabel = useMemo(() => {
    if (!drillMonth) return ''
    const [y, m] = drillMonth.split('-')
    return new Date(Number(y), Number(m) - 1, 1)
      .toLocaleDateString('de-CH', { month: 'long', year: 'numeric' })
  }, [drillMonth])

  function handleMonthClick(key: string) {
    setDrillMonth(prev => prev === key ? null : key)
  }

  function reset() {
    setFilterAccount(''); setFilterCategory('')
    setFilterDateFrom(''); setFilterDateTo(''); setFilterSearch('')
    setHideInternal(false)
    setInternalKeywords('Daniel Lorenz')
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

      {/* Fixkosten */}
      <FixkostenCard transactions={filtered} onFixkostenChange={setFixkostenByMonth} />

      {/* Schulden */}
      <SchuldenCard
        transactions={filtered}
        schuldenKeywords={schuldenKeywords}
        schuldenKeywordList={schuldenKeywordList}
        onSchuldenKeywordsChange={updateSchuldenKeywords}
      />

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
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <input
              id="hideInternal"
              type="checkbox"
              checked={hideInternal}
              onChange={e => setHideInternal(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
            />
            <label htmlFor="hideInternal" className="text-sm text-gray-600 cursor-pointer select-none">
              Interne Überweisungen ausblenden
            </label>
          </div>
          {hideInternal && (
            <div className="flex items-center gap-2 flex-1 min-w-[260px]">
              <span className="text-xs text-gray-400 whitespace-nowrap">+ Begriffe:</span>
              <input
                type="text"
                value={internalKeywords}
                onChange={e => setInternalKeywords(e.target.value)}
                placeholder="z.B. Daniel Lorenz, Umbuchung"
                className="flex-1 border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <span className="text-xs text-gray-400 whitespace-nowrap">kommagetrennt</span>
            </div>
          )}
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
        <MonthlyChart
          transactions={filtered}
          schuldenKeywordList={schuldenKeywordList}
          fixkostenByMonth={fixkostenByMonth}
          onMonthClick={handleMonthClick}
          selectedMonth={drillMonth}
        />
        {!drillMonth && (
          <p className="text-xs text-gray-400 text-center mt-3">
            Monat anklicken für Detailansicht
          </p>
        )}
      </div>

      {/* Drill-down Panel */}
      {drillMonth && (
        <div className="bg-white rounded-xl shadow-sm border border-blue-200 p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-700">
                {drillMonthLabel}
              </h2>
              <p className="text-sm text-gray-400 mt-0.5">
                {drillTransactions.length.toLocaleString('de-CH')} Transaktionen
              </p>
            </div>
            <button
              onClick={() => setDrillMonth(null)}
              className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-lg hover:bg-gray-100"
              aria-label="Detailansicht schließen"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
          <TransactionTable transactions={drillTransactions} />
        </div>
      )}

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

function SchuldenCard({
  transactions,
  schuldenKeywords,
  schuldenKeywordList,
  onSchuldenKeywordsChange,
}: {
  transactions: Transaction[]
  schuldenKeywords: string
  schuldenKeywordList: string[]
  onSchuldenKeywordsChange: (v: string) => void
}) {
  const matched = useMemo(() =>
    transactions.filter(tx => {
      const desc = (tx.description ?? '').toLowerCase()
      return schuldenKeywordList.some(kw => desc.includes(kw))
    })
  , [transactions, schuldenKeywordList])

  const aufgenommen   = useMemo(() => matched.filter(tx => Number(tx.amount) > 0).reduce((s, tx) => s + Number(tx.amount), 0), [matched])
  const zurückgezahlt = useMemo(() => matched.filter(tx => Number(tx.amount) < 0).reduce((s, tx) => s + Math.abs(Number(tx.amount)), 0), [matched])
  const verbleibend   = Math.max(0, aufgenommen - zurückgezahlt)
  const prozent       = aufgenommen > 0 ? Math.min(100, (zurückgezahlt / aufgenommen) * 100) : 0

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">Schulden</h2>
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-6">

        {/* Erkennungs-Begriffe */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1 uppercase tracking-wide">
            Erkennungs-Begriffe
          </label>
          <input
            type="text"
            value={schuldenKeywords}
            onChange={e => onSchuldenKeywordsChange(e.target.value)}
            placeholder="z.B. Rebekka Gerdes, Darlehen"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <p className="text-xs text-gray-400 mt-1">Kommagetrennt · lokal gespeichert</p>
        </div>

        {/* Aufgenommen */}
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Aufgenommen</p>
          <p className="text-2xl font-bold text-red-600">{fmt(aufgenommen)}</p>
          <p className="text-xs text-gray-400 mt-1">Erhaltene Schulden</p>
        </div>

        {/* Zurückgezahlt */}
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Zurückgezahlt</p>
          <p className="text-2xl font-bold text-green-600">{fmt(zurückgezahlt)}</p>
          <p className="text-xs text-gray-400 mt-1">Geleistete Rückzahlungen</p>
        </div>

        {/* Noch offen */}
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Noch offen</p>
          <p className="text-2xl font-bold text-orange-500">{fmt(verbleibend)}</p>
          <p className="text-xs text-gray-400 mt-1">Verbleibende Schuld</p>
        </div>
      </div>

      {/* Fortschrittsbalken */}
      {aufgenommen > 0 && (
        <div className="mt-5">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>{prozent.toFixed(1)} % zurückgezahlt</span>
            <span>{fmt(zurückgezahlt)} / {fmt(aufgenommen)} EUR</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-3">
            <div
              className="bg-green-500 h-3 rounded-full transition-all duration-500"
              style={{ width: `${prozent}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
