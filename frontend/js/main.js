/*
  main.js
  Shared vanilla-JS utilities used by upload.js and dashboard.js:
  API base resolution, byte/time formatting and nav-link highlighting.
  No framework, no build step — loaded directly via <script> tags.
*/

// Resolve the API base URL. The backend serves the frontend itself, so in
// the common case this is just the same origin the page was loaded from.
const API_BASE = window.location.origin;

/**
 * Format a byte count into a human readable string (KB / MB / GB).
 * @param {number} bytes
 * @returns {string}
 */
function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "0 MB";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

/**
 * Format a duration in seconds into "1m 24s" style text.
 * @param {number} seconds
 * @returns {string}
 */
function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

/**
 * Format a unix timestamp (seconds) into a short relative/absolute string.
 * @param {number} timestamp
 * @returns {string}
 */
function formatTimestamp(timestamp) {
  if (!timestamp) return "—";
  const date = new Date(timestamp * 1000);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Highlight the current page's nav link based on the document path. */
function highlightActiveNavLink() {
  const currentFile = window.location.pathname.split("/").pop() || "index.html";
  document.querySelectorAll(".nav-link").forEach((link) => {
    const linkFile = link.getAttribute("href");
    link.classList.toggle("active", linkFile === currentFile);
  });
}

document.addEventListener("DOMContentLoaded", highlightActiveNavLink);

