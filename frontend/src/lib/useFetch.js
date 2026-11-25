import { useCallback, useEffect, useRef, useState } from 'react'

// Small data hook: loading + error + manual reload, ignores out-of-order responses.
export function useFetch(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  const run = useCallback(async () => {
    const mine = ++seq.current
    setLoading(true)
    try {
      const d = await fn()
      if (mine === seq.current) { setData(d); setError(null) }
    } catch (e) {
      if (mine === seq.current) setError(e.message || 'Something went wrong')
    } finally {
      if (mine === seq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { run() }, [run])
  return { data, error, loading, reload: run }
}
