/** Router basename from <base href> (set by the backend to the URL base). */
export function routerBasename(): string {
  const path = new URL(document.baseURI).pathname
  return path.endsWith("/") ? path.slice(0, -1) || "/" : path
}
