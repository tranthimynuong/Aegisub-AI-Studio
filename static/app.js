// Video Subber Studio - Frontend Logic
let subtitles = [];
let currentVideoPath = "";
let selectedColor = "&H00FFFFFF"; // ASS format
let statusPollInterval = null;

// DOM Elements
const video = document.getElementById("mainVideo");
const videoSelect = document.getElementById("videoSelect");
const btnRefreshVideos = document.getElementById("btnRefreshVideos");
const subOverlay = document.getElementById("subOverlay");
const subOverlayText = document.getElementById("subOverlayText");
const logoBlurBox = document.getElementById("logoBlurBox");
const subListContainer = document.getElementById("subListContainer");
const emptyState = document.getElementById("emptyState");
const subCount = document.getElementById("subCount");
const subSearchInput = document.getElementById("subSearchInput");

// Controls
const btnPlayPause = document.getElementById("btnPlayPause");
const btnBack5 = document.getElementById("btnBack5");
const btnFwd5 = document.getElementById("btnFwd5");
const curTime = document.getElementById("curTime");
const durTime = document.getElementById("durTime");

// Settings
const settingFont = document.getElementById("settingFont");
const settingFontSize = document.getElementById("settingFontSize");
const valFontSize = document.getElementById("valFontSize");
const settingOutline = document.getElementById("settingOutline");
const valOutline = document.getElementById("valOutline");
const settingMarginV = document.getElementById("settingMarginV");
const valMarginV = document.getElementById("valMarginV");
const chkBlurLogo = document.getElementById("chkBlurLogo");
const blurX = document.getElementById("blurX");
const blurY = document.getElementById("blurY");
const blurW = document.getElementById("blurW");
const blurH = document.getElementById("blurH");

// Actions
const btnSaveSubs = document.getElementById("btnSaveSubs");
const btnExportVideo = document.getElementById("btnExportVideo");
const btnAddSub = document.getElementById("btnAddSub");

// Modal
const taskModal = document.getElementById("taskModal");
const modalTitle = document.getElementById("modalTitle");
const modalDesc = document.getElementById("modalDesc");
const modalProgressBar = document.getElementById("modalProgressBar");
const modalActions = document.getElementById("modalActions");
const btnOpenFolder = document.getElementById("btnOpenFolder");
const btnCloseModal = document.getElementById("btnCloseModal");

// Format seconds to mm:ss
function formatTime(sec) {
  if (isNaN(sec)) return "00:00:00";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// 1. Load Video List
async function loadVideos() {
  try {
    const res = await fetch("/api/list_videos");
    const list = await res.json();
    videoSelect.innerHTML = "";

    if (list.length === 0) {
      videoSelect.innerHTML = `<option value="">Không tìm thấy video nào trong D:\\Downloads</option>`;
      return;
    }

    list.forEach(item => {
      const opt = document.createElement("option");
      opt.value = item.path;
      opt.textContent = `${item.filename} (${item.size_mb} MB)`;
      videoSelect.appendChild(opt);
    });

    // Auto-select first video
    selectVideo(list[0].path);
  } catch (err) {
    console.error("Error loading videos:", err);
  }
}

// 2. Select and Load Video
async function selectVideo(path) {
  if (!path) return;
  currentVideoPath = path;
  videoSelect.value = path;
  video.src = `/api/video?path=${encodeURIComponent(path)}`;
  video.load();
  loadSubtitlesForVideo(path);
}

// 3. Load Subtitles
async function loadSubtitlesForVideo(videoPath) {
  try {
    const res = await fetch(`/api/load_subs?video_path=${encodeURIComponent(videoPath)}`);
    const data = await res.json();

    if (data.found && data.subs && data.subs.length > 0) {
      subtitles = data.subs;
      renderSubList(subtitles);
    } else {
      subtitles = [];
      renderSubList([]);
    }
  } catch (err) {
    console.error("Error loading subtitles:", err);
  }
}

// 4. Render Subtitle Rows
function renderSubList(subsToRender) {
  subListContainer.innerHTML = "";
  subCount.textContent = `${subsToRender.length} câu thoại`;

  if (subsToRender.length === 0) {
    subListContainer.appendChild(emptyState);
    emptyState.style.display = "flex";
    return;
  }

  emptyState.style.display = "none";

  subsToRender.forEach((sub, idx) => {
    const row = document.createElement("div");
    row.className = "sub-row";
    row.id = `sub-row-${sub.id}`;

    row.innerHTML = `
      <div class="sub-row-meta">
        <span class="sub-index">#${sub.id}</span>
        <span class="sub-time">${sub.start_fmt || formatTime(sub.start)} ➔ ${sub.end_fmt || formatTime(sub.end)}</span>
        <div class="sub-row-actions">
          <button class="sub-act-btn btn-play-sub" title="Xem đoạn này">▶️</button>
          <button class="sub-act-btn btn-del-sub" title="Xóa câu">🗑️</button>
        </div>
      </div>
      <textarea class="sub-text-input" rows="2">${sub.text}</textarea>
    `;

    // Seek on play click
    row.querySelector(".btn-play-sub").addEventListener("click", () => {
      video.currentTime = sub.start;
      video.play();
    });

    // Delete sub
    row.querySelector(".btn-del-sub").addEventListener("click", () => {
      subtitles = subtitles.filter(s => s.id !== sub.id);
      renderSubList(subtitles);
    });

    // Update text live
    const textarea = row.querySelector(".sub-text-input");
    textarea.addEventListener("input", (e) => {
      sub.text = e.target.value;
      updateActiveSubOverlay();
    });

    subListContainer.appendChild(row);
  });
}

// 5. Video Playback & Subtitle Sync
video.addEventListener("timeupdate", () => {
  curTime.textContent = formatTime(video.currentTime);
  updateActiveSubOverlay();
});

video.addEventListener("loadedmetadata", () => {
  durTime.textContent = formatTime(video.duration);
});

function updateActiveSubOverlay() {
  const now = video.currentTime;
  const activeSub = subtitles.find(s => now >= s.start && now <= s.end);

  if (activeSub && activeSub.text.trim()) {
    subOverlayText.textContent = activeSub.text;
    subOverlay.style.opacity = "1";

    // Highlight row in list
    document.querySelectorAll(".sub-row.active").forEach(r => r.classList.remove("active"));
    const activeRow = document.getElementById(`sub-row-${activeSub.id}`);
    if (activeRow) {
      activeRow.classList.add("active");
    }
  } else {
    subOverlay.style.opacity = "0";
    document.querySelectorAll(".sub-row.active").forEach(r => r.classList.remove("active"));
  }
}

// Controls
btnPlayPause.addEventListener("click", () => {
  if (video.paused) {
    video.play();
    btnPlayPause.textContent = "⏸";
  } else {
    video.pause();
    btnPlayPause.textContent = "▶";
  }
});

video.addEventListener("play", () => btnPlayPause.textContent = "⏸");
video.addEventListener("pause", () => btnPlayPause.textContent = "▶");

btnBack5.addEventListener("click", () => video.currentTime = Math.max(0, video.currentTime - 5));
btnFwd5.addEventListener("click", () => video.currentTime = Math.min(video.duration, video.currentTime + 5));

// Playback Speed
document.querySelectorAll(".speed-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".speed-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    video.playbackRate = parseFloat(btn.dataset.speed);
  });
});

// 6. Live Settings & Styles Update
function updateLiveStyles() {
  const font = settingFont.value;
  const size = settingFontSize.value;
  const outline = settingOutline.value;
  const marginV = settingMarginV.value;

  valFontSize.textContent = size;
  valOutline.textContent = outline;
  valMarginV.textContent = marginV;

  // Update live preview overlay
  subOverlay.style.bottom = `${marginV}px`;
  subOverlayText.style.fontFamily = font;
  subOverlayText.style.fontSize = `${size * 0.7}px`; // scaled for preview
  
  // Text color
  const colorMap = {
    "&H00FFFFFF": "#ffffff",
    "&H0000E6FF": "#FFE600",
    "&H0000FFFF": "#00FFFF"
  };
  subOverlayText.style.color = colorMap[selectedColor] || "#ffffff";

  // Text shadow (outline)
  subOverlayText.style.textShadow = `
    -${outline}px -${outline}px 0 #000,  
     ${outline}px -${outline}px 0 #000,
    -${outline}px  ${outline}px 0 #000,
     ${outline}px  ${outline}px 0 #000,
     0px 4px 10px rgba(0,0,0,0.9)
  `;

  // Logo blur box preview
  if (chkBlurLogo.checked) {
    logoBlurBox.style.display = "flex";
    logoBlurBox.style.left = `${blurX.value}px`;
    logoBlurBox.style.top = `${blurY.value}px`;
    logoBlurBox.style.width = `${blurW.value}px`;
    logoBlurBox.style.height = `${blurH.value}px`;
  } else {
    logoBlurBox.style.display = "none";
  }
}

// Listen to setting changes
[settingFont, settingFontSize, settingOutline, settingMarginV, chkBlurLogo, blurX, blurY, blurW, blurH].forEach(el => {
  el.addEventListener("input", updateLiveStyles);
});

// Color preset chips
document.querySelectorAll(".color-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".color-chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    selectedColor = chip.dataset.color;
    updateLiveStyles();
  });
});

// Tab navigation
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(tc => tc.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

// Search filter
subSearchInput.addEventListener("input", (e) => {
  const query = e.target.value.toLowerCase();
  const filtered = subtitles.filter(s => s.text.toLowerCase().includes(query));
  renderSubList(filtered);
});

// Add new sub row
btnAddSub.addEventListener("click", () => {
  const newId = subtitles.length > 0 ? Math.max(...subtitles.map(s => s.id)) + 1 : 1;
  const ct = video.currentTime;
  subtitles.push({
    id: newId,
    start: ct,
    end: ct + 2.5,
    start_fmt: formatTime(ct),
    end_fmt: formatTime(ct + 2.5),
    text: "Câu thoại mới"
  });
  subtitles.sort((a, b) => a.start - b.start);
  renderSubList(subtitles);
});

// 7. Save Subtitles
btnSaveSubs.addEventListener("click", async () => {
  if (!currentVideoPath) return alert("Vui lòng chọn video trước!");
  
  btnSaveSubs.textContent = "⏳ Đang lưu...";
  try {
    const res = await fetch("/api/save_subs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_path: currentVideoPath,
        subs: subtitles,
        font_name: settingFont.value,
        font_size: parseInt(settingFontSize.value),
        margin_v: parseInt(settingMarginV.value),
        primary_color: selectedColor,
        outline_width: parseFloat(settingOutline.value)
      })
    });
    const result = await res.json();
    if (result.success) {
      btnSaveSubs.textContent = "✅ Đã lưu!";
      setTimeout(() => btnSaveSubs.textContent = "💾 Lưu Phụ Đề", 2000);
    }
  } catch (err) {
    alert("Lỗi khi lưu phụ đề: " + err);
    btnSaveSubs.textContent = "💾 Lưu Phụ Đề";
  }
});

// 8. Export Video
btnExportVideo.addEventListener("click", async () => {
  if (!currentVideoPath) return alert("Vui lòng chọn video trước!");

  // Save first
  await btnSaveSubs.click();

  // Show modal
  taskModal.classList.add("active");
  modalTitle.textContent = "Đang tổng hợp & xuất video...";
  modalDesc.textContent = "FFmpeg đang xử lý làm mờ logo và in cứng phụ đề chất lượng cao.";
  modalProgressBar.style.width = "25%";
  modalActions.style.display = "none";

  try {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_path: currentVideoPath,
        blur_logo: chkBlurLogo.checked,
        blur_x: parseInt(blurX.value),
        blur_y: parseInt(blurY.value),
        blur_w: parseInt(blurW.value),
        blur_h: parseInt(blurH.value)
      })
    });
    const data = await res.json();
    if (data.success) {
      startStatusPolling();
    } else {
      alert(data.error);
      taskModal.classList.remove("active");
    }
  } catch (err) {
    alert("Lỗi khởi tạo xuất video: " + err);
    taskModal.classList.remove("active");
  }
});

function startStatusPolling() {
  if (statusPollInterval) clearInterval(statusPollInterval);

  statusPollInterval = setInterval(async () => {
    try {
      const res = await fetch("/api/status");
      const status = await res.json();

      if (status.status === "processing") {
        modalProgressBar.style.width = `${status.progress}%`;
        modalDesc.textContent = status.step;
      } else if (status.status === "done") {
        clearInterval(statusPollInterval);
        modalProgressBar.style.width = "100%";
        modalTitle.textContent = "🎉 Xuất video hoàn tất 100%!";
        modalDesc.textContent = `Video của bạn đã sẵn sàng tại: ${status.result_file}`;
        modalActions.style.display = "flex";

        btnOpenFolder.onclick = () => {
          fetch("/api/open_folder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: status.result_file })
          });
        };
      } else if (status.status === "error") {
        clearInterval(statusPollInterval);
        modalTitle.textContent = "❌ Có lỗi xảy ra!";
        modalDesc.textContent = status.error_message || "Lỗi không xác định";
        modalActions.style.display = "flex";
      }
    } catch (err) {
      console.error("Polling error:", err);
    }
  }, 1500);
}

btnCloseModal.addEventListener("click", () => {
  taskModal.classList.remove("active");
  if (statusPollInterval) clearInterval(statusPollInterval);
});

// Events
videoSelect.addEventListener("change", (e) => selectVideo(e.target.value));
btnRefreshVideos.addEventListener("click", loadVideos);

// Init
window.addEventListener("DOMContentLoaded", () => {
  loadVideos();
  updateLiveStyles();
});
