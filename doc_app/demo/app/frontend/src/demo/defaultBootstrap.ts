/**
 * Default kiosk bootstrap source.
 *
 * Module role:
 *   Re-exports the kiosk_bootstrap (agent roster, dock agents + canned
 *   replies, classifications) from a single canonical scenario. This is
 *   the data that seeds the stores synchronously on app mount, before
 *   the user picks a scenario via the header scenario picker.
 *
 *   Switching the active "default" scenario is a one-line change here:
 *   point the import at a different scenarios/<name>/bootstrap module.
 *
 * Why this indirection exists:
 *   kioskBootstrap.ts and kioskReplies.ts both need synchronous access
 *   to the bootstrap subtree at module-load time (page refresh must
 *   render with agents and dock replies already present). They cannot
 *   wait for the dynamic scenario loader. This file gives them a single
 *   import that is statically bundled.
 *
 * Key collaborators:
 *   - kioskBootstrap.ts — calls seedKioskStores() with this data
 *   - kioskReplies.ts   — keys canned reply lookup off this data
 *   - scenarios/<id>/bootstrap.ts — owns the actual content
 */

/* The NGM busbar trip is the canonical demo scenario as of 2026-04-20.
   To switch the default, replace this import with another scenario's
   bootstrap export. */
export { bootstrap as defaultKioskBootstrap } from "./scenarios/ngm_busbar_trip/bootstrap";
