// The seam that lets the browser walks run against an authenticated deployment.
//
// The application denies every unauthenticated request, so a walk that opens `/` on a
// deployed host gets a sign-in redirect and nothing to check. It needs a credential — and the
// walks must not know what kind, or where it lives, or how it is applied. So they do not:
// they call `signContext(context, baseUrl)` after creating each browser context, and this
// file loads whatever the operator named in `CYBEREYE_SIGNING_MODULE`.
//
// That indirection is the point, not a workaround. `deploy/` owns the client half of signed
// developer access and is the thing that knows where an operator's private key lives; the
// frontend must not import it, because the dependency runs the other way — operations verify
// the application, the application does not reach into operations. Naming the module at the
// process boundary keeps the direction honest, exactly as the server side injects
// `identity_factory` rather than importing a principal type.
//
// Unset, this is a no-op, so a local run against `dev.sh` behaves exactly as it always has.
// Set and broken, it throws: a walk that silently ran unsigned would report the sign-in page's
// missing controls as application defects.
//
//   CYBEREYE_URL=https://<host> \
//   CYBEREYE_SIGNING_MODULE=/abs/path/to/deploy/browser_pilot.mjs \
//   node app/cybereye/frontend/tests/browser/verify-ui5.mjs

let loaded = null;

/** The module named by CYBEREYE_SIGNING_MODULE, loaded once, or null when none is named. */
async function signer() {
  if (loaded !== null) return loaded;
  const path = process.env.CYBEREYE_SIGNING_MODULE;
  if (!path) {
    loaded = false;
    return loaded;
  }
  const module = await import(path.startsWith('/') ? `file://${path}` : path);
  if (typeof module.installRequestSigning !== 'function') {
    throw new Error(`${path} exports no installRequestSigning(context, options)`);
  }
  loaded = module;
  return loaded;
}

/**
 * Give one browser context a credential, if the operator supplied one.
 *
 * Per-context, not per-run: each `newContext()` in a walk is a separate browser with its own
 * storage, and a walk that signs only the first one proves nothing about the others.
 */
export async function signContext(context, baseUrl, contextSlug = 'verify') {
  const module = await signer();
  if (!module) return false;
  await module.installRequestSigning(context, { baseUrl, contextSlug });
  return true;
}

/** Whether this run is carrying a credential. Reported so a log says which walk happened. */
export function signingConfigured() {
  return Boolean(process.env.CYBEREYE_SIGNING_MODULE);
}
