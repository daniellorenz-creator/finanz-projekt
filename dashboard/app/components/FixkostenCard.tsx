'use client'

import { useState, useMemo, useEffect, useRef } from 'react'
import type { Transaction } from '@/lib/types'

type ManuellerEintrag = {
  id: string
  name: string
  betrag: string
  währung: string
}

type ErkannterEintrag = {
  key: string
  label: string
  schnitt: number
  schnittByJahr: Record<string, number>
  währung: string
  monate: number
}

interface Props {
  transactions: Transaction[]
  onFixkostenChange?: (byMonth: Record<string, number>) => void
}

const WÄHRUNGEN = ['EUR', 'CHF', 'CAD', 'USD']

function normalize(desc: string): string {
  return desc
    .toLowerCase()
    .replace(/\b\d{4,}\b/g, '')
    .replace(/\d+[.,]\d{2}/g, '')
    .replace(/[^a-zäöüß\s]/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .split(' ')
    .slice(0, 5)
    .join(' ')
}

export default function FixkostenCard({ transactions, onFixkostenChange }: Props) {
  const [manuell, setManuell]             = useState<ManuellerEintrag[]>([])
  const [ausgewählt, setAusgewählt]       = useState<Set<string>>(new Set())
  const [dropdownOffen, setDropdownOffen] = useState(false)
  const [suche, setSuche]                 = useState('')

  const [newName, setNewName]           = useState('')
  const [newBetrag, setNewBetrag]       = useState('')
  const [newWährung, setNewWährung]     = useState('EUR')
  const [positionSuche, setPositionSuche] = useState('')

  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const m = localStorage.getItem('fixkosten_manuell')
    const a = localStorage.getItem('fixkosten_ausgewaehlt')
    if (m) setManuell(JSON.parse(m))
    if (a) setAusgewählt(new Set(JSON.parse(a)))
  }, [])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node))
        setDropdownOffen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function saveManuell(list: ManuellerEintrag[]) {
    setManuell(list)
    localStorage.setItem('fixkosten_manuell', JSON.stringify(list))
  }

  function saveAusgewählt(set: Set<string>) {
    setAusgewählt(set)
    localStorage.setItem('fixkosten_ausgewaehlt', JSON.stringify([...set]))
  }

  function toggleAuswahl(key: string) {
    const next = new Set(ausgewählt)
    next.has(key) ? next.delete(key) : next.add(key)
    saveAusgewählt(next)
  }

  function addManuell() {
    if (!newName || !newBetrag) return
    saveManuell([...manuell, { id: crypto.randomUUID(), name: newName, betrag: newBetrag, währung: newWährung }])
    setNewName(''); setNewBetrag('')
  }

  function removeManuell(id: string) {
    saveManuell(manuell.filter(e => e.id !== id))
  }

  const alleMonate = useMemo(() =>
    [...new Set(transactions.map(tx => tx.started_at.slice(0, 7)))].sort()
  , [transactions])

  const alleJahre = useMemo(() =>
    [...new Set(alleMonate.map(m => m.slice(0, 4)))].sort()
  , [alleMonate])

  // Erkennungs-Algorithmus – berechnet Ø pro Jahr
  const kandidaten = useMemo((): ErkannterEintrag[] => {
    const groups: Record<string, Transaction[]> = {}
    for (const tx of transactions) {
      const desc = tx.description ?? ''
      if (!desc) continue
      const key = normalize(desc)
      if (!key || key.length < 3) continue
      if (!groups[key]) groups[key] = []
      groups[key].push(tx)
    }
    const result: ErkannterEintrag[] = []
    for (const [key, txs] of Object.entries(groups)) {
      const monate = new Set(txs.map(tx => tx.started_at.slice(0, 7)))
      if (monate.size < 2) continue
      const ausgaben = txs.filter(tx => Number(tx.amount) < 0)
      if (ausgaben.length < 2) continue
      const gesamt  = ausgaben.reduce((s, tx) => s + Math.abs(Number(tx.amount)), 0)
      const schnitt = gesamt / monate.size
      if (schnitt < 5) continue

      // Ø pro Jahr berechnen
      const schnittByJahr: Record<string, number> = {}
      const jahre = new Set(ausgaben.map(tx => tx.started_at.slice(0, 4)))
      for (const jahr of jahre) {
        const jahresAusgaben = ausgaben.filter(tx => tx.started_at.startsWith(jahr))
        const jahresMonate   = new Set(jahresAusgaben.map(tx => tx.started_at.slice(0, 7)))
        const jahresGesamt   = jahresAusgaben.reduce((s, tx) => s + Math.abs(Number(tx.amount)), 0)
        schnittByJahr[jahr]  = jahresGesamt / jahresMonate.size
      }

      const freq: Record<string, number> = {}
      for (const tx of ausgaben) freq[tx.description ?? ''] = (freq[tx.description ?? ''] ?? 0) + 1
      const label = Object.entries(freq).sort((a, b) => b[1] - a[1])[0][0]
      result.push({ key, label, schnitt, schnittByJahr, währung: ausgaben[0].currency, monate: monate.size })
    }
    return result.sort((a, b) => b.monate - a.monate)
  }, [transactions])

  const gefiltertKandidaten = useMemo(() =>
    suche ? kandidaten.filter(k => k.label.toLowerCase().includes(suche.toLowerCase())) : kandidaten
  , [kandidaten, suche])

  const ausgewähltEinträge = useMemo(() =>
    kandidaten.filter(k => ausgewählt.has(k.key))
  , [kandidaten, ausgewählt])

  // Monatliche Fixkosten – jahresspezifischer Wert pro Monat
  const fixkostenByMonth = useMemo(() => {
    const byMonth: Record<string, number> = {}
    for (const monat of alleMonate) {
      const jahr = monat.slice(0, 4)
      let total = 0
      for (const e of manuell) {
        total += parseFloat(e.betrag.replace(',', '.')) || 0
      }
      for (const eintrag of ausgewähltEinträge) {
        total += eintrag.schnittByJahr[jahr] ?? eintrag.schnitt
      }
      byMonth[monat] = round(total)
    }
    return byMonth
  }, [alleMonate, manuell, ausgewähltEinträge])

  useEffect(() => {
    onFixkostenChange?.(fixkostenByMonth)
  }, [fixkostenByMonth, onFixkostenChange])

  // Totals pro Jahr und Währung
  const totalsByJahr = useMemo(() => {
    const byJahr: Record<string, Record<string, number>> = {}
    for (const jahr of alleJahre) {
      byJahr[jahr] = {}
      for (const e of manuell) {
        const b = parseFloat(e.betrag.replace(',', '.')) || 0
        byJahr[jahr][e.währung] = (byJahr[jahr][e.währung] ?? 0) + b
      }
      for (const e of ausgewähltEinträge) {
        const val = e.schnittByJahr[jahr] ?? e.schnitt
        byJahr[jahr][e.währung] = (byJahr[jahr][e.währung] ?? 0) + val
      }
    }
    return byJahr
  }, [alleJahre, manuell, ausgewähltEinträge])

  const hatTotals = manuell.length > 0 || ausgewähltEinträge.length > 0

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-5">Fixkosten</h2>

      {/* Positions-Suche */}
      <div className="mb-5">
        <input
          type="text"
          placeholder="Position suchen (z.B. Spotify, DKV, Miete)…"
          value={positionSuche}
          onChange={e => setPositionSuche(e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        {positionSuche && (
          <div className="mt-2 border border-gray-100 rounded-lg overflow-hidden">
            {manuell.filter(e => e.name.toLowerCase().includes(positionSuche.toLowerCase())).map(e => (
              <div key={e.id} className="flex items-center justify-between px-3 py-2 hover:bg-gray-50 border-b border-gray-50 last:border-0">
                <span className="text-sm text-gray-700">{e.name}</span>
                <span className="text-xs font-mono text-gray-500">{fmt(parseFloat(e.betrag.replace(',', '.')) || 0)} {e.währung} / Mt. · Manuell</span>
              </div>
            ))}
            {kandidaten.filter(k => k.label.toLowerCase().includes(positionSuche.toLowerCase())).map(k => (
              <div key={k.key} className="flex items-center justify-between px-3 py-2 hover:bg-gray-50 border-b border-gray-50 last:border-0">
                <div className="flex items-center gap-2">
                  <input type="checkbox" checked={ausgewählt.has(k.key)} onChange={() => toggleAuswahl(k.key)}
                    className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                  <span className="text-sm text-gray-700 truncate max-w-xs" title={k.label}>{k.label}</span>
                </div>
                <span className="text-xs font-mono text-gray-500">Ø {fmt(k.schnitt)} {k.währung} · {k.monate} Mt.</span>
              </div>
            ))}
            {manuell.filter(e => e.name.toLowerCase().includes(positionSuche.toLowerCase())).length === 0 &&
             kandidaten.filter(k => k.label.toLowerCase().includes(positionSuche.toLowerCase())).length === 0 && (
              <div className="px-3 py-3 text-sm text-gray-400 text-center">Keine Treffer</div>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

        {/* Manuell */}
        <div>
          <h3 className="text-sm font-semibold text-gray-600 mb-3">Manuell</h3>
          {manuell.length > 0 && (
            <table className="w-full text-sm mb-4">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left pb-2 text-xs text-gray-400 font-medium">Bezeichnung</th>
                  <th className="text-right pb-2 text-xs text-gray-400 font-medium">Betrag / Mt.</th>
                  <th className="w-6" />
                </tr>
              </thead>
              <tbody>
                {manuell.map(e => (
                  <tr key={e.id} className="border-b border-gray-50">
                    <td className="py-2 text-gray-700">{e.name}</td>
                    <td className="py-2 text-right font-mono text-gray-700">
                      {fmt(parseFloat(e.betrag.replace(',', '.')) || 0)} {e.währung}
                    </td>
                    <td className="py-2 pl-2">
                      <button onClick={() => removeManuell(e.id)} className="text-gray-300 hover:text-red-400 text-lg leading-none">×</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="flex gap-2 flex-wrap">
            <input type="text" placeholder="Bezeichnung" value={newName}
              onChange={e => setNewName(e.target.value)} onKeyDown={e => e.key === 'Enter' && addManuell()}
              className="flex-1 min-w-[120px] border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            <input type="text" placeholder="Betrag" value={newBetrag}
              onChange={e => setNewBetrag(e.target.value)} onKeyDown={e => e.key === 'Enter' && addManuell()}
              className="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            <select value={newWährung} onChange={e => setNewWährung(e.target.value)}
              className="border border-gray-300 rounded-lg px-2 py-2 text-sm bg-white focus:ring-2 focus:ring-blue-500">
              {WÄHRUNGEN.map(w => <option key={w}>{w}</option>)}
            </select>
            <button onClick={addManuell} disabled={!newName || !newBetrag}
              className="px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-30 transition-colors">
              + Hinzufügen
            </button>
          </div>
        </div>

        {/* Automatisch erkannt */}
        <div>
          <h3 className="text-sm font-semibold text-gray-600 mb-3">
            Automatisch erkannt
            <span className="ml-2 text-xs font-normal text-gray-400">{kandidaten.length} Positionen gefunden</span>
          </h3>

          <div className="relative mb-4" ref={dropdownRef}>
            <button onClick={() => setDropdownOffen(o => !o)}
              className="w-full flex items-center justify-between border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white hover:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500">
              <span className="text-gray-600">
                {ausgewählt.size === 0 ? 'Positionen auswählen…' : `${ausgewählt.size} Position${ausgewählt.size !== 1 ? 'en' : ''} ausgewählt`}
              </span>
              <span className="text-gray-400 ml-2">{dropdownOffen ? '▲' : '▼'}</span>
            </button>

            {dropdownOffen && (
              <div className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg">
                <div className="p-2 border-b border-gray-100">
                  <input type="text" placeholder="Suchen…" value={suche}
                    onChange={e => setSuche(e.target.value)} autoFocus
                    className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
                </div>
                <div className="px-3 py-1.5 flex gap-3 border-b border-gray-100">
                  <button onClick={() => saveAusgewählt(new Set(kandidaten.map(k => k.key)))} className="text-xs text-blue-600 hover:underline">Alle auswählen</button>
                  <button onClick={() => saveAusgewählt(new Set())} className="text-xs text-gray-400 hover:underline">Alle abwählen</button>
                </div>
                <ul className="max-h-72 overflow-y-auto divide-y divide-gray-50">
                  {gefiltertKandidaten.length === 0 && (
                    <li className="px-3 py-4 text-sm text-gray-400 text-center">Keine Treffer</li>
                  )}
                  {gefiltertKandidaten.map(k => (
                    <li key={k.key}>
                      <label className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-50 cursor-pointer">
                        <input type="checkbox" checked={ausgewählt.has(k.key)} onChange={() => toggleAuswahl(k.key)}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                        <span className="flex-1 text-sm text-gray-700 truncate" title={k.label}>{k.label}</span>
                        <span className="text-xs text-gray-400 whitespace-nowrap ml-2">{k.monate} Mt.</span>
                        <span className="text-xs font-mono text-gray-600 whitespace-nowrap ml-1">Ø {fmt(k.schnitt)} {k.währung}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Ausgewählte Einträge – Ø pro Jahr */}
          {ausgewähltEinträge.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="text-left pb-2 text-xs text-gray-400 font-medium">Position</th>
                    {alleJahre.map(j => (
                      <th key={j} className="text-right pb-2 text-xs text-gray-400 font-medium pr-1">{j}</th>
                    ))}
                    <th className="w-6" />
                  </tr>
                </thead>
                <tbody>
                  {ausgewähltEinträge.map(e => (
                    <tr key={e.key} className="border-b border-gray-50">
                      <td className="py-2 text-gray-700 text-xs max-w-[150px] truncate" title={e.label}>{e.label}</td>
                      {alleJahre.map(j => (
                        <td key={j} className="py-2 text-right font-mono text-gray-700 pr-1 text-xs">
                          {e.schnittByJahr[j] != null
                            ? <>{fmt(e.schnittByJahr[j])} <span className="text-gray-400">{e.währung}</span></>
                            : <span className="text-gray-300">—</span>
                          }
                        </td>
                      ))}
                      <td className="py-2 pl-1">
                        <button onClick={() => toggleAuswahl(e.key)} className="text-gray-300 hover:text-red-400 text-lg leading-none">×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Totals pro Jahr */}
      {hatTotals && (
        <div className="mt-6 pt-5 border-t border-gray-100">
          <span className="text-sm font-semibold text-gray-500 block mb-3">Fixkosten / Monat nach Jahr:</span>
          <div className="flex flex-wrap gap-6">
            {alleJahre.map(jahr => {
              const jahresTotal = totalsByJahr[jahr] ?? {}
              if (Object.keys(jahresTotal).length === 0) return null
              return (
                <div key={jahr} className="text-center">
                  <p className="text-xs text-gray-400 mb-1">{jahr}</p>
                  {Object.entries(jahresTotal).sort().map(([cur, sum]) => (
                    <div key={cur}>
                      <p className="text-2xl font-bold text-gray-800">{fmt(sum)}</p>
                      <p className="text-xs text-gray-400">{cur}</p>
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function fmt(n: number) {
  return n.toLocaleString('de-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function round(n: number) {
  return Math.round(n * 100) / 100
}
