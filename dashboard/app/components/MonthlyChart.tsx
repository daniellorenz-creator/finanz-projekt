'use client'

import { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts'
import type { Transaction } from '@/lib/types'

interface Props { transactions: Transaction[] }

interface MonthData {
  monat: string   // 'Jan 24'
  einnahmen: number
  ausgaben: number
}

export default function MonthlyChart({ transactions }: Props) {
  const data: MonthData[] = useMemo(() => {
    const byMonth: Record<string, { einnahmen: number; ausgaben: number }> = {}
    for (const tx of transactions) {
      const key = tx.started_at.slice(0, 7) // 'YYYY-MM'
      if (!byMonth[key]) byMonth[key] = { einnahmen: 0, ausgaben: 0 }
      const amt = Number(tx.amount)
      if (amt > 0) byMonth[key].einnahmen += amt
      else byMonth[key].ausgaben += Math.abs(amt)
    }
    return Object.entries(byMonth)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, vals]) => {
        const [y, m] = key.split('-')
        const monat = new Date(Number(y), Number(m) - 1, 1)
          .toLocaleDateString('de-CH', { month: 'short', year: '2-digit' })
        return { monat, einnahmen: round(vals.einnahmen), ausgaben: round(vals.ausgaben) }
      })
  }, [transactions])

  if (data.length === 0) {
    return <p className="text-gray-400 text-center py-12">Keine Daten für den gewählten Zeitraum.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 4, right: 16, left: 16, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="monat"
          tick={{ fontSize: 11, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: '#6b7280' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)}
        />
        <Tooltip
          formatter={(value: number) =>
            value.toLocaleString('de-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
          }
          labelStyle={{ fontWeight: 600 }}
          contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 13 }}
        />
        <Legend
          wrapperStyle={{ fontSize: 13, paddingTop: 8 }}
          formatter={(value) => value === 'einnahmen' ? 'Einnahmen' : 'Ausgaben'}
        />
        <Bar dataKey="einnahmen" fill="#22c55e" radius={[3, 3, 0, 0]} maxBarSize={40} />
        <Bar dataKey="ausgaben"  fill="#ef4444" radius={[3, 3, 0, 0]} maxBarSize={40} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function round(n: number) {
  return Math.round(n * 100) / 100
}
