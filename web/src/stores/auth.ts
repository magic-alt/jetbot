import { defineStore } from 'pinia'

const KEY = 'jetbot.apiKey'

export const useAuthStore = defineStore('auth', {
  state: () => ({ apiKey: null as string | null }),
  actions: {
    load() {
      this.apiKey = localStorage.getItem(KEY)
    },
    setApiKey(v: string) {
      if (!v) {
        localStorage.removeItem(KEY)
        this.apiKey = null
      } else {
        localStorage.setItem(KEY, v)
        this.apiKey = v
      }
    },
  },
})
