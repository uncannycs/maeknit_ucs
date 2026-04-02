"use client"

/** @odoo-module **/

import { registry } from "@web/core/registry"
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl"
import { standardFieldProps } from "@web/views/fields/standard_field_props"
import { useService } from "@web/core/utils/hooks"

export class ExcalidrawWidget extends Component {
  static template = "maeknit_excalidraw.ExcalidrawWidget"
  static props = {
    ...standardFieldProps,
  }

  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.busService = useService("bus_service")
    this.canvasRef = useRef("canvasRef")
    this.recordId = this.props.record?.resId
    this.excalidrawAPI = null
    this.commentsController = null

    this.state = useState({
      isLoading: true,
      excalidrawData: null,
      isSaving: false,
      isFullscreen: false,
      commentMode: false,
    })

    // Option A: guard against initial-render onChange calls marking the field dirty
    this._excalidrawInitialized = false
    // Real-time collaboration: prevent re-save loop when applying a remote update
    this._applyingRemoteUpdate = false
    // Bus subscription handles
    this._busChannel = null
    this._busHandler = null

    const rawValue = this.props.record?.data?.[this.props.name]
    if (rawValue) {
      try {
        let parsed = typeof rawValue === "string" ? JSON.parse(rawValue) : rawValue
        // Handle double-encoded JSON (fields.Text storing a JSON string)
        if (typeof parsed === "string") parsed = JSON.parse(parsed)
        this.state.excalidrawData = {
          elements: Array.isArray(parsed.elements) ? parsed.elements : [],
          files: parsed.files || {},
          fileIds: parsed.fileIds || {}, // Keep track of attachment IDs
        }
        console.log("Loaded initial data for record:", this.recordId, this.state.excalidrawData)
      } catch (e) {
        console.error("Error parsing Excalidraw data:", e)
        this.state.excalidrawData = { elements: [], files: {}, fileIds: {} }
      }
    } else {
      this.state.excalidrawData = { elements: [], files: {}, fileIds: {} }
    }

    onMounted(() => { this.renderExcalidraw(); document.addEventListener("keydown", this._onKeyDown) })
    onWillUnmount(() => { this.cleanup(); document.removeEventListener("keydown", this._onKeyDown) })

    this.handleExcalidrawChange = this.handleExcalidrawChange.bind(this)
    this.saveData = this.saveData.bind(this)
    this.manualSave = this.manualSave.bind(this)
    this.toggleFullscreen = this.toggleFullscreen.bind(this)
    this.toggleCommentMode = this.toggleCommentMode.bind(this)
    this._onKeyDown = (e) => { if (e.key === "Escape" && this.state.isFullscreen) this.state.isFullscreen = false }
  }

  toggleFullscreen() {
    this.state.isFullscreen = !this.state.isFullscreen
  }

  toggleCommentMode() {
    this.state.commentMode = !this.state.commentMode
    if (this.commentsController) {
      this.commentsController.setCommentMode(this.state.commentMode)
    }
  }

  cleanup() {
    if (this.saveTimeout) {
      clearTimeout(this.saveTimeout)
      // Tab switch or unmount — fire a final save for any unsaved changes
      this._saveOnUnmount()
    }
    if (this.commentsController) {
      this.commentsController.destroy()
      this.commentsController = null
    }
    this._unsubscribeFromBus()
  }

  // fields.Text requires a JSON string; fields.Json accepts a raw object
  _serializeData(data) {
    const fieldType = this.props.record?.fields?.[this.props.name]?.type
    return (fieldType === 'text' || fieldType === 'char') ? JSON.stringify(data) : data
  }

  _saveOnUnmount() {
    if (!this.recordId || !this.props.record?.resModel) return
    // Capture everything now — don't rely on `this.*` after unmount
    const data = this._serializeData(this.state.excalidrawData)
    const resModel = this.props.record.resModel
    const resId = this.recordId
    const fieldName = this.props.name
    const orm = this.orm
    orm.write(resModel, [resId], { [fieldName]: data })
      .catch(e => console.error("ExcalidrawWidget: save on unmount failed:", e))
  }

  // ─── Real-time collaboration ──────────────────────────────────────────────

  _subscribeToBus() {
    if (!this.recordId || !this.props.record?.resModel) return
    this._busChannel = `excalidraw-${this.props.name}-${this.props.record.resModel}-${this.recordId}`
    this._busEventType = `excalidraw_update_${this.props.name}`
    this._busHandler = (payload) => this._onBusMessage(payload)
    this.busService.subscribe(this._busEventType, this._busHandler)
    this.busService.addChannel(this._busChannel)
    console.log("ExcalidrawWidget: subscribed to bus channel", this._busChannel)
  }

  _unsubscribeFromBus() {
    if (this._busChannel) {
      this.busService.deleteChannel(this._busChannel)
      this._busChannel = null
    }
    if (this._busHandler) {
      this.busService.unsubscribe(this._busEventType, this._busHandler)
      this._busHandler = null
      this._busEventType = null
    }
  }

  _onBusMessage(payload) {
    // Filter to this specific record only
    if (payload.resModel !== this.props.record?.resModel || payload.resId !== this.recordId) return
    // Ignore messages we sent ourselves
    const uid = odoo?.session_info?.uid
    if (uid && payload.uid === uid) return
    // Don't overwrite while the user is actively drawing
    if (this.saveTimeout) return

    this._applyRemoteUpdate()
  }

  async _applyRemoteUpdate() {
    try {
      const result = await this.orm.read(
        this.props.record.resModel,
        [this.recordId],
        [this.props.name]
      )
      const rawData = result[0]?.[this.props.name]
      if (!rawData) return

      const parsed = typeof rawData === "string" ? JSON.parse(rawData) : rawData
      const elements = Array.isArray(parsed.elements) ? parsed.elements : []
      const remoteFileIds = parsed.fileIds || {}

      // Fetch any image files not yet cached locally
      const currentFiles = this.state.excalidrawData.files || {}
      const updatedFiles = { ...currentFiles }
      for (const [fileId] of Object.entries(remoteFileIds)) {
        if (updatedFiles[fileId]) continue
        try {
          const model = this.props.record?.resModel || ''
          const res = await fetch(`/maeknit/excalidraw/image/${this.recordId}/${fileId}?model=${encodeURIComponent(model)}`)
          if (!res.ok) continue
          const data = await res.json()
          if (data.dataURL) {
            updatedFiles[fileId] = {
              dataURL: data.dataURL,
              mimeType: data.mimeType || "image/png",
              created: data.created || Date.now(),
            }
          }
        } catch (e) {
          console.error("ExcalidrawWidget: failed to fetch remote image:", fileId, e)
        }
      }

      if (!this.excalidrawAPI) return

      // Set flag so the onChange triggered by updateScene doesn't re-save
      this._applyingRemoteUpdate = true
      this.excalidrawAPI.updateScene({ elements, files: updatedFiles })
      setTimeout(() => { this._applyingRemoteUpdate = false }, 200)

      this.state.excalidrawData = { elements, files: updatedFiles, fileIds: remoteFileIds }
      console.log("ExcalidrawWidget: applied remote update for record", this.recordId)
    } catch (e) {
      console.error("ExcalidrawWidget: failed to apply remote update:", e)
      this._applyingRemoteUpdate = false
    }
  }

  // ─── Image loading ────────────────────────────────────────────────────────

  async fetchImagesFromBackend() {
    const fileIds = this.state.excalidrawData.fileIds || {}
    const files = this.state.excalidrawData.files || {}

    // If files already exist or no fileIds, nothing to fetch
    if (Object.keys(files).length > 0 || Object.keys(fileIds).length === 0) {
      console.log("No images to fetch from backend")
      return
    }

    console.log("Fetching", Object.keys(fileIds).length, "images from backend")

    const fetchedFiles = {}

    for (const [fileId] of Object.entries(fileIds)) {
      try {
        const model = this.props.record?.resModel || ''
        const url = `/maeknit/excalidraw/image/${this.recordId}/${fileId}?model=${encodeURIComponent(model)}`
        console.log("Fetching image:", fileId, "from", url)

        const response = await fetch(url)
        if (!response.ok) {
          console.error("Failed to fetch image:", fileId, response.status)
          continue
        }

        const imageData = await response.json()
        if (imageData.dataURL) {
          fetchedFiles[fileId] = {
            dataURL: imageData.dataURL,
            mimeType: imageData.mimeType || 'image/png',
            created: imageData.created || Date.now(),
          }
          console.log("Successfully fetched image:", fileId)
        }
      } catch (error) {
        console.error("Error fetching image:", fileId, error)
      }
    }

    // Update state with fetched images
    if (Object.keys(fetchedFiles).length > 0) {
      this.state.excalidrawData.files = fetchedFiles
      console.log("Fetched", Object.keys(fetchedFiles).length, "images successfully")
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  async renderExcalidraw() {
    console.log("Starting renderExcalidraw for record:", this.recordId)
    const container = this.canvasRef.el
    if (!container) {
      console.error("Canvas container not found")
      return
    }

    console.log("Container found:", container)
    container.innerHTML = ""

    try {
      // Always fetch fresh data from DB — OWL record cache is stale after orm.write() bypasses it
      if (this.recordId && this.props.record?.resModel) {
        try {
          const result = await this.orm.read(this.props.record.resModel, [this.recordId], [this.props.name])
          const rawValue = result[0]?.[this.props.name]
          if (rawValue) {
            const parsed = typeof rawValue === "string" ? JSON.parse(rawValue) : rawValue
            this.state.excalidrawData = {
              elements: Array.isArray(parsed.elements) ? parsed.elements : [],
              files: parsed.files || {},
              fileIds: parsed.fileIds || {},
            }
          }
        } catch (e) {
          console.error("ExcalidrawWidget: failed to fetch fresh data, using cached:", e)
        }
      }

      // Fetch images from backend if fileIds exist but files is empty
      await this.fetchImagesFromBackend()

      console.log("Loading Excalidraw scripts...")
      await this.loadExcalidrawScripts()

      const React = window.React
      const ReactDOM = window.ReactDOM
      const ExcalidrawLib = window.ExcalidrawLib

      console.log(" Libraries loaded:", {
        React: !!React,
        ReactDOM: !!ReactDOM,
        ExcalidrawLib: !!ExcalidrawLib,
      })

      if (!React || !ReactDOM || !ExcalidrawLib) {
        throw new Error("Required libraries not loaded")
      }

      console.log(" Creating React root...")
      const root = ReactDOM.createRoot(container)
      console.log(" React root created:", root)

      console.log(" Initializing Excalidraw with data:", this.state.excalidrawData)

      const ExcalidrawComponent = React.createElement(ExcalidrawLib.Excalidraw, {
        initialData: {
          elements: this.state.excalidrawData.elements,
          files: this.state.excalidrawData.files,
        },
        onChange: (elements, appState, files) => {
          this.handleExcalidrawChange(elements, appState, files)
        },
        excalidrawAPI: (api) => {
          this.excalidrawAPI = api
          console.log(" Excalidraw API initialized for record:", this.recordId)
          setTimeout(() => {
            if (this.excalidrawAPI && this.state.excalidrawData.elements.length > 0) {
              this.excalidrawAPI.scrollToContent(this.excalidrawAPI.getSceneElements(), {
                fitToViewport: true,
                animate: false,
              })
            }
          }, 100)
        },
        isCollaborating: false,
        frameRendering: {
          enabled: true,
          clip: true,
          name: true,
          outline: true,
        },
      })

      console.log(" Rendering Excalidraw component...")
      root.render(ExcalidrawComponent)
      this.state.isLoading = false

      // Mark ready after the initial mount onChange fires (typically < 50ms).
      // 150ms is enough to skip the spurious mount event without creating a
      // race window where real user interactions (e.g. pasting an image) get
      // dropped before initialization is flagged.
      setTimeout(() => {
        this._excalidrawInitialized = true
      }, 150)

      // Initialize comment overlay once Excalidraw is mounted
      if (window.ExcalidrawComments && this.recordId && this.props.record?.resModel) {
        const outerContainer = container.parentElement
        const sessionInfo = odoo.session_info || {}
        this.commentsController = new window.ExcalidrawComments({
          container: outerContainer,
          resModel: this.props.record.resModel,
          resId: this.recordId,
          fieldName: this.props.name,
          currentUser: {
            uid: sessionInfo.uid,
            name: sessionInfo.name,
            partnerId: sessionInfo.partner_id,
          },
          getExcalidrawAPI: () => this.excalidrawAPI,
          refreshChatter: () => this.props.record.load(),
        })
        this.commentsController.start()
      }

      // Subscribe to real-time bus updates
      this._subscribeToBus()

      console.log(" Excalidraw rendered successfully for record:", this.recordId)
    } catch (error) {
      console.error(" Error loading Excalidraw:", error)
      console.error(" Error stack:", error.stack)
      this.notification.add("Failed to load Excalidraw: " + error.message, {
        type: "danger",
      })
      this.state.isLoading = false
    }
  }

  async loadExcalidrawScripts() {
    // Load Excalidraw CSS first if not loaded
    if (!document.querySelector('link[href*="excalidraw"]')) {
      const link = document.createElement("link")
      link.rel = "stylesheet"
      link.href = "https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/excalidraw.min.css"
      document.head.appendChild(link)
      await new Promise((resolve) => setTimeout(resolve, 100)) // Wait for CSS to load
    }

    // Check if already loaded
    if (window.ExcalidrawLib && window.React && window.ReactDOM) {
      return
    }

    // Load React
    if (!window.React) {
      await this.loadScript("https://unpkg.com/react@18/umd/react.production.min.js")
    }

    // Load ReactDOM
    if (!window.ReactDOM) {
      await this.loadScript("https://unpkg.com/react-dom@18/umd/react-dom.production.min.js")
    }

    // Load Excalidraw
    if (!window.ExcalidrawLib) {
      await this.loadScript("https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/excalidraw.production.min.js")
    }
  }

  loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script")
      script.src = src
      script.onload = resolve
      script.onerror = reject
      document.head.appendChild(script)
    })
  }

  // ─── Change handling & save ───────────────────────────────────────────────

  handleExcalidrawChange(elements, appState, files) {
    // Option A: skip onChange calls that fire during initial Excalidraw mount
    if (!this._excalidrawInitialized) return
    // Skip onChange triggered by a remote update (prevents re-save loop)
    if (this._applyingRemoteUpdate) return

    const data = {
      elements: Array.isArray(elements) ? elements : [],
      files: files || {},
    }

    this.state.excalidrawData = data

    // Keep comment pins in sync with scroll/zoom and element positions
    if (this.commentsController) {
      this.commentsController.updateElements(elements)
      this.commentsController.syncScrollState(appState)
    }

    if (this.saveTimeout) {
      clearTimeout(this.saveTimeout)
    }

    this.saveTimeout = setTimeout(() => {
      this.saveTimeout = null  // clear so bus updates aren't blocked after save fires
      this.saveData()
    }, 500)
  }

  async manualSave() {
    if (!this.recordId) {
      return
    }

    if (this.saveTimeout) {
      clearTimeout(this.saveTimeout)
    }

    this.state.isSaving = true

    try {
      await this.orm.write(this.props.record.resModel, [this.recordId], {
        [this.props.name]: this._serializeData(this.state.excalidrawData),
      })

      this.notification.add("Sketch saved successfully", { type: "success" })
      console.log(" Excalidraw data saved successfully for record:", this.recordId)
    } catch (error) {
      console.error(" Error saving Excalidraw data:", error)
      this.notification.add("Failed to save sketch data", { type: "danger" })
    } finally {
      this.state.isSaving = false
    }
  }

  async saveData() {
    if (!this.recordId) {
      return
    }

    try {
      await this.orm.write(this.props.record.resModel, [this.recordId], {
        [this.props.name]: this._serializeData(this.state.excalidrawData),
      })

      console.log(" Excalidraw data saved successfully for record:", this.recordId)
    } catch (error) {
      console.error(" Error saving Excalidraw data:", error)
    }
  }
}

registry.category("fields").add("excalidraw", {
  component: ExcalidrawWidget,
  supportedTypes: ["json", "text", "char"],
})

export default ExcalidrawWidget
