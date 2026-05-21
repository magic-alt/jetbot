declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const c: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default c
}
