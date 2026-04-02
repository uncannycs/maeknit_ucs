/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

/**
 * Image utilities:
 * 1. Direct file-picker upload / replace for render images
 * 2. Delete render images via RPC
 * 3. Lightbox preview with zoom & pan (render images + Whole CAD / Panel CAD)
 */

// =========================================================================
//  HELPERS
// =========================================================================
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

async function reloadParentFormModel(startEl) {
    let el = startEl;
    while (el) {
        if (el.__owl__) {
            const comp = el.__owl__.component;
            if (comp?.model?.root?.load) {
                await comp.model.root.load();
                comp.render(true);
                return true;
            }
        }
        el = el.parentElement;
    }
    return false;
}

function patchCardImage(card, recordId, base64, mimeType) {
    const wrapper = card.querySelector(".o_kanban_image_wrapper");
    if (!wrapper) return;

    const dataUri = `data:${mimeType};base64,${base64}`;

    const existingImg = wrapper.querySelector("img");
    if (existingImg) {
        existingImg.src = dataUri;
        return;
    }

    const placeholder = wrapper.querySelector(".o_kanban_image_placeholder");
    if (placeholder) {
        const imgDiv = document.createElement("div");
        imgDiv.className = "oe_kanban_action o_render_lightbox_trigger";
        imgDiv.dataset.id = recordId;
        imgDiv.title = "Click to preview";

        const img = document.createElement("img");
        img.src = dataUri;
        img.style.maxWidth = "200px";
        img.style.maxHeight = "200px";
        img.style.objectFit = "contain";
        img.className = "o_attachment_image";

        imgDiv.appendChild(img);
        placeholder.replaceWith(imgDiv);
    }

    const btnRow = card.querySelector(".d-flex.gap-1.justify-content-center");
    if (btnRow && !btnRow.querySelector(".o_render_lightbox_trigger")) {
        const previewBtn = document.createElement("a");
        previewBtn.className = "btn btn-sm btn-primary oe_kanban_action o_render_lightbox_trigger";
        previewBtn.dataset.id = recordId;
        previewBtn.innerHTML = '<i class="fa fa-search-plus"></i> Preview';
        btnRow.appendChild(previewBtn);
    }
}

// =========================================================================
//  LIGHTBOX — reusable full-screen preview with zoom, pan, keyboard
// =========================================================================
function openLightbox(imgSrc) {
    let scale = 1;
    let panX = 0;
    let panY = 0;
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let panStartX = 0;
    let panStartY = 0;
    let rafId = 0;
    const MIN_SCALE = 0.25;
    const MAX_SCALE = 5;
    const ZOOM_STEP = 0.25;

    const overlay = document.createElement("div");
    overlay.className = "o_render_lightbox_overlay";

    const closeBtn = document.createElement("button");
    closeBtn.className = "o_render_lightbox_close";
    closeBtn.innerHTML = "&times;";
    closeBtn.title = "Close (Esc)";

    const toolbar = document.createElement("div");
    toolbar.className = "o_render_lightbox_toolbar";

    const zoomOutBtn = document.createElement("button");
    zoomOutBtn.className = "o_render_lightbox_btn";
    zoomOutBtn.innerHTML = '<i class="fa fa-search-minus"></i>';
    zoomOutBtn.title = "Zoom out (-)";

    const zoomLabel = document.createElement("span");
    zoomLabel.className = "o_render_lightbox_zoom_label";
    zoomLabel.textContent = "100%";

    const zoomInBtn = document.createElement("button");
    zoomInBtn.className = "o_render_lightbox_btn";
    zoomInBtn.innerHTML = '<i class="fa fa-search-plus"></i>';
    zoomInBtn.title = "Zoom in (+)";

    const resetBtn = document.createElement("button");
    resetBtn.className = "o_render_lightbox_btn";
    resetBtn.innerHTML = '<i class="fa fa-expand"></i>';
    resetBtn.title = "Reset zoom";

    toolbar.append(zoomOutBtn, zoomLabel, zoomInBtn, resetBtn);

    const img = document.createElement("img");
    img.className = "o_render_lightbox_img";
    img.src = imgSrc;
    img.alt = "Preview";
    img.draggable = false;

    overlay.append(closeBtn, toolbar, img);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => overlay.classList.add("active"));

    function applyTransform() {
        img.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
        zoomLabel.textContent = `${Math.round(scale * 100)}%`;
        img.style.cursor = scale > 1 ? (isDragging ? "grabbing" : "grab") : "default";
    }

    function zoom(delta) {
        scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale + delta));
        if (scale <= 1) { panX = 0; panY = 0; }
        applyTransform();
    }

    function resetZoom() {
        scale = 1; panX = 0; panY = 0;
        applyTransform();
    }

    function close() {
        overlay.classList.remove("active");
        overlay.addEventListener("transitionend", () => overlay.remove(), { once: true });
        document.removeEventListener("keydown", onKey);
        document.removeEventListener("mousemove", onDragMove);
        document.removeEventListener("mouseup", onDragEnd);
        setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 300);
    }

    function onKey(e) {
        if (e.key === "Escape") close();
        else if (e.key === "+" || e.key === "=") zoom(ZOOM_STEP);
        else if (e.key === "-") zoom(-ZOOM_STEP);
        else if (e.key === "0") resetZoom();
    }

    overlay.addEventListener("wheel", (e) => {
        e.preventDefault();
        zoom(e.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP);
    }, { passive: false });

    img.addEventListener("mousedown", (e) => {
        if (scale <= 1) return;
        e.preventDefault();
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        panStartX = panX;
        panStartY = panY;
        img.style.cursor = "grabbing";
        img.style.transition = "none";
    });

    function onDragMove(e) {
        if (!isDragging) return;
        panX = panStartX + (e.clientX - dragStartX);
        panY = panStartY + (e.clientY - dragStartY);
        if (!rafId) {
            rafId = requestAnimationFrame(() => {
                applyTransform();
                rafId = 0;
            });
        }
    }

    function onDragEnd() {
        isDragging = false;
        if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
        img.style.transition = "";
        if (img.parentNode) {
            img.style.cursor = scale > 1 ? "grab" : "default";
        }
    }

    document.addEventListener("mousemove", onDragMove);
    document.addEventListener("mouseup", onDragEnd);

    zoomInBtn.addEventListener("click", (e) => { e.stopPropagation(); zoom(ZOOM_STEP); });
    zoomOutBtn.addEventListener("click", (e) => { e.stopPropagation(); zoom(-ZOOM_STEP); });
    resetBtn.addEventListener("click", (e) => { e.stopPropagation(); resetZoom(); });

    closeBtn.addEventListener("click", close);
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) close();
    });
    document.addEventListener("keydown", onKey);
}

// =========================================================================
//  REPLACE / UPLOAD — click .o_render_upload_trigger → file picker → RPC
// =========================================================================
document.addEventListener("click", (ev) => {
    const trigger = ev.target.closest(".o_render_upload_trigger");
    if (!trigger) return;

    ev.preventDefault();
    ev.stopPropagation();
    ev.stopImmediatePropagation();

    const recordId = trigger.dataset.id;
    if (!recordId) return;

    const card = trigger.closest(".o_kanban_record") || trigger.closest(".card");

    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.style.display = "none";
    document.body.appendChild(input);

    input.addEventListener("change", async () => {
        const file = input.files[0];
        input.remove();
        if (!file) return;

        const base64 = await fileToBase64(file);

        await rpc("/web/dataset/call_kw", {
            model: "render.image.line",
            method: "write",
            args: [[parseInt(recordId)], { image: base64, image_filename: file.name }],
            kwargs: {},
        });

        if (card) {
            const reloaded = await reloadParentFormModel(card);
            if (!reloaded) {
                patchCardImage(card, recordId, base64, file.type);
            }
        }
    });

    input.addEventListener("cancel", () => input.remove());
    input.click();
}, true);

// =========================================================================
//  DELETE — click .o_render_delete_trigger → confirm → RPC unlink
// =========================================================================
document.addEventListener("click", async (ev) => {
    const trigger = ev.target.closest(".o_render_delete_trigger");
    if (!trigger) return;

    ev.preventDefault();
    ev.stopPropagation();
    ev.stopImmediatePropagation();

    const recordId = trigger.dataset.id;
    if (!recordId) return;

    if (!confirm("Delete this render image?")) return;

    const card = trigger.closest(".o_kanban_record") || trigger.closest(".card");

    await rpc("/web/dataset/call_kw", {
        model: "render.image.line",
        method: "unlink",
        args: [[parseInt(recordId)]],
        kwargs: {},
    });

    if (card) {
        const reloaded = await reloadParentFormModel(card);
        if (!reloaded) {
            card.remove();
        }
    }
}, true);

// =========================================================================
//  RENDER IMAGE PREVIEW — click .o_render_lightbox_trigger
// =========================================================================
document.addEventListener("click", (ev) => {
    const trigger = ev.target.closest(".o_render_lightbox_trigger");
    if (!trigger) return;
    if (trigger.classList.contains("o_render_upload_trigger")) return;

    ev.preventDefault();
    ev.stopPropagation();
    ev.stopImmediatePropagation();

    const recordId = trigger.dataset.id;
    if (!recordId) return;

    openLightbox(`/web/image/render.image.line/${recordId}/image`);
}, true);

// =========================================================================
//  REPROGRAM NOTES IMAGES — click any <img> inside the reprogram_notes_html
//  field (Upload Program Files dialog) OR the .o_reprogram_note_viewer
//  container (Latest reprogram note dialog) to open the lightbox.
// =========================================================================
document.addEventListener("click", (ev) => {
    const img = ev.target.closest("img");
    if (!img) return;

    const inNotesField = img.closest('[name="reprogram_notes_html"]');
    const inNoteViewer = img.closest(".o_reprogram_note_viewer");
    if (!inNotesField && !inNoteViewer) return;

    const src = img.src || img.dataset.src;
    if (!src) return;

    ev.preventDefault();
    ev.stopPropagation();

    openLightbox(src);
}, true);

// =========================================================================
//  CAD PREVIEW — click .o_cad_preview_trigger (Whole CAD / Panel CAD)
//  Grabs the image src from the nearest <img> inside the widget.
// =========================================================================
document.addEventListener("click", (ev) => {
    const trigger = ev.target.closest(".o_cad_preview_trigger");
    if (!trigger) return;

    // Find the image src — either from a nested <img> or sibling container
    const container = trigger.closest(".image-display") || trigger.closest(".whole-cad-image-container");
    const imgEl = container?.querySelector("img");
    if (!imgEl || !imgEl.src) return;

    ev.preventDefault();
    ev.stopPropagation();

    openLightbox(imgEl.src);
}, true);
