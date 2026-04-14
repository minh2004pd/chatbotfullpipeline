import { useEffect, useState, useRef } from 'react'

/**
 * Debounce a value by delaying updates until the value stops changing.
 * Useful for filter states to prevent excessive API calls.
 */
export function useDebounceValue<T>(value: T, delayMs: number = 300): T {
  const [debounced, setDebounced] = useState(value)
  const timer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    if (timer.current) {
      clearTimeout(timer.current)
    }
    timer.current = setTimeout(() => {
      setDebounced(value)
    }, delayMs)

    return () => {
      if (timer.current) {
        clearTimeout(timer.current)
      }
    }
  }, [value, delayMs])

  return debounced
}
