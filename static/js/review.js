(() => {
  const canvas = document.getElementById("annotCanvas");
  const ctx = canvas.getContext("2d");
  const canvasEmpty = document.getElementById("canvasEmpty");
  const canvasWrap = document.getElementById("canvasWrap");
  const drawClassSelect = document.getElementById("drawClassSelect");
  const deleteBoxBtn = document.getElementById("deleteBoxBtn");
  const classEditor = document.getElementById("classEditor");
  const boxList = document.getElementById("boxList");
  const imageSlider = document.getElementById("imageSlider");
  const imageCounter = document.getElementById("imageCounter");
  const imageName = document.getElementById("imageName");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  const nextUnlabeledBtn = document.getElementById("nextUnlabeledBtn");
  const finishBtn = document.getElementById("finishBtn");
  const overwriteModal = document.getElementById("overwriteModal");
  const downloadModal = document.getElementById("downloadModal");
  const overwriteFileList = document.getElementById("overwriteFileList");
  const alwaysOverwriteEl = document.getElementById("alwaysOverwrite");
  const confirmOverwriteBtn = document.getElementById("confirmOverwriteBtn");
  const downloadBtn = document.getElementById("downloadBtn");
  const downloadError = document.getElementById("downloadError");

  const HANDLE = 8;
  const MIN_BOX = 6;
  const ALWAYS_KEY = "auto_label_always_overwrite";

  let classes = [];
  let images = [];
  let index = 0;
  let imgEl = null;
  let scale = 1;
  let offsetX = 0;
  let offsetY = 0;
  let selectedBox = -1;
  let mode = null; // null | draw | move | resize
  let resizeHandle = null;
  let dragStart = null;
  let draftBox = null;
  let pendingFinishPayload = null;

  alwaysOverwriteEl.checked = localStorage.getItem(ALWAYS_KEY) === "1";

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function currentImage() {
    return images[index] || null;
  }

  function classColor(classId) {
    const c = classes[classId];
    return (c && c.color) || "#e11d48";
  }

  function className(classId) {
    const c = classes[classId];
    return (c && c.name) || `class_${classId}`;
  }

  function openModal(el) {
    el.hidden = false;
  }

  function closeModal(el) {
    el.hidden = true;
  }

  document.querySelectorAll("[data-close]").forEach((node) => {
    node.addEventListener("click", () => {
      const id = node.getAttribute("data-close");
      const modal = document.getElementById(id);
      if (modal) closeModal(modal);
    });
  });

  function renderClassEditor() {
    classEditor.innerHTML = "";
    classes.forEach((cls, i) => {
      const row = document.createElement("div");
      row.className = "class-edit-row";
      row.innerHTML = `
        <span class="class-swatch" style="background:${escapeHtml(cls.color)}"></span>
        <span class="class-id">${i}</span>
        <input type="text" value="${escapeHtml(cls.name)}" data-class-id="${i}" />
      `;
      const input = row.querySelector("input");
      input.addEventListener("change", () => {
        const name = input.value.trim();
        if (!name) {
          input.value = classes[i].name;
          return;
        }
        classes[i].name = name;
        refreshDrawSelect();
        renderBoxList();
        redraw();
      });
      classEditor.appendChild(row);
    });
    refreshDrawSelect();
  }

  function refreshDrawSelect() {
    const prev = drawClassSelect.value;
    drawClassSelect.innerHTML = "";
    classes.forEach((cls, i) => {
      const opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = `${i}: ${cls.name}`;
      drawClassSelect.appendChild(opt);
    });
    if (prev && [...drawClassSelect.options].some((o) => o.value === prev)) {
      drawClassSelect.value = prev;
    }
  }

  function renderBoxList() {
    const img = currentImage();
    boxList.innerHTML = "";
    if (!img) return;
    img.boxes.forEach((box, i) => {
      const li = document.createElement("li");
      if (i === selectedBox) li.classList.add("selected");
      li.innerHTML = `
        <span style="display:flex;align-items:center;gap:8px;">
          <span class="class-swatch" style="width:8px;height:8px;border-radius:2px;background:${classColor(box.class_id)}"></span>
          ${escapeHtml(className(box.class_id))}
        </span>
        <span style="font-family:var(--mono);font-size:0.7rem;color:var(--muted);">#${i + 1}</span>
      `;
      li.addEventListener("click", () => {
        selectedBox = i;
        deleteBoxBtn.disabled = false;
        renderBoxList();
        redraw();
      });
      boxList.appendChild(li);
    });
    deleteBoxBtn.disabled = selectedBox < 0;
  }

  function updateNav() {
    const total = images.length;
    imageSlider.max = String(Math.max(total - 1, 0));
    imageSlider.value = String(index);
    imageCounter.textContent = total ? `${index + 1} / ${total}` : "0 / 0";
    const img = currentImage();
    imageName.textContent = img
      ? `${img.filename}${img.source === "images_with_no_labels" ? " · no labels" : ""}`
      : "—";
    prevBtn.disabled = index <= 0;
    nextBtn.disabled = index >= total - 1;
  }

  function fitCanvas() {
    const img = currentImage();
    if (!img || !imgEl) return;

    const maxW = canvasWrap.clientWidth - 16;
    const maxH = Math.min(window.innerHeight * 0.7, 720);
    const sx = maxW / img.width;
    const sy = maxH / img.height;
    scale = Math.min(sx, sy, 1);
    const dispW = Math.round(img.width * scale);
    const dispH = Math.round(img.height * scale);
    canvas.width = dispW;
    canvas.height = dispH;
    offsetX = 0;
    offsetY = 0;
  }

  function toImageCoords(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const x = (clientX - rect.left) / scale;
    const y = (clientY - rect.top) / scale;
    const img = currentImage();
    return {
      x: Math.max(0, Math.min(img.width, x)),
      y: Math.max(0, Math.min(img.height, y)),
    };
  }

  function normalizeBox(b) {
    return {
      class_id: b.class_id,
      x1: Math.min(b.x1, b.x2),
      y1: Math.min(b.y1, b.y2),
      x2: Math.max(b.x1, b.x2),
      y2: Math.max(b.y1, b.y2),
    };
  }

  function handlesFor(box) {
    const x1 = box.x1 * scale;
    const y1 = box.y1 * scale;
    const x2 = box.x2 * scale;
    const y2 = box.y2 * scale;
    return {
      nw: { x: x1, y: y1 },
      ne: { x: x2, y: y1 },
      sw: { x: x1, y: y2 },
      se: { x: x2, y: y2 },
    };
  }

  function hitHandle(mx, my, box) {
    const hs = handlesFor(box);
    const r = HANDLE + 2;
    for (const [name, p] of Object.entries(hs)) {
      if (Math.abs(mx - p.x) <= r && Math.abs(my - p.y) <= r) return name;
    }
    return null;
  }

  function hitBox(mx, my) {
    const img = currentImage();
    if (!img) return -1;
    const x = mx / scale;
    const y = my / scale;
    for (let i = img.boxes.length - 1; i >= 0; i -= 1) {
      const b = img.boxes[i];
      if (x >= b.x1 && x <= b.x2 && y >= b.y1 && y <= b.y2) return i;
    }
    return -1;
  }

  function redraw() {
    const img = currentImage();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!img || !imgEl) return;

    ctx.drawImage(imgEl, 0, 0, canvas.width, canvas.height);

    const drawOne = (box, selected) => {
      const color = classColor(box.class_id);
      const x = box.x1 * scale;
      const y = box.y1 * scale;
      const w = (box.x2 - box.x1) * scale;
      const h = (box.y2 - box.y1) * scale;
      ctx.strokeStyle = color;
      ctx.lineWidth = selected ? 3 : 2;
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = color + "33";
      ctx.fillRect(x, y, w, h);

      const label = className(box.class_id);
      ctx.font = "12px IBM Plex Sans, sans-serif";
      const tw = ctx.measureText(label).width + 8;
      ctx.fillStyle = color;
      ctx.fillRect(x, Math.max(0, y - 18), tw, 18);
      ctx.fillStyle = "#fff";
      ctx.fillText(label, x + 4, Math.max(12, y - 5));

      if (selected) {
        const hs = handlesFor(box);
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = color;
        Object.values(hs).forEach((p) => {
          ctx.fillRect(p.x - HANDLE / 2, p.y - HANDLE / 2, HANDLE, HANDLE);
          ctx.strokeRect(p.x - HANDLE / 2, p.y - HANDLE / 2, HANDLE, HANDLE);
        });
      }
    };

    img.boxes.forEach((box, i) => drawOne(box, i === selectedBox));
    if (draftBox) drawOne(normalizeBox(draftBox), true);
  }

  async function loadImageAt(i) {
    if (!images.length) {
      canvasEmpty.hidden = false;
      canvasEmpty.textContent = "No images to review.";
      return;
    }
    index = Math.max(0, Math.min(images.length - 1, i));
    selectedBox = -1;
    draftBox = null;
    mode = null;
    const item = currentImage();
    canvasEmpty.hidden = false;
    canvasEmpty.textContent = "Loading…";

    await new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => {
        imgEl = image;
        item.width = image.naturalWidth;
        item.height = image.naturalHeight;
        canvasEmpty.hidden = true;
        fitCanvas();
        updateNav();
        renderBoxList();
        redraw();
        resolve();
      };
      image.onerror = () => {
        canvasEmpty.textContent = `Failed to load ${item.filename}`;
        reject(new Error("load failed"));
      };
      image.src = `${item.image_url}?t=${Date.now()}`;
    }).catch(() => {});
  }

  function deleteSelected() {
    const img = currentImage();
    if (!img || selectedBox < 0) return;
    img.boxes.splice(selectedBox, 1);
    selectedBox = -1;
    renderBoxList();
    redraw();
  }

  deleteBoxBtn.addEventListener("click", deleteSelected);
  window.addEventListener("keydown", (e) => {
    if ((e.key === "Delete" || e.key === "Backspace") && selectedBox >= 0) {
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      e.preventDefault();
      deleteSelected();
    }
  });

  canvas.addEventListener("mousedown", (e) => {
    const img = currentImage();
    if (!img) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const pt = toImageCoords(e.clientX, e.clientY);

    if (selectedBox >= 0) {
      const handle = hitHandle(mx, my, img.boxes[selectedBox]);
      if (handle) {
        mode = "resize";
        resizeHandle = handle;
        dragStart = pt;
        return;
      }
    }

    const hit = hitBox(mx, my);
    if (hit >= 0) {
      selectedBox = hit;
      mode = "move";
      dragStart = pt;
      renderBoxList();
      redraw();
      return;
    }

    // Start drawing
    selectedBox = -1;
    mode = "draw";
    const classId = Number(drawClassSelect.value || 0);
    draftBox = { class_id: classId, x1: pt.x, y1: pt.y, x2: pt.x, y2: pt.y };
    renderBoxList();
    redraw();
  });

  canvas.addEventListener("mousemove", (e) => {
    const img = currentImage();
    if (!img || !mode) return;
    const pt = toImageCoords(e.clientX, e.clientY);

    if (mode === "draw" && draftBox) {
      draftBox.x2 = pt.x;
      draftBox.y2 = pt.y;
      redraw();
      return;
    }

    if (mode === "move" && selectedBox >= 0 && dragStart) {
      const box = img.boxes[selectedBox];
      const dx = pt.x - dragStart.x;
      const dy = pt.y - dragStart.y;
      let x1 = box.x1 + dx;
      let y1 = box.y1 + dy;
      let x2 = box.x2 + dx;
      let y2 = box.y2 + dy;
      const w = x2 - x1;
      const h = y2 - y1;
      if (x1 < 0) {
        x1 = 0;
        x2 = w;
      }
      if (y1 < 0) {
        y1 = 0;
        y2 = h;
      }
      if (x2 > img.width) {
        x2 = img.width;
        x1 = img.width - w;
      }
      if (y2 > img.height) {
        y2 = img.height;
        y1 = img.height - h;
      }
      box.x1 = x1;
      box.y1 = y1;
      box.x2 = x2;
      box.y2 = y2;
      dragStart = pt;
      redraw();
      return;
    }

    if (mode === "resize" && selectedBox >= 0) {
      const box = img.boxes[selectedBox];
      if (resizeHandle.includes("n")) box.y1 = pt.y;
      if (resizeHandle.includes("s")) box.y2 = pt.y;
      if (resizeHandle.includes("w")) box.x1 = pt.x;
      if (resizeHandle.includes("e")) box.x2 = pt.x;
      const n = normalizeBox(box);
      Object.assign(box, n);
      redraw();
    }
  });

  function endDrag() {
    const img = currentImage();
    if (mode === "draw" && draftBox && img) {
      const n = normalizeBox(draftBox);
      if (n.x2 - n.x1 >= MIN_BOX && n.y2 - n.y1 >= MIN_BOX) {
        img.boxes.push(n);
        selectedBox = img.boxes.length - 1;
      }
      draftBox = null;
      renderBoxList();
      redraw();
    }
    mode = null;
    resizeHandle = null;
    dragStart = null;
  }

  canvas.addEventListener("mouseup", endDrag);
  canvas.addEventListener("mouseleave", endDrag);

  prevBtn.addEventListener("click", () => loadImageAt(index - 1));
  nextBtn.addEventListener("click", () => loadImageAt(index + 1));
  imageSlider.addEventListener("input", () => loadImageAt(Number(imageSlider.value)));

  nextUnlabeledBtn.addEventListener("click", () => {
    if (!images.length) return;
    for (let step = 1; step <= images.length; step += 1) {
      const i = (index + step) % images.length;
      if ((images[i].boxes || []).length === 0) {
        loadImageAt(i);
        return;
      }
    }
    alert("No images with zero boxes found.");
  });

  function buildPayload() {
    return {
      classes: classes.map((c) => c.name),
      annotations: images.map((img) => ({
        filename: img.filename,
        source: img.source,
        width: img.width,
        height: img.height,
        boxes: img.boxes.map((b) => ({
          class_id: b.class_id,
          x1: b.x1,
          y1: b.y1,
          x2: b.x2,
          y2: b.y2,
        })),
      })),
      overwrite: false,
      always_overwrite: alwaysOverwriteEl.checked || localStorage.getItem(ALWAYS_KEY) === "1",
    };
  }

  async function submitFinish(payload) {
    finishBtn.disabled = true;
    try {
      const res = await fetch("/api/review/finish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.needs_overwrite_confirm) {
        pendingFinishPayload = payload;
        overwriteFileList.innerHTML = "";
        (data.files || []).forEach((f) => {
          const li = document.createElement("li");
          li.textContent = f;
          overwriteFileList.appendChild(li);
        });
        openModal(overwriteModal);
        finishBtn.disabled = false;
        return;
      }
      if (!res.ok) {
        alert(data.error || "Finalize failed.");
        finishBtn.disabled = false;
        return;
      }
      closeModal(overwriteModal);
      openModal(downloadModal);
    } catch (err) {
      alert(err.message || "Network error");
    } finally {
      finishBtn.disabled = false;
    }
  }

  finishBtn.addEventListener("click", () => {
    const payload = buildPayload();
    if (localStorage.getItem(ALWAYS_KEY) === "1") {
      payload.always_overwrite = true;
      payload.overwrite = true;
    }
    submitFinish(payload);
  });

  confirmOverwriteBtn.addEventListener("click", () => {
    if (alwaysOverwriteEl.checked) {
      localStorage.setItem(ALWAYS_KEY, "1");
    }
    const payload = pendingFinishPayload || buildPayload();
    payload.overwrite = true;
    payload.always_overwrite = alwaysOverwriteEl.checked;
    submitFinish(payload);
  });

  alwaysOverwriteEl.addEventListener("change", () => {
    if (!alwaysOverwriteEl.checked) localStorage.removeItem(ALWAYS_KEY);
  });

  downloadBtn.addEventListener("click", async () => {
    downloadError.hidden = true;
    const selections = {
      images: document.getElementById("dlImages").checked,
      labels: document.getElementById("dlLabels").checked,
      classes_txt: document.getElementById("dlClasses").checked,
      data_yaml: document.getElementById("dlYaml").checked,
      images_with_no_labels: document.getElementById("dlNoLabels").checked,
    };
    if (!Object.values(selections).some(Boolean)) {
      downloadError.hidden = false;
      downloadError.textContent = "Select at least one item.";
      return;
    }
    try {
      const res = await fetch("/api/review/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(selections),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        downloadError.hidden = false;
        downloadError.textContent = data.error || "Download failed.";
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "images_and_labels.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      downloadError.hidden = false;
      downloadError.textContent = err.message || "Download failed.";
    }
  });

  window.addEventListener("resize", () => {
    fitCanvas();
    redraw();
  });

  async function init() {
    try {
      const res = await fetch("/api/review/session");
      const data = await res.json();
      if (!res.ok) {
        canvasEmpty.textContent = data.error || "Could not load review session.";
        return;
      }
      classes = data.classes || [];
      images = (data.images || []).map((img) => ({
        ...img,
        boxes: (img.boxes || []).map((b) => ({
          class_id: b.class_id,
          x1: b.x1,
          y1: b.y1,
          x2: b.x2,
          y2: b.y2,
        })),
      }));
      renderClassEditor();
      if (!images.length) {
        canvasEmpty.textContent = "No images found in the dataset.";
        return;
      }
      await loadImageAt(0);
    } catch (err) {
      canvasEmpty.textContent = err.message || "Failed to load session.";
    }
  }

  init();
})();
