/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `static` for the GitHub Pages build (in-browser engine, no server). */
  readonly VITE_MODE?: string;
}
