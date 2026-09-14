# NEXUS Research Web

React 19 + Vite + Ant Design frontend for the NEXUS Research FastAPI backend.

~~~powershell
Copy-Item .env.example .env
pnpm install
pnpm dev
~~~

Default HTTP API: http://127.0.0.1:8000

Default WebSocket: ws://127.0.0.1:8000

Environment variables: VITE_APP_NAME, VITE_APP_TAGLINE, VITE_API_BASE_URL, VITE_WS_BASE_URL.
