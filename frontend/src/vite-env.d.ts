/*
 * 이 파일은 프론트엔드에서 vite env.d 역할을 담당한다.
 */
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_NAME?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_WS_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
