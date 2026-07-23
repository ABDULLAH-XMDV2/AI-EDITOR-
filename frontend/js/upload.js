/*
  upload.js
  Drives the entire upload -> AI processing -> preview -> download flow on
  upload.html. Uses XMLHttpRequest (not fetch) for the upload specifically
  because XHR exposes upload progress events that fetch does not.
*/

// Ordered pipeline steps shown in the "AI is editing your video" panel.
// Keys must match the `current_step` values written by pipeline.py.
const PIPELINE_STEPS = [
  { key: "validating", label: "Validating & preparing video" },
  { key: "detecting_scenes", label: "Detecting scenes" },
  { key: "removing_silence", label: "Removing silent parts" },
  { key: "detecting_faces", label: "Detecting faces" },
  { key: "auto_cropping", label: "Auto cropping & zooming" },
  { key: "enhancing_color", label: "Enhancing color, brightness & sharpness" },
  { key: "stabilizing", label: "Stabilizing footage" },
  { key: "normalizing_audio", label: "Normalizing audio" },
  { key: "generating_subtitles", label: "Generating subtitles" },
  { key: "burning_subtitles", label: "Burning in subtitles" },
  { key: "adding_music", label: "Mixing background music" },
  { key: "smart_transitions", label: "Applying smart transitions" },
  { key: "exporting_720p", label: "Exporting 720p" },
  { key: "exporting_1080p", label: "Exporting 1080p" },
];

let selectedFile = null;
let selectedMusicFile = null;
let pollTimer = null;

// ---------------------------------------------------------------------------
// Element references
// ---------------------------------------------------------------------------
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const originalPreview = document.getElementById("originalPreview");
const originalVideo = document.getElementById("originalVideo");
const optionsPanel = document.getElementById("optionsPanel");
const musicInput = document.getElementById("musicInput");
const musicFileName = document.getElementById("musicFileName");
const startButton = document.getElementById("startButton");
const uploadProgressWrap = document.getElementById("uploadProgressWrap");
const uploadProgressFill = document.getElementById("uploadProgressFill");
const uploadProgressLabel = document.getElementById("uploadProgressLabel");
const processingPanel = document.getElementById("processingPanel");
const stepList = document.getElementById("stepList");
const overallProgressFill = document.getElementById("overallProgressFill");
const overallProgressLabel = document.getElementById("overallProgressLabel");
const resultPanel = document.getElementById("resultPanel");
const resultVideo = document.getElementById("resultVideo");
const resultTime = document.getElementById("resultTime");
const resultSize = document.getElementById("resultSize");
const download720Btn = document.getElementById("download720Btn");
const download1080Btn = document.getElementById("download1080Btn");
const errorAlert = document.getElementById("errorAlert");
const errorMessage = document.getElementById("errorMessage");

// ---------------------------------------------------------------------------
// Step list rendering
// ---------------------------------------------------------------------------

/** Build the initial (all-pending) pipeline step list DOM once. */
function renderStepList() {
  stepList.innerHTML = "";
  PIPELINE_STEPS.forEach((step) => {
    const row = document.createElement("div");
    row.className = "step-row";
    row.dataset.key = step.key;
    row.innerHTML = `<span class="step-dot"></span><span>${step.label}</span>`;
    stepList.appendChild(row);
  });
}

/** Mark steps up to and including currentKey as done/active based on order. */
function updateStepList(currentKey) {
  const currentIndex = PIPELINE_STEPS.findIndex((s) => s.key === currentKey);
  document.querySelectorAll(".step-row").forEach((row, index) => {
    row.classList.remove("active", "done");
    if (currentKey === "completed" || index < currentIndex) {
      row.classList.add("done");
    } else if (index === currentIndex) {
      row.classList.add("active");
    }
  });
}

// ---------------------------------------------------------------------------
// Drag & drop / file selection
// ---------------------------------------------------------------------------

function handleFileSelection(file) {
  if (!file) return;
  const validExtensions = [".mp4", ".mov", ".avi"];
  const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!validExtensions.includes(ext)) {
    showError("Unsupported file type. Please choose an MP4, MOV or AVI video.");
    return;
  }

  selectedFile = file;
  hideError();

  const objectUrl = URL.createObjectURL(file);
  originalVideo.src = objectUrl;
  originalPreview.classList.remove("hidden");
  optionsPanel.classList.remove("hidden");
  startButton.disabled = false;

  document.getElementById("selectedFileName").textContent = file.name;
  document.getElementById("selectedFileSize").textContent = formatBytes(file.size);
}

dropzone.addEventListener("click", () => fileInput.click());

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("drag-active");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("drag-active");
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("drag-active");
  const file = event.dataTransfer.files[0];
  handleFileSelection(file);
});

fileInput.addEventListener("change", (event) => {
  handleFileSelection(event.target.files[0]);
});

musicInput.addEventListener("change", (event) => {
  selectedMusicFile = event.target.files[0] || null;
  musicFileName.textContent = selectedMusicFile ? selectedMusicFile.name : "No file selected";
});

// ---------------------------------------------------------------------------
// Upload + processing kickoff
// ---------------------------------------------------------------------------

startButton.addEventListener("click", () => {
  if (!selectedFile) return;
  hideError();
  startButton.disabled = true;

  const formData = new FormData();
  formData.append("file", selectedFile);
  formData.append("target_aspect", document.getElementById("aspectSelect").value);
  formData.append("add_subtitles", document.getElementById("subtitlesToggle").checked);
  formData.append("music_volume", document.getElementById("musicVolume").value);
  if (selectedMusicFile) {
    formData.append("background_music", selectedMusicFile);
  }

  uploadProgressWrap.classList.remove("hidden");

  const xhr = new XMLHttpRequest();
  xhr.open("POST", `${API_BASE}/api/upload`);

  xhr.upload.addEventListener("progress", (event) => {
    if (!event.lengthComputable) return;
    const percent = Math.round((event.loaded / event.total) * 100);
    uploadProgressFill.style.width = `${percent}%`;
    uploadProgressLabel.textContent = `Uploading… ${percent}%`;
  });

  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      const response = JSON.parse(xhr.responseText);
      uploadProgressLabel.textContent = "Upload complete. AI processing started.";
      beginProcessingView(response.job_id);
    } else {
      const detail = safeParseError(xhr.responseText);
      showError(detail);
      startButton.disabled = false;
    }
  };

  xhr.onerror = () => {
    showError("Network error while uploading. Please check your connection and try again.");
    startButton.disabled = false;
  };

  xhr.send(formData);
});

function safeParseError(responseText) {
  try {
    const parsed = JSON.parse(responseText);
    return parsed.detail || "Something went wrong while uploading.";
  } catch (e) {
    return "Something went wrong while uploading.";
  }
}

// ---------------------------------------------------------------------------
// Processing view + status polling
// ---------------------------------------------------------------------------

function beginProcessingView(jobId) {
  renderStepList();
  processingPanel.classList.remove("hidden");
  processingPanel.classList.add("fade-in");
  optionsPanel.classList.add("hidden");

  pollTimer = setInterval(() => pollStatus(jobId), 1000);
  pollStatus(jobId); // fire immediately instead of waiting a full second
}

async function pollStatus(jobId) {
  try {
    const res = await fetch(`${API_BASE}/api/status/${jobId}`);
    if (!res.ok) throw new Error("Status request failed");
    const data = await res.json();

    overallProgressFill.style.width = `${data.progress}%`;
    overallProgressLabel.textContent = `${data.progress}%`;
    updateStepList(data.current_step);

    if (data.status === "completed") {
      clearInterval(pollTimer);
      showResult(jobId, data);
    } else if (data.status === "failed") {
      clearInterval(pollTimer);
      showError(data.error_message || "Processing failed unexpectedly.");
      processingPanel.classList.add("hidden");
    }
  } catch (err) {
    // Transient network hiccups shouldn't kill the whole poll loop;
    // the next interval tick will simply try again.
    console.warn("Status poll failed, retrying next tick:", err);
  }
}

// ---------------------------------------------------------------------------
// Result / download
// ---------------------------------------------------------------------------

function showResult(jobId, statusData) {
  processingPanel.classList.add("hidden");
  resultPanel.classList.remove("hidden");
  resultPanel.classList.add("fade-in");

  resultVideo.src = `${API_BASE}/api/preview/${jobId}?resolution=720p`;
  resultTime.textContent = formatDuration(statusData.processing_time_seconds);
  resultSize.textContent = formatBytes(statusData.output_size_bytes);

  download720Btn.href = `${API_BASE}/api/download/${jobId}?resolution=720p`;
  download1080Btn.href = `${API_BASE}/api/download/${jobId}?resolution=1080p`;
}

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

function showError(message) {
  errorMessage.textContent = message;
  errorAlert.classList.remove("hidden");
}

function hideError() {
  errorAlert.classList.add("hidden");
}
