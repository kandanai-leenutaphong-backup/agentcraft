/**
 * toastStore \u2014 transient notification queue.
 *
 * Purpose:
 *   Hold a short-lived array of toast notifications. Features elsewhere
 *   (situation escalation watcher, command palette, etc.) push toasts
 *   via `pushToast()`; the `<Toaster />` component renders them, and
 *   each toast auto-dismisses after `durationMs` unless dismissed by
 *   the user.
 *
 * Why a store and not local state:
 *   Any component anywhere in the tree must be able to raise a toast
 *   without prop-drilling. Keeping the queue in Zustand lets event
 *   watchers (which are not React components) publish toasts, and lets
 *   the <Toaster /> component render from a single source of truth.
 *
 * Collaborators:
 *   - components/shared/Toaster.tsx       renders active toasts
 *   - features/situation/escalationWatcher.ts  emits toasts on severity
 *                                             upgrade between scans
 */

import { create } from "zustand";

/** Toast severity tone \u2014 drives the left strip + icon colour. */
export type ToastTone = "info" | "success" | "warning" | "error";

/** One toast record. `id` is an auto-incrementing number kept in the store. */
export interface ToastEntry {
  id: number;
  title: string;
  /** Optional second line \u2014 longer context or station codes. */
  body?: string;
  tone: ToastTone;
  /** Milliseconds until auto-dismiss. Set to 0 to disable auto-dismiss. */
  durationMs: number;
  /** When true, the toast will flash / pulse to grab attention. */
  pulse?: boolean;
}

/** Argument to pushToast \u2014 `id` is assigned by the store. */
export type ToastInput = Omit<ToastEntry, "id">;

interface ToastStore {
  toasts: ToastEntry[];
  /** Append a toast. Returns the assigned id so callers can dismiss it early. */
  pushToast: (input: ToastInput) => number;
  /** Remove the toast with the given id. No-op if id is gone. */
  dismissToast: (id: number) => void;
  /** Clear all toasts (used when the operator logs out or clears panels). */
  clearToasts: () => void;
}

/* Monotonic id counter \u2014 lives in module scope so multiple store resets
   in tests do not collide. */
let nextId = 1;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],

  pushToast: (input) => {
    const id = nextId++;
    const entry: ToastEntry = { id, ...input };
    set((state) => ({ toasts: [...state.toasts, entry] }));
    return id;
  },

  dismissToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  clearToasts: () => set({ toasts: [] }),
}));
