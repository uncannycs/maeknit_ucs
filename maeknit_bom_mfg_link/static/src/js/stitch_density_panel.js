/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class StitchDensityPanelWidget extends Component {
    static template = "maeknit_bom_mfg_link.StitchDensityPanel";
    static props = {
        ...standardFieldProps,
        mode: { type: String, optional: true }, // "swatch" (default) or "toile"
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            records: [],
            isLoading: false,
            // Library search
            showLibrary: false,
            librarySearch: "",
            libraryResults: [],
            libraryLoading: false,
            // Inline stitch density viewer
            selectedMoId: null,
            calibData: null,
            calibLoading: false,
            // Lightbox
            lightboxImages: [],  // [{src, label}]
            lightboxIndex: 0,
            lightboxZoom: 1,
            lightboxPanX: 0,
            lightboxPanY: 0,
            lightboxDragging: false,
            // Swatch picker (for Generate Toile)
            showSwatchPicker: false,
            swatchPickerOptions: [],
        });

        this._searchTimeout = null;
        this._lbDrag = null;

        this._onKeyDown = (ev) => {
            if (!this.state.lightboxImages.length) return;
            if (ev.key === "Escape")     this.closeLightbox();
            if (ev.key === "ArrowRight") this.lightboxNext();
            if (ev.key === "ArrowLeft")  this.lightboxPrev();
            if (ev.key === "+" || ev.key === "=") this.lightboxZoomIn();
            if (ev.key === "-")          this.lightboxZoomOut();
            if (ev.key === "0")          this.lightboxResetZoom();
        };
        this._onWheel = (ev) => {
            if (!this.state.lightboxImages.length) return;
            ev.preventDefault();
            const delta = ev.deltaY < 0 ? 0.2 : -0.2;
            const next = Math.max(0.25, Math.min(5, +(this.state.lightboxZoom + delta).toFixed(2)));
            this.state.lightboxZoom = next;
            if (next <= 1) { this.state.lightboxPanX = 0; this.state.lightboxPanY = 0; }
        };
        this._onMouseMove = (ev) => {
            if (!this._lbDrag) return;
            this.state.lightboxPanX = this._lbDrag.startPanX + (ev.clientX - this._lbDrag.startX);
            this.state.lightboxPanY = this._lbDrag.startPanY + (ev.clientY - this._lbDrag.startY);
        };
        this._onMouseUp = () => {
            if (this._lbDrag) { this._lbDrag = null; this.state.lightboxDragging = false; }
        };

        onWillStart(() => this.loadRecords());
        onMounted(() => {
            document.addEventListener("keydown", this._onKeyDown);
            document.addEventListener("wheel", this._onWheel, { passive: false });
            document.addEventListener("mousemove", this._onMouseMove);
            document.addEventListener("mouseup", this._onMouseUp);
        });
        onWillUnmount(() => {
            document.removeEventListener("keydown", this._onKeyDown);
            document.removeEventListener("wheel", this._onWheel);
            document.removeEventListener("mousemove", this._onMouseMove);
            document.removeEventListener("mouseup", this._onMouseUp);
        });
    }

    get isToile() {
        return this.props.mode === "toile";
    }

    get parentMoId() {
        return this.props.record.resId;
    }

    get partnerId() {
        return this.props.record.data.partner_id?.[0] || null;
    }

    // ── Record loading ──────────────────────────────────────────────────────

    async loadRecords() {
        this.state.isLoading = true;
        const moId = this.parentMoId;
        if (!moId) {
            this.state.records = [];
            this.state.isLoading = false;
            return;
        }

        let domain, fields;
        if (this.isToile) {
            domain = [["dev_mo_id", "=", moId]];
            fields = ["name", "product_id", "toile_swatch_mo_id", "state"];
        } else {
            domain = [
                ["parent_garment_mo_id", "=", moId],
                ["product_id.product_tmpl_id.product_category", "=", "swatch"],
            ];
            fields = ["name", "product_id", "yarn_variant", "colorway_id", "state"];
        }

        try {
            const records = await this.orm.searchRead("mrp.production", domain, fields, {
                order: "name asc",
            });
            this.state.records = records;
            // Auto-select first record
            if (records.length > 0 && !this.state.selectedMoId) {
                await this.selectMo(records[0].id);
            } else if (records.length === 0) {
                this.state.selectedMoId = null;
                this.state.calibData = null;
            }
        } catch {
            this.state.records = [];
        }
        this.state.isLoading = false;
    }

    // ── Stitch density viewer ───────────────────────────────────────────────

    async selectMo(moId) {
        if (this.state.selectedMoId === moId) return;
        this.state.selectedMoId = moId;
        this.state.calibData = null;
        this.state.calibLoading = true;
        try {
            const data = await this.orm.call(
                "mrp.production",
                "get_calibration_data_for_swatch",
                [moId]
            );
            this.state.calibData = typeof data === "string" ? JSON.parse(data) : (data || null);
        } catch {
            this.state.calibData = null;
        }
        this.state.calibLoading = false;
    }

    fmtNum(val) {
        const n = parseFloat(val);
        return isNaN(n) ? "—" : n.toFixed(2);
    }

    // ── Lightbox ─────────────────────────────────────────────────────────────

    get lightboxCurrent() {
        return this.state.lightboxImages[this.state.lightboxIndex] || null;
    }

    openLightbox(src, label) {
        const cd = this.state.calibData || {};
        const all = [
            cd.widthImage   ? { src: cd.widthImage,   label: "Width (Body)"   } : null,
            cd.widthImage2  ? { src: cd.widthImage2,  label: "Width (Cuff)"   } : null,
            cd.heightImage  ? { src: cd.heightImage,  label: "Height (Body)"  } : null,
            cd.heightImage2 ? { src: cd.heightImage2, label: "Height (Cuff)"  } : null,
        ].filter(Boolean);
        const idx = all.findIndex((img) => img.src === src);
        this.state.lightboxImages    = all;
        this.state.lightboxIndex     = idx >= 0 ? idx : 0;
        this.state.lightboxZoom      = 1;
        this.state.lightboxPanX      = 0;
        this.state.lightboxPanY      = 0;
        this.state.lightboxDragging  = false;
    }

    closeLightbox() {
        this._lbDrag = null;
        this.state.lightboxImages    = [];
        this.state.lightboxIndex     = 0;
        this.state.lightboxZoom      = 1;
        this.state.lightboxPanX      = 0;
        this.state.lightboxPanY      = 0;
        this.state.lightboxDragging  = false;
    }

    lightboxNext() {
        const len = this.state.lightboxImages.length;
        if (!len) return;
        this.state.lightboxIndex = (this.state.lightboxIndex + 1) % len;
        this.state.lightboxZoom  = 1;
        this.state.lightboxPanX  = 0;
        this.state.lightboxPanY  = 0;
    }

    lightboxPrev() {
        const len = this.state.lightboxImages.length;
        if (!len) return;
        this.state.lightboxIndex = (this.state.lightboxIndex - 1 + len) % len;
        this.state.lightboxZoom  = 1;
        this.state.lightboxPanX  = 0;
        this.state.lightboxPanY  = 0;
    }

    lightboxZoomIn() {
        this.state.lightboxZoom = Math.min(5, +(this.state.lightboxZoom + 0.25).toFixed(2));
    }

    lightboxZoomOut() {
        const next = Math.max(0.25, +(this.state.lightboxZoom - 0.25).toFixed(2));
        this.state.lightboxZoom = next;
        if (next <= 1) { this.state.lightboxPanX = 0; this.state.lightboxPanY = 0; }
    }

    lightboxResetZoom() {
        this.state.lightboxZoom = 1;
        this.state.lightboxPanX = 0;
        this.state.lightboxPanY = 0;
    }

    onLightboxMouseDown(ev) {
        if (this.state.lightboxZoom <= 1 || ev.button !== 0) return;
        ev.preventDefault();
        this._lbDrag = {
            startX: ev.clientX, startY: ev.clientY,
            startPanX: this.state.lightboxPanX,
            startPanY: this.state.lightboxPanY,
        };
        this.state.lightboxDragging = true;
    }

    lightboxDownload() {
        const img = this.lightboxCurrent;
        if (!img) return;
        const a = document.createElement("a");
        a.href = img.src;
        a.download = img.label.replace(/\s+/g, "_") + ".png";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    // ── Swatch picker (for Generate Toile) ──────────────────────────────────

    async generateToile() {
        const moId = this.parentMoId;
        if (!moId) {
            this.notification.add("Please save the MO first.", { type: "warning" });
            return;
        }
        try {
            const swatches = await this.orm.searchRead(
                "mrp.production",
                [
                    ["parent_garment_mo_id", "=", moId],
                    ["product_id.product_tmpl_id.product_category", "=", "swatch"],
                ],
                ["id", "name", "product_id", "colorway_id", "yarn_variant", "state"],
                { order: "name asc" }
            );
            if (swatches.length > 1) {
                this.state.swatchPickerOptions = swatches;
                this.state.showSwatchPicker = true;
                return;
            }
            await this._doGenerateToile(swatches.length === 1 ? swatches[0].id : null);
        } catch (e) {
            this.notification.add(e.data?.message || e.message || "Failed to generate toile.", {
                type: "danger",
            });
        }
    }

    async selectSwatchForToile(swatchId) {
        this.state.showSwatchPicker = false;
        this.state.swatchPickerOptions = [];
        await this._doGenerateToile(swatchId);
    }

    cancelSwatchPicker() {
        this.state.showSwatchPicker = false;
        this.state.swatchPickerOptions = [];
    }

    async _doGenerateToile(swatchId) {
        const moId = this.parentMoId;
        try {
            const result = await this.orm.call(
                "mrp.production",
                "action_generate_toile",
                [[moId]],
                swatchId ? { swatch_mo_id: swatchId } : {}
            );
            if (result?.type === "ir.actions.act_window") {
                await this.action.doAction(result);
            } else {
                await this.loadRecords();
            }
        } catch (e) {
            this.notification.add(e.data?.message || e.message || "Failed to generate toile.", {
                type: "danger",
            });
        }
    }

    get unit() {
        return this.state.calibData?.measurementUnit || "inches";
    }

    // ── Navigation ──────────────────────────────────────────────────────────

    async openMo(ev, moId) {
        ev.stopPropagation();
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "mrp.production",
            res_id: moId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }

    async removeSwatch(ev, moId) {
        ev.stopPropagation();
        try {
            await this.orm.write("mrp.production", [moId], { parent_garment_mo_id: false });
            if (this.state.selectedMoId === moId) {
                this.state.selectedMoId = null;
                this.state.calibData = null;
            }
            await this.loadRecords();
            await this.props.record.load();
        } catch (e) {
            this.notification.add(e.data?.message || e.message || "Failed to unlink.", {
                type: "danger",
            });
        }
    }

    // ── Generate actions ────────────────────────────────────────────────────

    async generateSwatch() {
        const moId = this.parentMoId;
        if (!moId) {
            this.notification.add("Please save the MO first.", { type: "warning" });
            return;
        }
        try {
            const result = await this.orm.call(
                "mrp.production",
                "action_generate_calibration_swatch",
                [[moId]]
            );
            if (result?.type === "ir.actions.act_window") {
                await this.action.doAction(result);
            } else {
                await this.loadRecords();
            }
        } catch (e) {
            this.notification.add(e.data?.message || e.message || "Failed to generate swatch.", {
                type: "danger",
            });
        }
    }

    // ── Library search ──────────────────────────────────────────────────────

    async toggleLibrary() {
        this.state.showLibrary = !this.state.showLibrary;
        if (this.state.showLibrary) {
            await this.searchLibrary("");
        }
    }

    onLibraryInput(ev) {
        const query = ev.target.value;
        this.state.librarySearch = query;
        clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(() => this.searchLibrary(query), 300);
    }

    async searchLibrary(query) {
        this.state.libraryLoading = true;
        try {
            const partnerId = this.partnerId;
            let results = partnerId
                ? await this.orm.call("mrp.production", "get_calibration_swatches_for_client", [
                      partnerId,
                  ])
                : [];
            const linkedIds = new Set(this.state.records.map((r) => r.id));
            const q = query.toLowerCase();
            this.state.libraryResults = results
                .filter((r) => !linkedIds.has(r.id))
                .filter(
                    (r) =>
                        !q ||
                        (r.productName || "").toLowerCase().includes(q) ||
                        (r.moRef || "").toLowerCase().includes(q)
                )
                .slice(0, 12);
        } catch {
            this.state.libraryResults = [];
        }
        this.state.libraryLoading = false;
    }

    async addFromLibrary(moId) {
        try {
            await this.orm.write("mrp.production", [moId], {
                parent_garment_mo_id: this.parentMoId,
            });
            this.state.showLibrary = false;
            this.state.librarySearch = "";
            await this.loadRecords();
            await this.props.record.load();
        } catch (e) {
            this.notification.add(e.data?.message || e.message || "Failed to add swatch.", {
                type: "danger",
            });
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────────────

    stateBadge(state) {
        const map = {
            done: ["bg-success text-white", "Done"],
            to_close: ["bg-success text-white", "To Close"],
            progress: ["bg-warning text-dark", "In Progress"],
            confirmed: ["bg-info text-white", "Confirmed"],
            draft: ["bg-secondary text-white", "Draft"],
            cancel: ["bg-danger text-white", "Cancelled"],
        };
        const [cls, label] = map[state] || ["bg-secondary text-white", state];
        return { cls: `badge rounded-pill ${cls}`, label };
    }
}

registry.category("fields").add("stitch_density_panel", {
    component: StitchDensityPanelWidget,
    supportedTypes: ["one2many"],
    extractProps: ({ attrs }) => ({
        mode: attrs.mode || "swatch",
    }),
});
