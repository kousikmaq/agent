// Email-only login. Access is restricted to a single company email domain.
export const ALLOWED_DOMAIN = "maqsoftware.com";

export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function isAllowedEmail(email) {
  const e = String(email || "").trim().toLowerCase();
  return EMAIL_RE.test(e) && e.endsWith(`@${ALLOWED_DOMAIN}`);
}

// Derive a friendly display name from the email local part.
// e.g. "kousik.maity@maqsoftware.com" -> "Kousik Maity"
export function nameFromEmail(email) {
  const local = String(email || "").split("@")[0] || "user";
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ") || "User";
}
