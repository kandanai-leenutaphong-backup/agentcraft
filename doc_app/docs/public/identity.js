// Identity chip in the sidebar footer. Reads the platform auth endpoint, so it
// shows whoever Entra signed in — no identity state of our own.
// Loaded as a file (not inline) to satisfy script-src 'self'.

(async () => {
  const MOUNT_POLL_MS = 120
  const MOUNT_TIMEOUT_MS = 6000

  function initials(name) {
    const base = (name || '').split('@')[0].replace(/[._-]+/g, ' ').trim()
    const parts = base.split(/\s+/).filter(Boolean)
    return ((parts[0]?.[0] || '?') + (parts[1]?.[0] || '')).toUpperCase()
  }

  async function whoami() {
    try {
      const res = await fetch('/api/me', { credentials: 'same-origin', cache: 'no-store' })
      if (!res.ok) return null
      const data = await res.json()
      return data?.name || null
    } catch {
      return null // local preview, or the endpoint is unavailable
    }
  }

  function render(mount, identity) {
    const chip = document.createElement('div')
    chip.className = 'identity'
    chip.innerHTML = identity
      ? `<div class="identity__who" title="${identity}">
           <span class="identity__avatar">${initials(identity)}</span>
           <span class="identity__name">${identity}</span>
         </div>
         <a class="identity__signout" href="/.auth/logout?post_logout_redirect_uri=%2F">Sign out</a>`
      : `<div class="identity__who">
           <span class="identity__avatar identity__avatar--anon">–</span>
           <span class="identity__name identity__name--anon">No Entra session</span>
         </div>`
    mount.appendChild(chip)
  }

  function renderRepo(mount) {
    const a = document.createElement('a')
    a.className = 'sidebar-repo'
    a.href = 'https://github.com/han-microsoft/azure-hillclimbing'
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
    a.innerHTML =
      `<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/></svg>
       <span>Azure Native Hillclimbing Kit</span>`
    mount.appendChild(a)
  }

  function renderNote(mount) {
    const note = document.createElement('p')
    note.className = 'sidebar-note'
    note.textContent = 'Internal method note. Handwritten.'
    mount.appendChild(note)
  }

  // React hydration re-renders the sidebar and discards anything appended to it,
  // so mount idempotently and re-mount whenever the footer loses our nodes.
  let identity
  let resolved = false
  let mounting = false

  // Mount into our own body-level element rather than the sidebar's React tree:
  // appending into React-managed nodes gets reconciled away, and in the
  // production build the sidebar footer is prerendered empty.
  async function mount() {
    if (mounting || document.querySelector('.sidebar-dock')) return
    mounting = true
    try {
      if (!resolved) {
        identity = await whoami()
        resolved = true
      }
      if (document.querySelector('.sidebar-dock')) return
      const dock = document.createElement('div')
      dock.className = 'sidebar-dock'
      document.body.appendChild(dock)
      render(dock, identity)
      renderRepo(dock)
      renderNote(dock)
    } finally {
      mounting = false
    }
  }

  // /demo/ is served from this origin but is not a Vocs route. Harmless today,
  // since the strict CSP stops React hydrating and every link is already a full
  // navigation — but it keeps the demo reachable if hydration is ever restored.
  document.addEventListener(
    'click',
    (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey) return
      const link = event.target.closest && event.target.closest('a[href^="/demo"]')
      if (!link) return
      event.preventDefault()
      window.location.assign(link.getAttribute('href'))
    },
    true,
  )

  // DOM-ready, not 'load': waiting for the full bundle delays the dock by
  // seconds on the deployed site.
  if (document.readyState !== 'loading') mount()
  else document.addEventListener('DOMContentLoaded', mount, { once: true })
})()
