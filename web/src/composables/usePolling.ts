import { onScopeDispose, ref } from 'vue'

export function usePolling(fn: () => Promise<void> | void, intervalMs = 2000) {
  const active = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null

  async function tick() {
    if (!active.value) return
    try {
      await fn()
    } catch {
      // swallow — caller handles errors via reactive state
    }
    if (active.value) timer = setTimeout(tick, intervalMs)
  }

  function start() {
    if (active.value) return
    active.value = true
    void tick()
  }

  function stop() {
    active.value = false
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  onScopeDispose(stop)
  return { active, start, stop }
}
