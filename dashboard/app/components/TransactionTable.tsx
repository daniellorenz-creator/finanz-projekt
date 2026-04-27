'use client'

import { useState, useEffect } from 'react'
import type { Transaction } from '@/lib/types'

const PAGE_SIZE = 50

interface Props { transactions: Transaction[] }

export default function TransactionTable({ transactions }: Props) {
  const [page, setPage] = useState(0)

  // Reset page when filter changes
  useEffect(() => { setPage(0) }, [transactions])

  const total = transactions.length
  const pages = Math.ceil(total / PAGE_SIZE)
  const rows  = transactions.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  if (total === 0) {
    return (
      <p className="text-gray-400 text-center py-12">
        Keine Transaktionen für die gewählten Filter gefunden.
      </p>
    )
  }

  return (
    <div>
      <div className="overflow-x-auto -mx-6 px-6">
        <table className="w-full text-sm min-w-[720px]">
          <thead>
            <tr className="border-b-2 border-gray-100">
              <th className="text-left pb-3 px-2 font-medium text-gray-500 text-xs uppercase tracking-wide">Datum</th>
              <th className="text-left pb-3 px-2 font-medium text-gray-500 text-xs uppercase tracking-wide">Konto</th>
              <th className="text-left pb-3 px-2 font-medium text-gray-500 text-xs uppercase tracking-wide">Typ</th>
              <th className="text-right pb-3 px-2 font-medium text-gray-500 text-xs uppercase tracking-wide">Betrag</th>
              <th className="text-left pb-3 px-2 font-medium text-gray-500 text-xs uppercase tracking-wide">Kategorie</th>
              <th className="text-left pb-3 px-2 font-medium text-gray-500 text-xs uppercase tracking-wide">Beschreibung</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(tx => {
              const amt      = Number(tx.amount)
              const negative = amt < 0
              const absAmt   = Math.abs(amt).toLocaleString('de-CH', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })

              return (
                <tr
                  key={tx.id}
                  className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                >
                  <td className="py-2.5 px-2 text-gray-500 whitespace-nowrap font-mono text-xs">
                    {fmtDate(tx.started_at)}
                  </td>
                  <td className="py-2.5 px-2 whitespace-nowrap">
                    <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                      {tx.accounts?.name ?? '—'}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-gray-600 whitespace-nowrap text-xs">
                    {tx.transaction_type}
                  </td>
                  <td className={`py-2.5 px-2 text-right font-mono font-semibold whitespace-nowrap ${negative ? 'text-red-600' : 'text-green-600'}`}>
                    {negative ? '−' : '+'}{absAmt}{' '}
                    <span className="text-xs font-normal text-gray-400">{tx.currency}</span>
                  </td>
                  <td className="py-2.5 px-2 whitespace-nowrap">
                    {tx.categories?.name ? (
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                        {tx.categories.name}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-300">—</span>
                    )}
                  </td>
                  <td className="py-2.5 px-2 text-gray-500 max-w-xs">
                    <span className="block truncate text-xs" title={tx.description ?? ''}>
                      {tx.description ? tx.description.split(' | ')[0] : '—'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between mt-5 pt-4 border-t border-gray-100">
          <p className="text-sm text-gray-400">
            {(page * PAGE_SIZE + 1).toLocaleString('de-CH')}–
            {Math.min((page + 1) * PAGE_SIZE, total).toLocaleString('de-CH')} von{' '}
            {total.toLocaleString('de-CH')}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg disabled:opacity-30 hover:bg-gray-50 transition-colors"
            >
              ← Zurück
            </button>
            <span className="px-3 py-1.5 text-sm text-gray-500">
              {page + 1} / {pages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(pages - 1, p + 1))}
              disabled={page === pages - 1}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg disabled:opacity-30 hover:bg-gray-50 transition-colors"
            >
              Weiter →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('de-CH', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}
