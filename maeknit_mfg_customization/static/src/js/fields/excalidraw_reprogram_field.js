/** @odoo-module **/

/**
 * ExcalidrawReprogramField
 *
 * Custom field widget for the Request New Program wizard.
 * Saves the drawing as JSON (→ sketch_data) AND auto-exports a PNG
 * (→ sketch_preview) so the PNG can be embedded in the chatter note.
 *
 * Registered as widget="excalidraw_reprogram" (does NOT conflict with the
 * existing "excalidraw" key from maeknit_excalidraw).
 */

import { registry } from "@web/core/registry"
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl"
import { standardFieldProps } from "@web/views/fields/standard_field_props"
import { useService } from "@web/core/utils/hooks"

// Name of the companion Binary field that stores the PNG preview.
const PREVIEW_FIELD = "sketch_preview"

export class ExcalidrawReprogramField extends Component {
    static template = "maeknit_mfg_customization.ExcalidrawReprogramField"
    static props = { ...standardFieldProps }

    setup() {
        this.notification = useService("notification")
        this.canvasRef = useRef("canvasRef")
        this.excalidrawAPI = null

        this.state = useState({
            isLoading: true,
            isExporting: false,
        })

        // Parse any previously saved drawing from the JSON field
        const rawValue = this.props.record?.data?.[this.props.name]
        this.initialData = { elements: [], files: {}, appState: { viewBackgroundColor: "#ffffff" } }
        if (rawValue) {
            try {
                const parsed = typeof rawValue === "string" ? JSON.parse(rawValue) : rawValue
                this.initialData.elements = Array.isArray(parsed.elements) ? parsed.elements : []
                this.initialData.files = parsed.files || {}
            } catch (e) {
                console.error("ExcalidrawReprogramField: failed to parse saved data", e)
            }
        }

        this._handleChange = this._handleChange.bind(this)

        onMounted(() => this._renderExcalidraw())
        onWillUnmount(() => {
            if (this._saveTimeout) {
                clearTimeout(this._saveTimeout)
                // Flush pending changes synchronously so they are included in
                // the wizard record save that fires when Confirm is clicked.
                const elements = this._latestElements || []
                const files = this._latestFiles || {}
                if (elements.length || Object.keys(files).length) {
                    const jsonData = JSON.stringify({ elements, files })
                    this.props.record.update({ [this.props.name]: jsonData })
                }
            }
        })
    }

    // ─── Script loading ────────────────────────────────────────────────────────

    _loadScript(src) {
        return new Promise((resolve, reject) => {
            const el = document.createElement("script")
            el.src = src
            el.onload = resolve
            el.onerror = reject
            document.head.appendChild(el)
        })
    }

    async _loadLibraries() {
        // Load Excalidraw CSS once
        if (!document.querySelector('link[href*="excalidraw"]')) {
            const link = document.createElement("link")
            link.rel = "stylesheet"
            link.href = "https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/excalidraw.min.css"
            document.head.appendChild(link)
        }
        // Reuse already-loaded globals (shared with maeknit_excalidraw if loaded)
        if (window.React && window.ReactDOM && window.ExcalidrawLib) return
        if (!window.React)        await this._loadScript("https://unpkg.com/react@18/umd/react.production.min.js")
        if (!window.ReactDOM)    await this._loadScript("https://unpkg.com/react-dom@18/umd/react-dom.production.min.js")
        if (!window.ExcalidrawLib) await this._loadScript("https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/excalidraw.production.min.js")
    }

    // ─── Excalidraw rendering ──────────────────────────────────────────────────

    async _renderExcalidraw() {
        const container = this.canvasRef.el
        if (!container) return
        container.innerHTML = ""

        try {
            await this._loadLibraries()
            const { React, ReactDOM, ExcalidrawLib } = window
            if (!React || !ReactDOM || !ExcalidrawLib) throw new Error("Libraries missing")

            const root = ReactDOM.createRoot(container)
            root.render(
                React.createElement(ExcalidrawLib.Excalidraw, {
                    initialData: this.initialData,
                    onChange: this._handleChange,
                    excalidrawAPI: (api) => {
                        this.excalidrawAPI = api
                        // Fit existing content into view
                        if (this.initialData.elements.length) {
                            setTimeout(() => {
                                api.scrollToContent(api.getSceneElements(), {
                                    fitToViewport: true,
                                    animate: false,
                                })
                            }, 100)
                        }
                    },
                    UIOptions: {
                        canvasActions: {
                            export: false,
                            loadScene: false,
                            saveToActiveFile: false,
                            saveAsImage: false,
                        },
                    },
                    isCollaborating: false,
                })
            )
            this.state.isLoading = false
        } catch (err) {
            console.error("ExcalidrawReprogramField: render error", err)
            this.notification.add("Failed to load sketch tool: " + err.message, { type: "danger" })
            this.state.isLoading = false
        }
    }

    // ─── Change handler (debounced) ────────────────────────────────────────────

    _handleChange(elements, appState, files) {
        this._latestElements = elements
        this._latestAppState = appState
        this._latestFiles = files

        if (this._saveTimeout) clearTimeout(this._saveTimeout)
        this._saveTimeout = setTimeout(() => this._saveAll(), 50)
    }

    async _saveAll() {
        const elements = this._latestElements || []
        const files = this._latestFiles || {}

        // 1. Save JSON drawing state → sketch_data
        const jsonData = JSON.stringify({ elements, files })
        await this.props.record.update({ [this.props.name]: jsonData })

        // 2. Export PNG → sketch_preview (shown in chatter note)
        await this._exportPng(elements, files)
    }

    async _exportPng(elements, files) {
        if (!elements.length) return
        if (!window.ExcalidrawLib?.exportToBlob) return

        this.state.isExporting = true
        try {
            const blob = await window.ExcalidrawLib.exportToBlob({
                elements,
                appState: {
                    ...(this._latestAppState || {}),
                    exportBackground: true,
                },
                files,
                quality: 0.9,
            })
            const base64 = await new Promise((resolve, reject) => {
                const reader = new FileReader()
                reader.onloadend = () => resolve(reader.result.split(",")[1])
                reader.onerror = reject
                reader.readAsDataURL(blob)
            })
            await this.props.record.update({ [PREVIEW_FIELD]: base64 })
        } catch (err) {
            console.error("ExcalidrawReprogramField: PNG export error", err)
        } finally {
            this.state.isExporting = false
        }
    }
}

registry.category("fields").add("excalidraw_reprogram", {
    component: ExcalidrawReprogramField,
    displayName: "Excalidraw Reprogram Sketch",
    supportedTypes: ["text", "json", "char"],
})
