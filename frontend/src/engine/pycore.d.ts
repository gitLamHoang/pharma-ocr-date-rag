/** The bundled pure Python core: path under backend/ -> source (see vite.pages.ts). */
declare module "virtual:pycore" {
  const files: Record<string, string>;
  export default files;
}
