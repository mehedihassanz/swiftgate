/**
 * Legacy auth module — now redirects to userAuth.
 *
 * SwiftGate has unified auth: all users sign in via the portal (/portal/login).
 * Admin users (emails in ADMIN_EMAILS) get access to admin routes via the same
 * JWT. The old X-Admin-Key header approach still works for API automation.
 *
 * authFetch() is kept as a thin wrapper around userFetch() so existing pages
 * don't need to change their imports.
 */
export { useUserAuth as useAuth } from "./userAuth";
export { userFetch as authFetch } from "./userAuth";
