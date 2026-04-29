/**
 * hooks/useKeyboard.js — Global "g <key>" chord keyboard shortcuts.
 *
 * The shortcut map accepts plain keys (single press) or chord strings like
 * "g d" (two sequential key presses within 600ms).
 */
import { useEffect, useRef } from 'react'

export function useKeyboard(shortcuts) {
  const pending = useRef(null) // first key of a chord

  useEffect(() => {
    function onKeyDown(e) {
      // Don't hijack shortcuts while typing in form elements
      const tag = e.target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.metaKey || e.ctrlKey || e.altKey) return

      const key = e.key

      // Try chord first: "g d", "g t", etc.
      if (pending.current) {
        const chord = `${pending.current} ${key}`
        if (shortcuts[chord]) {
          e.preventDefault()
          shortcuts[chord]()
          pending.current = null
          return
        }
        // Not a valid chord continuation — try as standalone
        pending.current = null
      }

      // Check if this key starts a chord
      const isChordStart = Object.keys(shortcuts).some(
        (s) => s.includes(' ') && s.startsWith(key + ' ')
      )
      if (isChordStart) {
        pending.current = key
        setTimeout(() => { pending.current = null }, 600)
        return
      }

      // Plain shortcut
      if (shortcuts[key]) {
        e.preventDefault()
        shortcuts[key]()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [shortcuts])
}
