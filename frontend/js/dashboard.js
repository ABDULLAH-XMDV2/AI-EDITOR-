/*
  dashboard.js
  Polls /api/dashboard/stats and /api/dashboard/jobs to render the summary
  cards and job history table, refreshing automatically every few seconds
  so the queue/progress numbers stay live without a manual reload.
*/

const REFRESH_INTERVAL_MS = 3000;

const totalVideosEl = document.getElementById("statTotalVideos");
const queueEl = document.getElementById("statQueue");
const completedEl = document.getElementById("statCompleted");
const failedEl = document.getElementById("statFailed");
const storageEl = document.getElementById("statStorage");
const jobsTableBody = document.getElementById("jobsTableBody");
const emptyState = document.getElementById("emptyState");

const STATUS_BADGE_CLASS = {
  completed: "badge-completed",
  processing: "badge-processing",
  queued: "badge-queued",
  failed: "badge-failed",
};

/** Fetch and render the four/five summary stat cards. */
async function refreshStats() {
  try {
    const res = await fetch(`${API_BASE}/api/dashboard/stats`);
    const stats = await res.json();

    totalVideosEl.textContent = stats.total_videos;
    queueEl.textContent = stats.processing_queue;
    completedEl.textContent = stats.completed_edits;
    failedEl.textContent = stats.failed_jobs;
    storageEl.textContent = formatBytes(stats.storage_usage_bytes);
  } catch (err) {
    console.warn("Failed to refresh dashboard stats:", err);
  }
}

/** Fetch and render the recent jobs table. */
async function refreshJobs() {
  try {
    const res = await fetch(`${API_BASE}/api/dashboard/jobs?limit=50`);
    const data = await res.json();
    renderJobsTable(data.jobs);
  } catch (err) {
    console.warn("Failed to refresh job list:", err);
  }
}

/** Render the jobs array into the table body, or show the empty state. */
function renderJobsTable(jobs) {
  if (!jobs.length) {
    jobsTableBody.innerHTML = "";
    emptyState.classList.remove("hidden");
    return;
  }
  emptyState.classList.add("hidden");

  jobsTableBody.innerHTML = jobs
    .map((job) => {
      const badgeClass = STATUS_BADGE_CLASS[job.status] || "badge-queued";
      const sizeText = job.output_size_bytes
        ? formatBytes(job.output_size_bytes)
        : formatBytes(job.input_size_bytes);
      const progressText = job.status === "processing" ? `${job.progress}%` : "";

      return `
        <tr>
          <td>${escapeHtml(job.original_filename)}</td>
          <td><span class="badge ${badgeClass}">${job.status} ${progressText}</span></td>
          <td class="mono text-muted">${escapeHtml(job.current_step || "—")}</td>
          <td class="mono">${sizeText}</td>
          <td class="text-muted">${formatTimestamp(job.created_at)}</td>
        </tr>
      `;
    })
    .join("");
}

/** Minimal HTML escaping for filenames rendered into the table. */
function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value || "";
  return div.innerHTML;
}

function startDashboardPolling() {
  refreshStats();
  refreshJobs();
  setInterval(refreshStats, REFRESH_INTERVAL_MS);
  setInterval(refreshJobs, REFRESH_INTERVAL_MS);
}

document.addEventListener("DOMContentLoaded", startDashboardPolling);
