(() => {
  const classListEl = document.getElementById("classList");
  const addClassBtn = document.getElementById("addClassBtn");
  const startBtn = document.getElementById("startBtn");
  const formError = document.getElementById("formError");
  const imageFolder = document.getElementById("imageFolder");
  const confidence = document.getElementById("confidence");
  const confidenceOut = document.getElementById("confidenceOut");
  const nmsIou = document.getElementById("nmsIou");
  const nmsIouOut = document.getElementById("nmsIouOut");
  const applyNms = document.getElementById("applyNms");
  const progressBlock = document.getElementById("progressBlock");
  const progressFill = document.getElementById("progressFill");
  const progressBar = document.getElementById("progressBar");
  const progressText = document.getElementById("progressText");
  const progressPct = document.getElementById("progressPct");
  const gallery = document.getElementById("gallery");
  const galleryEmpty = document.getElementById("galleryEmpty");
  const stats = document.getElementById("stats");
  const statLabeled = document.getElementById("statLabeled");
  const statUnlabeled = document.getElementById("statUnlabeled");
  const statTotal = document.getElementById("statTotal");
  const reviewBtnTop = document.getElementById("reviewBtnTop");
  const reviewBtnBottom = document.getElementById("reviewBtnBottom");
  const listImages = document.getElementById("listImages");
  const listLabels = document.getElementById("listLabels");
  const listNoLabels = document.getElementById("listNoLabels");
  const countImages = document.getElementById("countImages");
  const countLabels = document.getElementById("countLabels");
  const countNoLabels = document.getElementById("countNoLabels");
  const folderPath = document.getElementById("folderPath");

  let eventSource = null;
  let labeledCount = 0;
  let unlabeledCount = 0;
  let reviewEnabled = false;
  let folderPollTimer = null;

  function syncSlider(input, output) {
    const update = () => {
      output.textContent = Number(input.value).toFixed(2);
    };
    input.addEventListener("input", update);
    update();
  }

  syncSlider(confidence, confidenceOut);
  syncSlider(nmsIou, nmsIouOut);

  function setReviewEnabled(enabled) {
    reviewEnabled = enabled;
    reviewBtnTop.disabled = !enabled;
    reviewBtnBottom.disabled = !enabled;
    const title = enabled
      ? "Open manual review"
      : "Available after labeling completes";
    reviewBtnTop.title = title;
    reviewBtnBottom.title = title;
  }

  function goReview() {
    if (!reviewEnabled) return;
    window.location.href = "/review";
  }

  reviewBtnTop.addEventListener("click", goReview);
  reviewBtnBottom.addEventListener("click", goReview);

  function renderFileList(ul, files) {
    ul.innerHTML = "";
    files.forEach((name) => {
      const li = document.createElement("li");
      li.textContent = name;
      li.title = name;
      ul.appendChild(li);
    });
  }

  async function refreshFolderListing() {
    try {
      const res = await fetch("/api/dataset");
      if (!res.ok) return;
      const data = await res.json();
      if (data.root) {
        folderPath.textContent = data.root;
        folderPath.title = data.root;
      }
      renderFileList(listImages, data.images || []);
      renderFileList(listLabels, data.labels || []);
      renderFileList(listNoLabels, data.images_with_no_labels || []);
      countImages.textContent = String((data.images || []).length);
      countLabels.textContent = String((data.labels || []).length);
      countNoLabels.textContent = String((data.images_with_no_labels || []).length);

      if (data.has_content && !reviewEnabled) {
        // Allow review if a dataset already exists from a prior run
        setReviewEnabled(true);
      }
    } catch (err) {
      console.error(err);
    }
  }

  function startFolderPolling() {
    stopFolderPolling();
    folderPollTimer = setInterval(refreshFolderListing, 1500);
  }

  function stopFolderPolling() {
    if (folderPollTimer) {
      clearInterval(folderPollTimer);
      folderPollTimer = null;
    }
  }

  function addClassRow(name = "", prompt = "") {
    const row = document.createElement("div");
    row.className = "class-row";
    row.innerHTML = `
      <div class="class-id">0</div>
      <div class="class-fields">
        <input type="text" class="class-name" placeholder="Class name (e.g. coke bottle)" value="${escapeAttr(name)}" />
        <input type="text" class="class-prompt" placeholder="Detection prompt (e.g. a coca cola glass bottle)" value="${escapeAttr(prompt)}" />
      </div>
      <button type="button" class="btn-icon remove-class" title="Remove class" aria-label="Remove class">×</button>
    `;
    row.querySelector(".remove-class").addEventListener("click", () => {
      if (classListEl.children.length <= 1) {
        showError("At least one class is required.");
        return;
      }
      row.remove();
      renumberClasses();
      hideError();
    });
    classListEl.appendChild(row);
    renumberClasses();
  }

  function renumberClasses() {
    [...classListEl.querySelectorAll(".class-row")].forEach((row, i) => {
      row.querySelector(".class-id").textContent = String(i);
    });
  }

  function collectClasses() {
    return [...classListEl.querySelectorAll(".class-row")].map((row) => {
      const name = row.querySelector(".class-name").value.trim();
      let prompt = row.querySelector(".class-prompt").value.trim();
      if (!prompt && name) prompt = `a ${name}`;
      return { name, prompt };
    });
  }

  function showError(msg) {
    formError.hidden = false;
    formError.textContent = msg;
  }

  function hideError() {
    formError.hidden = true;
    formError.textContent = "";
  }

  function escapeAttr(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function setProgress(current, total, text) {
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;
    progressBlock.hidden = false;
    progressFill.style.width = `${pct}%`;
    progressBar.setAttribute("aria-valuenow", String(pct));
    progressPct.textContent = `${pct}%`;
    progressText.textContent = text;
  }

  function updateLiveStats() {
    stats.hidden = false;
    statLabeled.textContent = String(labeledCount);
    statUnlabeled.textContent = String(unlabeledCount);
    statTotal.textContent = String(labeledCount + unlabeledCount);
  }

  function addGalleryCard({ filename, status, detections, previewUrl, message }) {
    galleryEmpty.hidden = true;
    const card = document.createElement("article");
    card.className = "gallery-card";

    if (status === "labeled" && previewUrl) {
      card.innerHTML = `
        <img src="${escapeAttr(previewUrl)}?t=${Date.now()}" alt="Preview of ${escapeAttr(filename)}" loading="lazy" />
        <div class="meta">
          <span class="name" title="${escapeAttr(filename)}">${escapeHtml(filename)}</span>
          <span class="badge">${detections} box${detections === 1 ? "" : "es"}</span>
        </div>
      `;
    } else if (status === "no_label") {
      card.innerHTML = `
        <div style="aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;background:#f0ebe3;color:#6b675f;font-size:0.8rem;padding:12px;text-align:center;">
          No detections
        </div>
        <div class="meta">
          <span class="name" title="${escapeAttr(filename)}">${escapeHtml(filename)}</span>
          <span class="badge muted">skipped</span>
        </div>
      `;
    } else {
      card.innerHTML = `
        <div style="aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;background:#fde8e8;color:#b42318;font-size:0.8rem;padding:12px;text-align:center;">
          ${escapeHtml(message || "Error")}
        </div>
        <div class="meta">
          <span class="name" title="${escapeAttr(filename)}">${escapeHtml(filename)}</span>
          <span class="badge error">error</span>
        </div>
      `;
    }

    gallery.prepend(card);
  }

  function resetResults() {
    labeledCount = 0;
    unlabeledCount = 0;
    gallery.innerHTML = "";
    galleryEmpty.hidden = false;
    stats.hidden = true;
    setReviewEnabled(false);
    setProgress(0, 1, "Starting…");
  }

  function closeEventSource() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function handleEvent(event) {
    if (event.type === "start") {
      setProgress(0, event.total || 1, event.total ? `0 / ${event.total}` : "No images found");
      refreshFolderListing();
      return;
    }

    if (event.type === "progress") {
      if (event.status === "labeled") {
        labeledCount += 1;
        addGalleryCard({
          filename: event.filename,
          status: "labeled",
          detections: event.detections,
          previewUrl: event.preview_url,
        });
      } else if (event.status === "no_label") {
        unlabeledCount += 1;
        addGalleryCard({
          filename: event.filename,
          status: "no_label",
        });
      } else if (event.status === "error") {
        addGalleryCard({
          filename: event.filename,
          status: "error",
          message: event.message,
        });
      }
      updateLiveStats();
      setProgress(
        event.current,
        event.total,
        `${event.filename} · ${event.current} / ${event.total}`
      );
      refreshFolderListing();
      return;
    }

    if (event.type === "complete") {
      labeledCount = event.labeled ?? labeledCount;
      unlabeledCount = event.unlabeled ?? unlabeledCount;
      updateLiveStats();
      setProgress(
        event.total,
        event.total || 1,
        `Done — ${event.labeled} labeled, ${event.unlabeled} without labels`
      );
      startBtn.disabled = false;
      setReviewEnabled(true);
      stopFolderPolling();
      refreshFolderListing();
      closeEventSource();
      return;
    }

    if (event.type === "error") {
      showError(event.message || "Labeling failed.");
      setProgress(0, 1, "Failed");
      startBtn.disabled = false;
      stopFolderPolling();
      closeEventSource();
    }
  }

  async function startLabeling() {
    hideError();
    const classes = collectClasses();
    if (!classes.length || classes.some((c) => !c.name)) {
      showError("Each class needs a name.");
      return;
    }

    startBtn.disabled = true;
    resetResults();
    startFolderPolling();

    try {
      closeEventSource();
      eventSource = new EventSource("/api/events");
      eventSource.onmessage = (e) => {
        try {
          handleEvent(JSON.parse(e.data));
        } catch (err) {
          console.error(err);
        }
      };

      const res = await fetch("/api/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_folder: imageFolder.value.trim(),
          classes,
          confidence_threshold: Number(confidence.value),
          nms_iou_threshold: Number(nmsIou.value),
          apply_nms: applyNms.checked,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        showError(data.error || "Could not start labeling.");
        startBtn.disabled = false;
        stopFolderPolling();
        closeEventSource();
        return;
      }
    } catch (err) {
      showError(err.message || "Network error.");
      startBtn.disabled = false;
      stopFolderPolling();
      closeEventSource();
    }
  }

  addClassBtn.addEventListener("click", () => addClassRow());
  startBtn.addEventListener("click", startLabeling);

  addClassRow("coke bottle", "a coca cola glass bottle");
  refreshFolderListing();
})();
