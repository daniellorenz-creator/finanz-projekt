'use client'

import { useMemo, useState } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'
import type { Transaction } from '@/lib/types'

interface Props {
  transactions: Transaction[]
  schuldenKeywordList: string[]
  fixkostenByMonth: Record<string, number>
  onMonthClick?: (key: string) => void
  selectedMonth?: string | null
}

interface MonthData {
  monat: string
  key: string
  einnahmen: number
  ausgaben: number
  schulden: number
  fixkosten: number
}

type SeriesKey = 'einnahmen' | 'ausgaben' | 'schulden' | 'fixkosten'

const SERIES: { key: SeriesKey; label: string; color: string; type: 'bar' | 'line' }[] = [
  { key: 'einnahmen', label: 'Einnahmen', color: '#22c55e', type: 'bar' },
  { key: 'ausgaben',  label: 'Ausgaben',  color: '#ef4444', type: 'bar' },
  { key: 'schulden',  label: 'Schulden',  color: '#f97316', type: 'bar' },
  { key: 'fixkosten', label: 'Fixkosten', color: '#6366f1', type: 'line' },
]

export default function MonthlyChart({ transactions, schuldenKeywordList, fixkostenByMonth, onMonthClick, selectedMonth }: Props) {
  const [hidden, setHidden] = useState<Set<SeriesKey>>(new Set())

  function handleChartClick(data: any) {
    const key = data?.activePayload?.[0]?.payload?.key
    if (key && onMonthClick) onMonthClick(key)
  }

  function toggle(key: SeriesKey) {
    setHidden(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const data: MonthData[] = useMemo(() => {
    const byMonth: Record<string, { einnahmen: number; ausgaben: number; schulden: number }> = {}

    for (const tx of transactions) {
      const key = tx.started_at.slice(0, 7)
      if (!byMonth[key]) byMonth[key] = { einnahmen: 0, ausgaben: 0, schulden: 0 }
      const amt = Number(tx.amount)
      if (amt > 0) byMonth[key].einnahmen += amt
      else byMonth[key].ausgaben += Math.abs(amt)
    }

    for (const tx of transactions) {
      const desc = (tx.description ?? '').toLowerCase()
      if (!schuldenKeywordList.some(kw => desc.includes(kw))) continue
      const key = tx.started_at.slice(0, 7)
      if (!byMonth[key]) byMonth[key] = { einnahmen: 0, ausgaben: 0, schulden: 0 }
      byMonth[key].schulden += Math.abs(Number(tx.amount))
    }

    // Alle Monate aus transactions + fixkostenByMonth vereinigen
    const allKeys = new Set([...Object.keys(byMonth), ...Object.keys(fixkostenByMonth)])

    return [...allKeys]
      .sort()
      .map(key => {
        const vals = byMonth[key] ?? { einnahmen: 0, ausgaben: 0, schulden: 0 }
        const [y, m] = key.split('-')
        const monat = new Date(Number(y), Number(m) - 1, 1)
          .toLocaleDateString('de-CH', { month: 'short', year: '2-digit' })
        return {
          key,
          monat,
          einnahmen: round(vals.einnahmen),
          ausgaben:  round(vals.ausgaben),
          schulden:  round(vals.schulden),
          fixkosten: round(fixkostenByMonth[key] ?? 0),
        }
      })
      .filter(d => d.einnahmen > 0 || d.ausgaben > 0 || d.fixkosten > 0)
  }, [transactions, schuldenKeywordList, fixkostenByMonth])

  if (data.length === 0) {
    return <p className="text-gray-400 text-center py-12">Keine Daten für den gewählten Zeitraum.</p>
  }

  return (
    <div>
      {/* Toggle-Buttons */}
      <div className="flex flex-wrap gap-2 mb-4">
        {SERIES.map(s => (
          <button
            key={s.key}
            onClick={() => toggle(s.key)}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-all ${
              hidden.has(s.key)
                ? 'border-gray-200 text-gray-400 bg-white'
                : 'border-transparent text-white'
            }`}
            style={hidden.has(s.key) ? {} : { backgroundColor: s.color }}
          >
            <span>{s.type === 'line' ? '—' : '■'}</span>
            {s.label}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart
          data={data}
          margin={{ top: 4, right: 16, left: 16, bottom: 4 }}
          onClick={handleChartClick}
          style={{ cursor: onMonthClick ? 'pointer' : 'default' }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="monat" tick={{ fontSize: 11, fill: '#6b7280' }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} tickLine={false} axisLine={false}
            tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)} />
          <Tooltip
            formatter={(value: number, name: string) => [
              value.toLocaleString('de-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
              SERIES.find(s => s.key === name)?.label ?? name,
            ]}
            labelStyle={{ fontWeight: 600 }}
            contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 13 }}
          />
          <Bar dataKey="einnahmen" fill="#22c55e" radius={[3, 3, 0, 0]} maxBarSize={32} hide={hidden.has('einnahmen')}>
            {selectedMonth && data.map(entry => (
              <Cell key={entry.key} fill="#22c55e" opacity={entry.key === selectedMonth ? 1 : 0.3} />
            ))}
          </Bar>
          <Bar dataKey="ausgaben" fill="#ef4444" radius={[3, 3, 0, 0]} maxBarSize={32} hide={hidden.has('ausgaben')}>
            {selectedMonth && data.map(entry => (
              <Cell key={entry.key} fill="#ef4444" opacity={entry.key === selectedMonth ? 1 : 0.3} />
            ))}
          </Bar>
          <Bar dataKey="schulden" fill="#f97316" radius={[3, 3, 0, 0]} maxBarSize={32} hide={hidden.has('schulden')}>
            {selectedMonth && data.map(entry => (
              <Cell key={entry.key} fill="#f97316" opacity={entry.key === selectedMonth ? 1 : 0.3} />
            ))}
          </Bar>
          <Line
            dataKey="fixkosten"
            stroke="#6366f1"
            strokeWidth={2}
            dot={{ r: 3, fill: '#6366f1' }}
            activeDot={{ r: 5 }}
            hide={hidden.has('fixkosten')}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function round(n: number) {
  return Math.round(n * 100) / 100
}
