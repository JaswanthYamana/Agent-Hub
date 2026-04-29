/**
 * store/useStore.js — Zustand global state.
 * Shared state only: backend health, toasts, active trace ID, traces list.
 * View-specific state lives in local component hooks.
 */
import { create } from 'zustand'
import api from '../services/api'

let _toastId = 0

export const useStore = create((set, get) => ({
  // ── Backend health ────────────────────────────────────────────────────
  backendOnline: null, // null = unknown
  checkHealth: async () => {
    try {
      await api.health()
      set({ backendOnline: true })
    } catch {
      set({ backendOnline: false })
    }
  },

  // ── Toast notifications ───────────────────────────────────────────────
  toasts: [],
  toast: (message, type = 'info') => {
    const id = ++_toastId
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }))
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, 3500)
  },
  dismissToast: (id) => {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
  },

  // ── Shared active trace (cross-view linking) ──────────────────────────
  activeTraceId: null,
  setActiveTrace: (id) => set({ activeTraceId: id }),
}))

export default useStore
