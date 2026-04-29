/**
 * hooks/useAsync.js — Tiny hook for async data-fetching.
 *
 * Usage:
 *   const { data, loading, error, execute } = useAsync(api.listTraces)
 *   useEffect(() => { execute() }, [execute])
 */
import { useState, useCallback, useEffect, useRef } from 'react'

export function useAsync(asyncFn) {
  const [state, setState] = useState({ data: null, loading: false, error: null })
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const execute = useCallback(
    async (...args) => {
      setState({ data: null, loading: true, error: null })
      try {
        const data = await asyncFn(...args)
        if (mounted.current) setState({ data, loading: false, error: null })
        return data
      } catch (err) {
        if (mounted.current)
          setState({ data: null, loading: false, error: err?.message ?? String(err) })
        throw err
      }
    },
    [asyncFn]
  )

  return { ...state, execute }
}
