// Resolve the backend base URL once, shared by every view.
//
// Priority:
//   1. VITE_API_URL — an explicit override baked at build time. Set it only when
//      the backend lives on a different host/port than the page that loads it.
//   2. Otherwise derive the base from the page's own origin, so the app works
//      both on localhost AND when reached from another machine over the LAN:
//      a page served from 10.200.192.4:5173 then calls the backend on
//      10.200.192.4:8000. Using window.location.hostname (not the literal
//      "localhost") is exactly what makes remote access work without rebuilding
//      the bundle per host.
const BACKEND_PORT = '8000';

function resolveApiUrl() {
  const configured = import.meta.env.VITE_API_URL;
  if (configured) return configured;
  if (typeof window !== 'undefined' && window.location) {
    return window.location.protocol + '//' + window.location.hostname + ':' + BACKEND_PORT;
  }
  // SSR / tests without a window: fall back to the local dev backend.
  return 'http://localhost:' + BACKEND_PORT;
}

export const API_URL = resolveApiUrl();
