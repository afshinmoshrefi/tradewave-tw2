// Registry of in-flight viewer loads that a Tara transaction may cancel.
//
// A load generation is bumped ONLY by a Tara action. A viewer request the user
// starts after that transaction reaches a terminal state therefore reuses the
// SAME generation. Cancelling a whole generation aborted those requests too, so
// the first manual change after a Tara action (a month, a date, a years value)
// was killed before it left the browser. Nothing recovered it: an aborted fetch
// returns without reporting a terminal state, so the viewer stayed on
// 'loading' and the chart never came back until the control was changed twice.
//
// Entries therefore carry the request key they belong to, and a cancel scoped
// to a key touches only that transaction's own loads. This does not weaken the
// stale-response protection: while a transaction is loading,
// `taraActionAllowsViewerRequest` admits a request only when its key already
// equals the transaction's key, so a scoped cancel covers exactly the same
// loads a generation-wide cancel did.
export const createTaraLoadAborters = () => {
  const byGeneration = new Map()

  const register = (generation, abortLoad, requestKey) => {
    if (!Number.isInteger(generation) || typeof abortLoad !== 'function') {
      return () => {}
    }
    if (!byGeneration.has(generation)) byGeneration.set(generation, new Set())
    const entries = byGeneration.get(generation)
    const entry = { abortLoad, requestKey: String(requestKey || '') }
    entries.add(entry)
    return () => {
      entries.delete(entry)
      if (entries.size === 0) byGeneration.delete(generation)
    }
  }

  // requestKey scopes the cancel to the loads of one transaction's view.
  // Omitting it keeps the previous generation-wide behaviour.
  const cancel = (generation, requestKey) => {
    const entries = byGeneration.get(generation)
    if (!entries) return 0
    const target = String(requestKey || '')
    let cancelled = 0
    for (const entry of Array.from(entries)) {
      if (target && entry.requestKey !== target) continue
      entries.delete(entry)
      cancelled += 1
      try {
        entry.abortLoad()
      } catch (err) {
        console.warn('Tara load cancellation failed:', err?.message || err)
      }
    }
    if (entries.size === 0) byGeneration.delete(generation)
    return cancelled
  }

  // A completed transaction simply drops its bookkeeping - nothing is aborted.
  const release = (generation) => {
    byGeneration.delete(generation)
  }

  const pendingCount = (generation) => {
    const entries = byGeneration.get(generation)
    return entries ? entries.size : 0
  }

  return { register, cancel, release, pendingCount }
}
