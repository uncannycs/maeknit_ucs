"use client"

/** @odoo-module **/

import { Component, useState } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { registry } from "@web/core/registry"
import { standardFieldProps } from "@web/views/fields/standard_field_props"
import { AddRowsDialog } from "./whole_cad_widget"
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog"

export class MeasurementSheetWidget extends Component {
  static template = "measurement_sheet_widget.MeasurementSheetWidget"
  static props = {
    ...standardFieldProps,
  }

  setup() {
    // All hooks must be called at the top level of the component
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.actionService = useService("action")
    this.dialogService = useService("dialog")

    this.letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    this.state = useState({
      activeTab: "cad_panels",
      activePanel: null,
      customPanels: [],
      isDirty: false,
      hiddenPanels: [], // kept only for backward-compat reading of old saved data
      showAddPanelModal: false,
      newPanelName: "",
      unit: "inches", // "inches" or "cm"
      status: "draft", // "draft" | "ready"
      panels: {},
    })
    this.state.zoomLevel = 1.0
    this.state.zoomLevel2 = 1.0
    this.dragState = {
      isDragging: false,
      startX: 0,
      startY: 0,
      scrollLeft: 0,
      scrollTop: 0,
      container: null,
    }
    this.dragState2 = {
      isDragging: false,
      startX: 0,
      startY: 0,
      scrollLeft: 0,
      scrollTop: 0,
    }

    // ── Points image zoom / pan ────────────────────────────────────────────
    this.adjustZoom = (delta) => {
      const newZoom = Math.min(5, Math.max(0.5, this.state.zoomLevel + delta))
      this.state.zoomLevel = newZoom
      const wrapper = document.querySelector(".image-wrapper")
      if (wrapper) wrapper.style.transform = `scale(${newZoom})`
    }

    this.resetZoom = () => {
      this.state.zoomLevel = 1.0
      const wrapper = document.querySelector(".image-wrapper")
      const container = document.querySelector(".zoom-container")
      if (wrapper) { wrapper.style.transform = "scale(1)"; wrapper.style.left = "0px"; wrapper.style.top = "0px" }
      if (container) { container.scrollTop = 0; container.scrollLeft = 0 }
    }

    this.fitToContainer = () => {
      this.state.zoomLevel = 1.0
      const wrapper = document.querySelector(".image-wrapper")
      const container = document.querySelector(".zoom-container")
      if (wrapper) { wrapper.style.transform = "scale(1)"; wrapper.style.left = "0px"; wrapper.style.top = "0px" }
      if (container) { container.scrollTop = 0; container.scrollLeft = 0 }
    }

    this.handleWheel = (event) => {
      event.preventDefault()
      this.adjustZoom(event.deltaY < 0 ? 0.1 : -0.1)
    }

    this.handleMouseDown = (event) => {
      if (event.button !== 0) return
      const wrapper = document.querySelector(".image-wrapper")
      if (!wrapper) return
      this.dragState.isDragging = true
      this.dragState.startX = event.clientX
      this.dragState.startY = event.clientY
      this.dragState.scrollLeft = Number.parseFloat(wrapper.style.left || "0")
      this.dragState.scrollTop = Number.parseFloat(wrapper.style.top || "0")
      document.addEventListener("mousemove", this.handleMouseMove)
      document.addEventListener("mouseup", this.handleMouseUp)
      event.preventDefault()
    }

    this.handleMouseMove = (event) => {
      if (!this.dragState.isDragging) return
      event.preventDefault()
      const wrapper = document.querySelector(".image-wrapper")
      if (!wrapper) return
      wrapper.style.left = `${this.dragState.scrollLeft + event.clientX - this.dragState.startX}px`
      wrapper.style.top  = `${this.dragState.scrollTop  + event.clientY - this.dragState.startY}px`
    }

    this.handleMouseUp = () => {
      if (!this.dragState.isDragging) return
      this.dragState.isDragging = false
      this.dragState.container = null
      document.removeEventListener("mousemove", this.handleMouseMove)
      document.removeEventListener("mouseup", this.handleMouseUp)
    }

    // ── Structure image zoom / pan ─────────────────────────────────────────
    this.adjustZoom2 = (delta) => {
      const newZoom = Math.min(5, Math.max(0.5, this.state.zoomLevel2 + delta))
      this.state.zoomLevel2 = newZoom
      const wrapper = document.querySelector(".image-wrapper-2")
      if (wrapper) wrapper.style.transform = `scale(${newZoom})`
    }

    this.resetZoom2 = () => {
      this.state.zoomLevel2 = 1.0
      const wrapper = document.querySelector(".image-wrapper-2")
      const container = document.querySelector(".zoom-container-2")
      if (wrapper) { wrapper.style.transform = "scale(1)"; wrapper.style.left = "0px"; wrapper.style.top = "0px" }
      if (container) { container.scrollTop = 0; container.scrollLeft = 0 }
    }

    this.fitToContainer2 = () => {
      this.state.zoomLevel2 = 1.0
      const wrapper = document.querySelector(".image-wrapper-2")
      const container = document.querySelector(".zoom-container-2")
      if (wrapper) { wrapper.style.transform = "scale(1)"; wrapper.style.left = "0px"; wrapper.style.top = "0px" }
      if (container) { container.scrollTop = 0; container.scrollLeft = 0 }
    }

    this.handleWheel2 = (event) => {
      event.preventDefault()
      this.adjustZoom2(event.deltaY < 0 ? 0.1 : -0.1)
    }

    this.handleMouseDown2 = (event) => {
      if (event.button !== 0) return
      const wrapper = document.querySelector(".image-wrapper-2")
      if (!wrapper) return
      this.dragState2.isDragging = true
      this.dragState2.startX = event.clientX
      this.dragState2.startY = event.clientY
      this.dragState2.scrollLeft = Number.parseFloat(wrapper.style.left || "0")
      this.dragState2.scrollTop = Number.parseFloat(wrapper.style.top || "0")
      document.addEventListener("mousemove", this.handleMouseMove2)
      document.addEventListener("mouseup", this.handleMouseUp2)
      event.preventDefault()
    }

    this.handleMouseMove2 = (event) => {
      if (!this.dragState2.isDragging) return
      event.preventDefault()
      const wrapper = document.querySelector(".image-wrapper-2")
      if (!wrapper) return
      wrapper.style.left = `${this.dragState2.scrollLeft + event.clientX - this.dragState2.startX}px`
      wrapper.style.top  = `${this.dragState2.scrollTop  + event.clientY - this.dragState2.startY}px`
    }

    this.handleMouseUp2 = () => {
      if (!this.dragState2.isDragging) return
      this.dragState2.isDragging = false
      document.removeEventListener("mousemove", this.handleMouseMove2)
      document.removeEventListener("mouseup", this.handleMouseUp2)
    }

    const rawValue = this.props.record?.data?.[this.props.name]
    const computedRawValue = this.props.record?.data?.measurement_widget_data_with_images
    console.log("Debug: Raw field value:", rawValue)
    let parsedValue = null
    let parsedComputedValue = null
    if (computedRawValue) {
      try {
        parsedComputedValue =
          typeof computedRawValue === "string" ? JSON.parse(computedRawValue) : computedRawValue
      } catch (e) {
        console.error("Debug: Error parsing computed field value:", e)
        parsedComputedValue = null
      }
    }
    if (rawValue && typeof rawValue === "string") {
      try {
        parsedValue = JSON.parse(rawValue)
      } catch (e) {
        console.error("Debug: Error parsing field value:", e)
        parsedValue = null
      }
    } else if (rawValue && typeof rawValue === "object") {
      parsedValue = rawValue
    }
    if (parsedComputedValue) {
      parsedValue = parsedComputedValue
    }

    if (parsedValue) {
      if (parsedValue?.status) this.state.status = parsedValue.status
      if (parsedValue.unit) this.state.unit = parsedValue.unit

      // Backward-compat: read hiddenPanels so we can skip panels the user
      // explicitly removed in old sessions (they used to be "hidden" not deleted)
      const legacyHidden = parsedValue.hiddenPanels || []

      // Helper to load panel data
      const _loadPanelData = (key, src, defaultName) => {
        console.log(`[LoadPanel] key=${key} image=${src.image?.length} annotated_image_url=${src.annotated_image_url?.length} annotated_att_id=${src.annotated_image_attachment_id}`)
        this.state.panels[key] = {
          name: defaultName || (key[0].toUpperCase() + key.slice(1)),
          image: src.image || null,
          image_attachment_id: src.image_attachment_id || null,
          image2: src.image2 || null,
          image2_attachment_id: src.image2_attachment_id || null,
          annotated_image_url: src.annotated_image_url || null,
          annotated_image_attachment_id: src.annotated_image_attachment_id || null,
          measurements: (src.measurements || []).map((m) => ({
            point: m.point,
            name: m.name,
            value:
              m.value === "" || m.value === null
                ? ""
                : isNaN(Number.parseFloat(m.value))
                  ? m.value
                  : Number.parseFloat(m.value).toFixed(3),
          })),
          panelRequests: src.panelRequests || [],
          // activeEditVersion: the panelRequest version currently being edited in the table.
          // null = no active new-request; latest version = that row is editable.
          activeEditVersion: src.panelRequests?.length > 0
            ? Math.max(...src.panelRequests.map(r => r.version))
            : null,
          // Keep legacy fields so old saved data round-trips safely
          pendingChanges: src.pendingChanges || {},
          hasPendingRequest: src.hasPendingRequest || false,
          pendingBaseVersion: src.pendingBaseVersion !== undefined ? src.pendingBaseVersion
            : (src.panelRequests?.length > 0 ? Math.max(...src.panelRequests.map(r => r.version)) : 1),
        }
        this.seedPanel(key)
      }

      // Load customPanels list first
      this.state.customPanels = parsedValue.customPanels || []

      // Backward compat: old records stored front/back/sleeve/collar directly
      // in parsedValue instead of in customPanels. Merge them in at the front.
      const legacyCore = ["front", "back", "sleeve", "collar"]
      for (const key of legacyCore) {
        if (legacyHidden.includes(key)) continue // was hidden/deleted in old session
        if (!parsedValue[key]) continue          // wasn't saved for this key
        _loadPanelData(key, parsedValue[key], key[0].toUpperCase() + key.slice(1))
        // Add to customPanels list if not already there
        if (!this.state.customPanels.find((cp) => cp.id === key)) {
          this.state.customPanels.unshift({ id: key, name: key[0].toUpperCase() + key.slice(1) })
        }
      }

      // Load custom panel bodies
      this.state.customPanels.forEach((cp) => {
        if (parsedValue[cp.id] && !this.state.panels[cp.id]) {
          _loadPanelData(cp.id, parsedValue[cp.id], cp.name)
        }
      })

      // Active panel = index [0]
      this.state.activePanel = this.state.customPanels[0]?.id || null
    } else {
      // No saved data — start completely empty
      this.state.activePanel = null
    }

    console.log("Debug: Final widget state:", this.state)

    this.addMeasurement = this.addMeasurement.bind(this)
    this.removeMeasurement = this.removeMeasurement.bind(this)
    this.updateMeasurement = this.updateMeasurement.bind(this)
    this.setActiveTab = this.setActiveTab.bind(this)
    this.setActivePanel = this.setActivePanel.bind(this)
    this.getCurrentPanelMeasurements = this.getCurrentPanelMeasurements.bind(this)
    this.getCurrentPanelName = this.getCurrentPanelName.bind(this)
    this.getCurrentPanelImage = this.getCurrentPanelImage.bind(this)
    this.getCurrentPanelImage2 = this.getCurrentPanelImage2.bind(this)
    this.addNewPanel = this.addNewPanel.bind(this)
    this.removePanel = this.removePanel.bind(this)
    this.handleImageUpload = this.handleImageUpload.bind(this)
    this.handleImage2Upload = this.handleImage2Upload.bind(this)
    this.triggerFileInput = this.triggerFileInput.bind(this)
    this.triggerFile2Input = this.triggerFile2Input.bind(this)
    this.deleteCurrentPanelImage = this.deleteCurrentPanelImage.bind(this)
    this.deleteCurrentPanelImage2 = this.deleteCurrentPanelImage2.bind(this)
    this.notifyFormChange = this.notifyFormChange.bind(this)
    this.setupSaveHook = this.setupSaveHook.bind(this)
    this.saveChanges = this.saveChanges.bind(this)
    this.handleDragOver = this.handleDragOver.bind(this)
    this.handleDragEnter = this.handleDragEnter.bind(this)
    this.handleDragLeave = this.handleDragLeave.bind(this)
    this.handleDrop = this.handleDrop.bind(this)
    this.handleDrop2 = this.handleDrop2.bind(this)
    this.showAddPanelModal = this.showAddPanelModal.bind(this)
    this.hideAddPanelModal = this.hideAddPanelModal.bind(this)
    this.confirmAddPanel = this.confirmAddPanel.bind(this)
    this.updateNewPanelName = this.updateNewPanelName.bind(this)
    this.fitToContainer = this.fitToContainer.bind(this)
    this.handleWheel = this.handleWheel.bind(this)
    this.handleMouseDown = this.handleMouseDown.bind(this)
    this.handleMouseMove = this.handleMouseMove.bind(this)
    this.handleMouseUp = this.handleMouseUp.bind(this)
    this.toggleStatus = this.toggleStatus.bind(this)
    this.refreshPanelData = this.refreshPanelData.bind(this)
    this.toggleUnit = this.toggleUnit.bind(this)
    this.getCurrentUnit = this.getCurrentUnit.bind(this)
    this.handleInputFocus = this.handleInputFocus.bind(this)
    this.handleInputBlur = this.handleInputBlur.bind(this)
    this.getConfirmedRequests = this.getConfirmedRequests.bind(this)
    this.getValuesAtVersion = this.getValuesAtVersion.bind(this)
    this.getLatestVersionNumber = this.getLatestVersionNumber.bind(this)
    this.getLastRequestVersion = this.getLastRequestVersion.bind(this)
    this.getLastRequestValues = this.getLastRequestValues.bind(this)
    this.getNewRequestValues = this.getNewRequestValues.bind(this)
    this.getChangeForPoint = this.getChangeForPoint.bind(this)
    this.hasActiveRequest = this.hasActiveRequest.bind(this)
    this.getActiveEditVersion = this.getActiveEditVersion.bind(this)
    this.createNewRequest = this.createNewRequest.bind(this)
    this.setNewRequestValue = this.setNewRequestValue.bind(this)
    this.deleteLatestRequest = this.deleteLatestRequest.bind(this)
    this.getNextRequestVersion = this.getNextRequestVersion.bind(this)
    this.getPanelHasPendingRequest = this.getPanelHasPendingRequest.bind(this)
    this.getAvailableBaseVersions = this.getAvailableBaseVersions.bind(this)
    this.getPendingBaseVersion = this.getPendingBaseVersion.bind(this)
    this.setPendingBaseVersion = this.setPendingBaseVersion.bind(this)
    this.getPendingChangeDisplay = this.getPendingChangeDisplay.bind(this)
    this.setPendingChange = this.setPendingChange.bind(this)
    this.getPendingTotal = this.getPendingTotal.bind(this)
    this.getActualValue = this.getActualValue.bind(this)
    this.getActualVersionsForPanel = this.getActualVersionsForPanel.bind(this)
    this.getSelectedActualVersion = this.getSelectedActualVersion.bind(this)
    this.setSelectedActualVersion = this.setSelectedActualVersion.bind(this)
    this.panelHasActuals = this.panelHasActuals.bind(this)

    // Load toile documentation actuals
    const docRaw = this.props.record?.data?.toile_doc_data
    this.state.toileDocData = docRaw
      ? (typeof docRaw === "object" ? docRaw : (() => { try { return JSON.parse(docRaw) } catch { return {} } })())
      : {}
    this.state.selectedActualVersions = {}

    // Setup save hook after initializing state
    this.setupSaveHook()
  }

  onMounted() {
    const zoomContainer = document.querySelector(".zoom-container")
    if (zoomContainer) {
      zoomContainer.addEventListener("wheel", (e) => {
        e.preventDefault()
        const delta = e.deltaY < 0 ? 0.1 : -0.1
        this.adjustZoom(delta)
      })
    }
  }

  hasAnyPanels() {
    return Object.keys(this.state.panels).length > 0
  }

  _firstAvailablePanel() {
    return this.state.customPanels[0]?.id || null
  }

  getNextPoint(measurements) {
    if (!measurements || !Array.isArray(measurements)) return "A"

    const usedPoints = new Set(measurements.map((m) => m?.point || "").filter(Boolean))

    // Search through infinite sequence until we find an unused label
    for (let i = 0; ; i++) {
      const label = this.getPointLabel(i)
      if (!usedPoints.has(label)) {
        return label
      }
    }
  }

  resequencePoints(panel) {
    if (!panel?.measurements || !Array.isArray(panel.measurements)) return

    panel.measurements.forEach((measurement, index) => {
      if (measurement) {
        measurement.point = this.getPointLabel(index)
      }
    })
  }

  getPointLabel(i) {
    // 0->A, 1->B, ... 25->Z, 26->A2, 27->B2, ... 51->Z2, 52->A3, ...
    const cycle = Math.floor(i / 26)
    const letter = this.letters[i % 26]
    return cycle === 0 ? letter : letter + (cycle + 1)
  }

  seedPanel(panelKey, initial = []) {
    const panel = this.state.panels[panelKey]
    if (!panel) return
    if (!Array.isArray(panel.measurements)) panel.measurements = []

    // load any provided defaults
    if (initial.length && panel.measurements.length === 0) {
      panel.measurements = initial
    }

    // pad up to 2 rows (A, B) with blank values
    const existing = panel.measurements.length
    for (let i = existing; i < 2; i++) {
      panel.measurements.push({
        point: this.getPointLabel(i),
        name: "",
        value: "",
      })
    }
  }

  addMeasurement(panelKey) {
    const panel = this.state.panels[panelKey]
    if (!panel || !panel.measurements) return

    const nextPoint = this.getNextPoint(panel.measurements)
    panel.measurements.push({
      point: nextPoint,
      name: "",
      value: "",
    })
    this.notifyFormChange()
  }

  addMultipleRows(panelKey) {
    const panel = this.state.panels[panelKey]
    if (!panel || !panel.measurements) return

    const startIndex = panel.measurements.length
    this.dialogService.add(AddRowsDialog, {
      startIndex,
      getPointLabel: (idx) => this.getPointLabel(idx),
      onConfirm: (count) => {
        for (let i = 0; i < count; i++) {
          panel.measurements.push({
            point: this.getPointLabel(startIndex + i),
            name: "",
            value: "",
          })
        }
        this.notifyFormChange()
      },
    })
  }

  removeMeasurement(panelKey, index) {
    const panel = this.state.panels[panelKey]
    if (!panel?.measurements || index < 0 || index >= panel.measurements.length) return

    const m = panel.measurements[index]
    const label = m.point ? `point ${m.point}` : "this row"
    this.dialogService.add(ConfirmationDialog, {
      title: "Delete Row",
      body: `Are you sure you want to delete ${label}?`,
      confirm: () => {
        panel.measurements.splice(index, 1)
        this.notifyFormChange()
      },
    })
  }

  handleRowDragStart(ev, index) {
    this._dragSourceIndex = index
    ev.dataTransfer.effectAllowed = 'move'
  }

  handleRowDragOver(ev) {
    ev.preventDefault()
    ev.dataTransfer.dropEffect = 'move'
  }

  handleRowDrop(ev, panelKey, targetIndex) {
    ev.preventDefault()
    const sourceIndex = this._dragSourceIndex
    this._dragSourceIndex = null
    if (sourceIndex === null || sourceIndex === undefined || sourceIndex === targetIndex) return

    const panel = this.state.panels[panelKey]
    if (!panel?.measurements) return

    const [removed] = panel.measurements.splice(sourceIndex, 1)
    panel.measurements.splice(targetIndex, 0, removed)
    this.notifyFormChange()
  }

  handleRowDragEnd() {
    this._dragSourceIndex = null
  }

  updateMeasurement(panelKey, index, field, value) {
    const panel = this.state.panels[panelKey]
    if (!panel?.measurements?.[index]) return
    panel.measurements[index][field] = value // no toFixed here
    this.notifyFormChange()
  }

  roundToEighth(value) {
    const num = Number.parseFloat(value)
    return num
  }

  handleValueKeyDown(panelKey, index, ev) {
    if (ev.key !== "Enter") return
    ev.preventDefault()
    this.formatValueToGrid(panelKey, index) // <- use grid-aware blur

    // lock in formatting before moving
    this.formatValueToEighth(panelKey, index)

    // find all value inputs in this table, figure out "next"
    const table = ev.currentTarget.closest("table")
    const valueInputs = Array.from(table.querySelectorAll('tbody input[data-role="value-input"]'))

    // if no rows → just save
    if (valueInputs.length === 0) {
      // safe trigger of form save (uses your intercepted save hook)
      this.props.record?.save?.()
      return
    }

    const me = ev.currentTarget
    const pos = valueInputs.indexOf(me)

    // if there is a next row → focus it
    if (pos > -1 && pos < valueInputs.length - 1) {
      const nxt = valueInputs[pos + 1]
      nxt?.focus()
      nxt?.select()
      this.props.record?.save?.()
      return
    }

    // last row → save
    this.props.record?.save?.()
  }
  handleNewReqKeyDown(ev) {
    if (ev.key !== 'Enter') return
    ev.preventDefault()
    const table = ev.currentTarget.closest('table')
    const inputs = Array.from(table?.querySelectorAll('tbody input[data-role="newreq-input"]') || [])
    const pos = inputs.indexOf(ev.currentTarget)
    if (pos > -1 && pos < inputs.length - 1) {
      inputs[pos + 1].focus()
      inputs[pos + 1].select()
    }
  }

  handleNameKeyDown(panelKey, index, ev) {
    if (ev.key !== "Enter") return
    ev.preventDefault()
    ev.stopPropagation()

    const table = ev.currentTarget.closest("table")
    const nameInputs = Array.from(table.querySelectorAll('tbody input[data-role="name-input"]'))
    if (nameInputs.length === 0) {
      this.props.record?.save?.()
      return
    }

    const pos = nameInputs.indexOf(ev.currentTarget)
    if (pos > -1 && pos < nameInputs.length - 1) {
      const nxt = nameInputs[pos + 1]
      nxt?.focus()
      nxt?.select()
      this.props.record?.save?.()
      return
    }
    this.props.record?.save?.()
  }

  formatValueToEighth(panelKey, index) {
    const panel = this.state.panels[panelKey]
    const m = panel?.measurements?.[index]
    if (!m) return
    if (m.value === "" || m.value === null) {
      m.value = ""
      return
    }
    m.value = this.roundToEighth(m.value)
  }

  triggerFieldUpdate() {
    this.notifyFormChange()
  }

  setActiveTab(tab) {
    console.log("Debug: setActiveTab called with tab:", tab)
    this.state.activeTab = tab
  }

  setActivePanel(panelKey) {
    console.log("Debug: setActivePanel called with panelKey:", panelKey)
    this.state.activePanel = panelKey
  }

  getCurrentPanelMeasurements() {
    const panel = this.state.panels[this.state.activePanel]
    return panel?.measurements || []
  }

  panelHasData(panelId) {
    const panel = this.state.panels[panelId]
    if (!panel?.measurements?.length) return false
    return panel.measurements.some(
      (m) => (m.name && m.name.trim()) || (m.value !== '' && m.value !== null && m.value !== undefined)
    )
  }

  getCurrentPanelName() {
    const panel = this.state.panels[this.state.activePanel]
    if (panel) return panel.name
    const customPanel = this.state.customPanels.find((p) => p.id === this.state.activePanel)
    return customPanel?.name || this.state.activePanel
  }

  getCurrentPanelImage() {
    const panel = this.state.panels[this.state.activePanel]
    // Show annotated version if available, otherwise the original
    return panel?.annotated_image_url || panel?.image || null
  }

  getCurrentPanelImage2() {
    const panel = this.state.panels[this.state.activePanel]
    return panel?.image2 || null
  }

  addNewPanel() {
    this.showAddPanelModal()
  }

  get canAddPanel() {
    const isToile = this.props.record?.data?.is_toile_mo
    if (isToile && this.state.customPanels.length >= 1) return false
    return true
  }

  showAddPanelModal() {
    this.state.showAddPanelModal = true
    this.state.newPanelName = ""
  }

  hideAddPanelModal() {
    this.state.showAddPanelModal = false
    this.state.newPanelName = ""
  }

  updateNewPanelName(value) {
    this.state.newPanelName = value
  }

  confirmAddPanel() {
    const panelName = this.state.newPanelName.trim()
    if (!panelName) return

    const panelId = panelName.toLowerCase().replace(/\s+/g, "_")
    this.state.customPanels.push({
      id: panelId,
      name: panelName,
    })
    this.state.panels[panelId] = {
      name: panelName,
      measurements: [],
      image: null,
      image_attachment_id: null,
      image2: null,
      image2_attachment_id: null,
    }
    this.seedPanel(panelId)
    this.state.activePanel = panelId
    this.hideAddPanelModal()
    this.notifyFormChange()
  }

  removePanel(panelId) {
    const panelName = this.state.panels[panelId]?.name || panelId
    this.dialogService.add(ConfirmationDialog, {
      title: "Delete Panel",
      body: `Are you sure you want to delete the "${panelName}" panel?`,
      confirm: () => this._doRemovePanel(panelId),
    })
  }

  _doRemovePanel(panelId) {
    this.state.customPanels = this.state.customPanels.filter((p) => p.id !== panelId)
    delete this.state.panels[panelId]
    if (this.state.activePanel === panelId) {
      this.state.activePanel = this.state.customPanels[0]?.id || null
    }
    this.notifyFormChange()
  }

  triggerFileInput() {
    const fileInput = this.__owl__.refs.fileInput
    if (fileInput) {
      fileInput.click()
    } else {
      console.log("Debug: File input reference not found")
    }
  }

  triggerFile2Input() {
    const fileInput = this.__owl__.refs.file2Input
    if (fileInput) {
      fileInput.click()
    } else {
      console.log("Debug: File2 input reference not found")
    }
  }

  handleImageUpload(event) {
    const file = event.target.files[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      const panel = this.state.panels[this.state.activePanel]
      if (panel) {
        panel.image = e.target.result
        panel.image_attachment_id = null
        // New upload clears any prior annotation
        panel.annotated_image_url = null
        panel.annotated_image_attachment_id = null
        panel.originalImage = null
        this.notifyFormChange()
      }
    }
    reader.readAsDataURL(file)
  }

  handleImage2Upload(event) {
    const file = event.target.files[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      const panel = this.state.panels[this.state.activePanel]
      if (panel) {
        panel.image2 = e.target.result
        panel.image2_attachment_id = null
        this.notifyFormChange()
      }
    }
    reader.readAsDataURL(file)
  }

  deleteCurrentPanelImage() {
    this.dialogService.add(ConfirmationDialog, {
      title: "Delete Image",
      body: "Are you sure you want to delete this panel image?",
      confirm: () => {
        const panel = this.state.panels[this.state.activePanel]
        if (panel) {
          panel.image = null
          panel.image_attachment_id = null
          this.notifyFormChange()
        }
      },
    })
  }

  deleteCurrentPanelImage2() {
    this.dialogService.add(ConfirmationDialog, {
      title: "Delete Image",
      body: "Are you sure you want to delete this structure image?",
      confirm: () => {
        const panel = this.state.panels[this.state.activePanel]
        if (panel) {
          panel.image2 = null
          panel.image2_attachment_id = null
          this.notifyFormChange()
        }
      },
    })
  }

  // ── Annotation helpers ────────────────────────────────────────────────────

  hasAnnotatedImage() {
    const panel = this.state.panels[this.state.activePanel]
    return !!(panel?.annotated_image_url)
  }

  restoreOriginalImage() {
    const panel = this.state.panels[this.state.activePanel]
    if (panel) {
      panel.annotated_image = null
      panel.annotated_image_url = null
      panel.annotated_image_attachment_id = null
      panel.originalImage = null
      this.notifyFormChange()
    }
  }

  async generateAnnotatedImage() {
    const panelId = this.state.activePanel
    const panel = this.state.panels[panelId]
    const placeholder = '/maeknit_sales_customization/static/src/img/place.png'

    if (!panel?.image || panel.image === placeholder) {
      this.notification.add('Upload a panel image first.', { type: 'warning' })
      return
    }

    // Always annotate from the original image (panel.image = original URL or unsaved base64).
    // panel.originalImage is only used as in-memory cache for unsaved base64 images.
    const imageIsBase64 = panel.image ? panel.image.startsWith('data:') : false
    if (imageIsBase64 && !panel.originalImage) {
      panel.originalImage = panel.image
    } else if (!imageIsBase64) {
      panel.originalImage = null
    }

    // Decide which columns to show
    const hasReq = this.hasActiveRequest(panelId)
    const lastReqVer  = this.getLastRequestVersion(panelId)
    const activeReqVer = this.getActiveEditVersion(panelId)
    const lastReqVals  = hasReq ? this.getLastRequestValues(panelId) : null
    const newReqVals   = hasReq ? this.getNewRequestValues(panelId) : null

    const measurements = (panel.measurements || []).filter((m) => {
      if (!m.point) return false
      const hasBase = m.value !== '' && m.value !== null && m.value !== undefined
      const hasNewReq = hasReq && newReqVals && newReqVals[m.point] !== undefined && newReqVals[m.point] !== null && newReqVals[m.point] !== ''
      const hasLastReq = hasReq && lastReqVals && lastReqVals[m.point] !== undefined && lastReqVals[m.point] !== null && lastReqVals[m.point] !== ''
      return hasBase || hasNewReq || hasLastReq
    })
    if (!measurements.length) {
      this.notification.add('No measurements to annotate.', { type: 'warning' })
      return
    }

    const hasActuals   = this.panelHasActuals(panelId)
    const actualVer    = hasActuals ? this.getSelectedActualVersion(panelId) : null
    const actualVals   = hasActuals ? this.getActualVersionsForPanel(panelId).find(v => v.version === actualVer)?.measurements : null

    // Load image — works for both base64 dataURLs and same-origin attachment URLs
    const img = new Image()
    img.crossOrigin = 'anonymous'
    let imgSrc = panel.originalImage || panel.image
    if (!imgSrc.startsWith('data:')) {
      try {
        const resp = await fetch(imgSrc)
        const blob = await resp.blob()
        imgSrc = URL.createObjectURL(blob)
      } catch (_) { /* fall through to direct src */ }
    }
    await new Promise((resolve, reject) => {
      img.onload = resolve
      img.onerror = reject
      img.src = imgSrc
    })

    // ── Table sizing (scaled to image resolution) ──────────────────────────
    const FONT_SIZE = Math.max(11, Math.round(img.width / 45))
    const ROW_H     = Math.round(FONT_SIZE * 2.2)
    const CELL_PAD  = Math.round(FONT_SIZE * 0.7)
    const unit      = this.state.unit === 'inches' ? 'in' : 'cm'

    // Columns: always Point + Last Req; optionally Change + New Req; optionally Actual; always blank Notes
    const COL_PT    = FONT_SIZE * 3
    const COL_VAL   = FONT_SIZE * 6.5
    const COL_CHG   = FONT_SIZE * 5   // Change column (narrower)
    const COL_NOTES = FONT_SIZE * 7   // Blank fill-in column

    // Build column list
    const cols = [
      { key: 'pt',      label: 'Pt',                          width: COL_PT    },
      { key: 'lastReq', label: `Req ${lastReqVer} (${unit})`, width: COL_VAL   },
    ]
    if (hasReq) {
      cols.push({ key: 'change',  label: 'Change',                         width: COL_CHG })
      cols.push({ key: 'newReq',  label: `Req ${activeReqVer} (${unit})`,  width: COL_VAL })
    }
    if (hasActuals) {
      cols.push({ key: 'actual', label: `Actual v${actualVer}`, width: COL_VAL })
    }
    cols.push({ key: 'notes', label: 'Notes', width: COL_NOTES })

    // Compute total table width
    let TABLE_W = CELL_PAD
    for (const c of cols) TABLE_W += c.width + CELL_PAD

    const panelName  = this.getCurrentPanelName() || ''
    const TITLE_H    = panelName ? Math.round(ROW_H * 1.8) : 0
    const PAD_T      = 30
    const PAD_B      = 30
    const HEADER_H   = Math.round(ROW_H * 1.5)
    const tableContentH = TITLE_H + HEADER_H + measurements.length * ROW_H

    const canvas = document.createElement('canvas')
    canvas.width  = TABLE_W + img.width
    canvas.height = Math.max(img.height + PAD_T + PAD_B, tableContentH + PAD_T + PAD_B)
    const ctx = canvas.getContext('2d')

    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, TABLE_W, PAD_T)

    // ── Panel name title row ───────────────────────────────────────────────
    if (TITLE_H > 0) {
      ctx.fillStyle = '#1a3a5c'
      ctx.fillRect(0, PAD_T, TABLE_W, TITLE_H)
      ctx.fillStyle = '#ffffff'
      ctx.font = `bold ${Math.round(FONT_SIZE * 1.2)}px Arial, sans-serif`
      ctx.textBaseline = 'middle'
      ctx.textAlign = 'center'
      ctx.fillText(panelName, TABLE_W / 2, PAD_T + TITLE_H / 2)
    }

    // ── Table header ───────────────────────────────────────────────────────
    const headerY = PAD_T + TITLE_H
    ctx.fillStyle = '#2c3e50'
    ctx.fillRect(0, headerY, TABLE_W, HEADER_H)
    ctx.fillStyle = '#ffffff'
    ctx.font = `bold ${FONT_SIZE}px Arial, sans-serif`
    ctx.textBaseline = 'middle'

    const hMid = headerY + HEADER_H / 2
    let xCursor = CELL_PAD
    for (const c of cols) {
      ctx.textAlign = c.key === 'pt' ? 'center' : 'right'
      ctx.fillText(c.label, xCursor + (c.key === 'pt' ? c.width / 2 : c.width), hMid)
      xCursor += c.width + CELL_PAD
    }

    // ── Table rows ─────────────────────────────────────────────────────────
    measurements.forEach((m, i) => {
      const y   = PAD_T + HEADER_H + i * ROW_H
      const mid = y + ROW_H / 2

      ctx.fillStyle = i % 2 === 0 ? '#f8f9fa' : '#ffffff'
      ctx.fillRect(0, y, TABLE_W, ROW_H)
      ctx.strokeStyle = '#dee2e6'
      ctx.lineWidth   = 0.5
      ctx.strokeRect(0, y, TABLE_W, ROW_H)

      ctx.textBaseline = 'middle'
      let xc = CELL_PAD

      for (const c of cols) {
        let text = ''
        let color = '#212529'

        if (c.key === 'pt') {
          text  = m.point
          color = '#c80000'
          ctx.fillStyle = color
          ctx.font      = `bold ${FONT_SIZE}px Arial, sans-serif`
          ctx.textAlign = 'center'
          ctx.fillText(text, xc + c.width / 2, mid)
          xc += c.width + CELL_PAD
          continue
        }

        if (c.key === 'lastReq') {
          const val = lastReqVals ? lastReqVals[m.point] : parseFloat(m.value)
          text = val !== undefined && val !== null ? Number(val).toFixed(3) : '—'
        } else if (c.key === 'change') {
          const chg = this.getChangeForPoint(panelId, m.point)
          text  = chg !== 0 ? (chg > 0 ? '+' : '') + chg.toFixed(3) : '0'
          color = chg > 0 ? '#c80000' : chg < 0 ? '#1a56db' : '#6c757d'
        } else if (c.key === 'newReq') {
          const val = newReqVals?.[m.point]
          text  = val !== undefined && val !== null ? Number(val).toFixed(3) : '—'
          color = '#1a56db'
        } else if (c.key === 'actual') {
          const val = actualVals?.[m.point]
          text  = val !== null && val !== undefined ? Number(val).toFixed(3) : '—'
          color = '#198754'
        }

        ctx.fillStyle = color
        ctx.font      = `${FONT_SIZE}px Arial, sans-serif`
        ctx.textAlign = 'right'
        ctx.fillText(text, xc + c.width, mid)
        xc += c.width + CELL_PAD
      }
    })

    // ── Column dividers ────────────────────────────────────────────────────
    const divH = HEADER_H + measurements.length * ROW_H
    ctx.strokeStyle = '#adb5bd'
    ctx.lineWidth   = 1
    let xDiv = CELL_PAD
    for (let ci = 0; ci < cols.length - 1; ci++) {
      xDiv += cols[ci].width + CELL_PAD / 2
      ctx.beginPath()
      ctx.moveTo(xDiv, PAD_T)
      ctx.lineTo(xDiv, PAD_T + divH)
      ctx.stroke()
      xDiv += CELL_PAD / 2
    }

    // ── Separator between table and image ─────────────────────────────────
    ctx.strokeStyle = '#6c757d'
    ctx.lineWidth   = 2
    ctx.beginPath()
    ctx.moveTo(TABLE_W, PAD_T)
    ctx.lineTo(TABLE_W, PAD_T + img.height)
    ctx.stroke()

    // Store annotated result separately — original image is preserved untouched
    panel.annotated_image = canvas.toDataURL('image/png')
    panel.annotated_image_url = panel.annotated_image   // display immediately (will become URL after save)
    panel.annotated_image_attachment_id = null           // cleared so backend creates a new attachment
    this.notifyFormChange()
    this.notification.add('Measurement table generated. Save to persist.', { type: 'success' })
  }

  // ─────────────────────────────────────────────────────────────────────────

  handleDragOver(event) {
    event.preventDefault()
    event.stopPropagation()
    event.stopImmediatePropagation()

    const dropZone = event.currentTarget
    dropZone.classList.add("border-blue-500", "bg-blue-50")
  }

  handleDragEnter(event) {
    event.preventDefault()
    event.stopPropagation()
    event.stopImmediatePropagation()

    const dropZone = event.currentTarget
    dropZone.classList.add("border-blue-500", "bg-blue-50")
  }

  handleDragLeave(event) {
    event.preventDefault()
    event.stopPropagation()
    event.stopImmediatePropagation()

    const dropZone = event.currentTarget
    dropZone.classList.remove("border-blue-500", "bg-blue-50")
  }

  handleDrop(event) {
    event.preventDefault()
    event.stopPropagation()
    event.stopImmediatePropagation()

    const dropZone = event.currentTarget
    dropZone.classList.remove("border-blue-500", "bg-blue-50")

    const files = event.dataTransfer.files
    if (files.length > 0) {
      const file = files[0]
      if (file.type.startsWith("image/")) {
        const reader = new FileReader()
        reader.onload = (e) => {
          const panel = this.state.panels[this.state.activePanel]
          if (panel) {
            panel.image = e.target.result
            panel.image_attachment_id = null
            this.notifyFormChange()
          }
        }
        reader.readAsDataURL(file)
      }
    }
  }

  handleDrop2(event) {
    event.preventDefault()
    event.stopPropagation()
    event.stopImmediatePropagation()

    const dropZone = event.currentTarget
    dropZone.classList.remove("border-blue-500", "bg-blue-50")

    const files = event.dataTransfer.files
    if (files.length > 0) {
      const file = files[0]
      if (file.type.startsWith("image/")) {
        const reader = new FileReader()
        reader.onload = (e) => {
          const panel = this.state.panels[this.state.activePanel]
          if (panel) {
            panel.image2 = e.target.result
            panel.image2_attachment_id = null
            this.notifyFormChange()
          }
        }
        reader.readAsDataURL(file)
      }
    }
  }

  getCurrentPanelAttachmentId() {
    const panel = this.state.panels[this.state.activePanel]
    // Prefer annotated attachment for download if available
    return (panel && (panel.annotated_image_attachment_id || panel.image_attachment_id)) || null
  }

  getCurrentPanelImageDownloadUrl() {
    const panel = this.state.panels[this.state.activePanel]
    const displayImage = panel?.annotated_image_url || panel?.image
    if (!displayImage) return null

    // Annotated attachment takes priority
    if (panel.annotated_image_attachment_id) {
      return `/web/content/${panel.annotated_image_attachment_id}?download=1`
    }
    // Unsaved annotated blob (generated but not yet saved)
    if (panel.annotated_image?.startsWith('data:')) {
      return panel.annotated_image
    }
    const attachmentId = panel.image_attachment_id
    if (attachmentId) {
      return `/web/content/${attachmentId}?download=1`
    }
    // For base64/data URL images (not yet saved as attachments), return the data URL directly
    if (displayImage.startsWith('data:')) {
      return displayImage
    }
    return null
  }

  downloadAllPanelsCSV() {
    const unit = this.state.unit
    const rows = [['Panel', 'Point', `Value (${unit})`, 'Measurement Name']]

    const allPanelIds = this.state.customPanels.map((p) => p.id)

    for (const panelId of allPanelIds) {
      const panel = this.state.panels[panelId]
      if (!panel) continue
      const panelName = panel.name || panelId
      for (const m of panel.measurements || []) {
        rows.push([panelName, m.point || '', m.value || '', m.name || ''])
      }
    }

    const csv = rows
      .map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n')

    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'measurement_chart.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  notifyFormChange() {
    try {
      // Mark the record as dirty so Odoo's save button becomes enabled
      if (this.props.record && this.props.record.model) {
        if (this.props.record.model.root) {
          this.props.record.model.root.dirty = true
        }
      }

      // Enable the save button in the UI
      const statusIndicator = document.querySelector(".o_form_status_indicator_buttons")
      if (statusIndicator && statusIndicator.classList.contains("invisible")) {
        statusIndicator.classList.remove("invisible")
      }

      const saveButton = document.querySelector(".o_form_button_save")
      if (saveButton && saveButton.hasAttribute("disabled")) {
        saveButton.removeAttribute("disabled")
      }

      this.state.isDirty = true
      console.log("Debug: Form marked as dirty")
    } catch (error) {
      console.error("Debug: Error notifying form change:", error)
    }
  }

  setupSaveHook() {
    try {
      if (this.props.record && this.props.record.save) {
        const originalSave = this.props.record.save.bind(this.props.record)

        this.props.record.save = async (...args) => {
          console.log("Debug: Odoo save intercepted - saving measurement data")

          // Save our measurement data before the main save
          if (this.state.isDirty) {
            await this.saveChanges()
          }

          // Call the original save method
          const result = await originalSave(...args)

          // Mark as clean after successful save
          this.state.isDirty = false

          return result
        }
      }
    } catch (error) {
      console.error("Debug: Error setting up save hook:", error)
    }
  }

  firstVisiblePanelId() {
    return this.state.customPanels[0]?.id || null
  }

  async saveChanges() {
    try {
      if (!this.state.isDirty) {
        console.log("No changes to save");
        return;
      }

      // Strip transient/display-only fields before persisting.
      // annotated_image_url is a computed display URL (not stored); annotated_image is the
      // base64 blob that the backend will convert to an ir.attachment.
      // originalImage/originalImage2 are in-memory caches only.
      const cleanPanels = {}
      for (const [panelId, panel] of Object.entries(this.state.panels)) {
        const { originalImage, originalImage2, annotated_image_url, ...rest } = panel
        cleanPanels[panelId] = rest
      }
      const fieldData = {
        ...cleanPanels,
        customPanels: this.state.customPanels,
        unit: this.state.unit,
        status: this.state.status,
      }

      console.log("Saving measurement data to database:", fieldData)

      if (this.props.record && this.props.name) {
        // Update the in-memory record model so Odoo's own save (originalSave, called
        // immediately after this) writes the correct data.  Using orm.write() here
        // was wrong: originalSave() would then overwrite the DB with the stale
        // props.record.data value, causing data loss after tab switches.
        await this.props.record.update({ [this.props.name]: fieldData })
      }

      this.state.isDirty = false
      console.log("Measurement data saved successfully")
    } catch (error) {
      console.error("Error saving measurement data:", error)
      this.notification.add("Error saving measurement data", { type: "danger" })
    }
  }


  refreshPanelData() {
    // IMPORTANT: Read from the COMPUTED field (_with_images) for display data with image URLs
    // The computed field has image URLs restored from attachments by the backend
    const computedFieldName = 'measurement_widget_data_with_images';
    const rawValue = this.props.record?.data?.[computedFieldName];

    console.log("refreshPanelData reading from computed field:", computedFieldName);
    console.log("rawValue =", rawValue);

    if (!rawValue) {
      console.log("No computed field data available");
      return;
    }

    let parsedValue;
    try {
      parsedValue = typeof rawValue === "string" ? JSON.parse(rawValue) : rawValue;
    } catch (e) {
      console.error("Error parsing computed field:", e);
      parsedValue = null;
    }

    if (!parsedValue) {
      console.log("Failed to parse computed field data");
      return;
    }

    console.log("Successfully parsed computed field data");

    const _refreshPanel = (panelKey, src) => {
      if (this.state.panels[panelKey]) {
        this.state.panels[panelKey].measurements = src.measurements || [];
        this.state.panels[panelKey].image = src.image || null;
        this.state.panels[panelKey].image_attachment_id = src.image_attachment_id || null;
        this.state.panels[panelKey].image2 = src.image2 || null;
        this.state.panels[panelKey].image2_attachment_id = src.image2_attachment_id || null;
        this.state.panels[panelKey].annotated_image_url = src.annotated_image_url || null;
        this.state.panels[panelKey].annotated_image_attachment_id = src.annotated_image_attachment_id || null;
        this.state.panels[panelKey].panelRequests = src.panelRequests || [];
        this.state.panels[panelKey].pendingChanges = src.pendingChanges || {};
        this.state.panels[panelKey].hasPendingRequest = src.hasPendingRequest || (src.panelRequests?.length > 0) || false;
        this.state.panels[panelKey].pendingBaseVersion = src.pendingBaseVersion !== undefined ? src.pendingBaseVersion
          : (src.panelRequests?.length > 0 ? Math.max(...src.panelRequests.map(r => r.version)) : 1);
      }
    }

    // Update all panels in customPanels list (covers both old core panels and new custom ones)
    const panels = parsedValue.customPanels || [];
    for (const cp of panels) {
      if (cp.id && parsedValue[cp.id] && this.state.panels[cp.id]) {
        _refreshPanel(cp.id, parsedValue[cp.id]);
      }
    }

    this.state.customPanels = panels;
    this.state.unit = parsedValue.unit || this.state.unit;
    this.state.status = parsedValue.status || this.state.status;

    // Re-select active panel using index [0] if current selection is gone
    if (!this.state.activePanel || !this.state.panels[this.state.activePanel]) {
      this.state.activePanel = this.state.customPanels[0]?.id || null;
    }

    console.log("Panel data refresh complete");
  }

  toggleStatus() {
    this.state.status = this.state.status === "ready" ? "draft" : "ready"
    this.notifyFormChange()
  }

  getStatusBadgeClass() {
    return this.state.status === "ready" ? "badge bg-success" : "badge bg-secondary"
  }
  toRounded(value) {
    const num = parseFloat(value);
    if (isNaN(num)) return "";
    return Number(num.toFixed(3));   // always two decimals
  }

  convertSnap(value, fromUnit, toUnit) {
    const num = parseFloat(value);
    if (!Number.isFinite(num)) return value;

    let converted = num;

    // Unit conversion
    if (fromUnit !== toUnit) {
      if (fromUnit === "inches" && toUnit === "cm") {
        converted = num * 2.54;
      } else if (fromUnit === "cm" && toUnit === "inches") {
        converted = num / 2.54;
      }
    }

    // Round after converting
    return Number(converted.toFixed(3));
  }


  convertAllMeasurements(toUnit) {
    const fromUnit = this.state.unit;
    if (fromUnit === toUnit) return;

    for (const key in this.state.panels) {
      const panel = this.state.panels[key];
      if (!panel?.measurements) continue;

      panel.measurements = panel.measurements.map((m) => ({
        ...m,
        value: m.value === "" ? "" : this.convertSnap(m.value, fromUnit, toUnit),
      }));
    }

    this.state.unit = toUnit;
  }


  formatValueToGrid(panelKey, index) {
    const panel = this.state.panels[panelKey];
    const m = panel?.measurements?.[index];
    if (!m) return;

    if (m.value === "" || m.value === null) {
      m.value = "";
      return;
    }

    m.value = this.toRounded(m.value);
  }


  toggleUnit() {
    const target = this.state.unit === "inches" ? "cm" : "inches"
    this.convertAllMeasurements(target)
    this.state.unit = target
    this.notifyFormChange()
  }

  getCurrentUnit() {
    return this.state.unit === "inches" ? "in" : "cm"
  }

  handleInputFocus(ev) {
    const row = ev.currentTarget.closest("tr")
    if (row) {
      row.classList.add("row-focused")
    }
  }

  handleInputBlur(ev) {
    const row = ev.currentTarget.closest("tr")
    if (row) {
      row.classList.remove("row-focused")
    }
  }

  // ── Panel Request (versioning) methods ──────────────────────────────────

  getConfirmedRequests(panelId) {
    const panel = this.state.panels[panelId]
    return panel?.panelRequests || []
  }

  // Compute absolute values at a specific version, respecting each request's baseVersion
  getValuesAtVersion(panelId, version) {
    const panel = this.state.panels[panelId]
    if (!panel) return {}
    const base = {}
    for (const m of panel.measurements || []) {
      base[m.point] = parseFloat(m.value) || 0
    }
    if (version <= 1) return base
    const req = (panel.panelRequests || []).find(r => r.version === version)
    if (!req) return base
    const baseVersion = req.baseVersion !== undefined ? req.baseVersion : version - 1
    const baseValues = this.getValuesAtVersion(panelId, baseVersion)
    const result = { ...baseValues }
    for (const [point, delta] of Object.entries(req.changes || {})) {
      if (result[point] !== undefined) {
        result[point] = parseFloat((result[point] + (parseFloat(delta) || 0)).toFixed(3))
      }
    }
    return result
  }

  getLatestVersionNumber(panelId) {
    const panel = this.state.panels[panelId]
    if (!panel?.panelRequests?.length) return 1
    return Math.max(...panel.panelRequests.map(r => r.version))
  }

  // "Last Request" = the version before the activeEditVersion, or base (v1)
  getLastRequestVersion(panelId) {
    const panel = this.state.panels[panelId]
    if (!panel) return 1
    const active = panel.activeEditVersion
    if (!active) return this.getLatestVersionNumber(panelId)
    // Find the request entry for activeEditVersion to get its baseVersion
    const activeReq = (panel.panelRequests || []).find(r => r.version === active)
    if (!activeReq) return 1
    return activeReq.baseVersion !== undefined ? activeReq.baseVersion : active - 1
  }

  // Absolute values of the "last request" column
  getLastRequestValues(panelId) {
    return this.getValuesAtVersion(panelId, this.getLastRequestVersion(panelId))
  }

  // Absolute values of the "new request" (active edit version)
  getNewRequestValues(panelId) {
    const panel = this.state.panels[panelId]
    if (!panel?.activeEditVersion) return {}
    return this.getValuesAtVersion(panelId, panel.activeEditVersion)
  }

  // Change for a single point = newReq - lastReq
  getChangeForPoint(panelId, point) {
    const lastVal = parseFloat(this.getLastRequestValues(panelId)[point]) || 0
    const newVal  = parseFloat(this.getNewRequestValues(panelId)[point]) || 0
    return parseFloat((newVal - lastVal).toFixed(3))
  }

  hasActiveRequest(panelId) {
    const panel = this.state.panels[panelId]
    return !!(panel?.activeEditVersion)
  }

  getActiveEditVersion(panelId) {
    return this.state.panels[panelId]?.activeEditVersion ?? null
  }

  // Create a new request version immediately — copies last request values (zero changes)
  createNewRequest(panelId) {
    const panel = this.state.panels[panelId]
    if (!panel) return
    const baseVersion = this.getLatestVersionNumber(panelId)
    const nextVersion = baseVersion + 1
    if (!panel.panelRequests) panel.panelRequests = []
    panel.panelRequests.push({
      version: nextVersion,
      baseVersion,
      changes: {},  // zero changes = copy of last request
    })
    panel.activeEditVersion = nextVersion
    this.notifyFormChange()
  }

  // Set the new request value for a point (stored as delta from its baseVersion)
  setNewRequestValue(panelId, point, newAbsoluteValue) {
    const panel = this.state.panels[panelId]
    if (!panel?.activeEditVersion) return
    const req = (panel.panelRequests || []).find(r => r.version === panel.activeEditVersion)
    if (!req) return
    const baseValues = this.getValuesAtVersion(panelId, req.baseVersion !== undefined ? req.baseVersion : panel.activeEditVersion - 1)
    const base = parseFloat(baseValues[point]) || 0
    const newVal = parseFloat(newAbsoluteValue) || 0
    const delta = parseFloat((newVal - base).toFixed(3))
    if (!req.changes) req.changes = {}
    req.changes[point] = delta
    this.notifyFormChange()
  }

  deleteLatestRequest(panelId) {
    const panel = this.state.panels[panelId]
    if (!panel) return
    const latest = this.getLatestVersionNumber(panelId)
    if (latest <= 1) return
    this.dialogService.add(ConfirmationDialog, {
      title: `Delete Request ${latest}`,
      body: `Delete Request ${latest}? This cannot be undone.`,
      confirm: () => {
        panel.panelRequests = (panel.panelRequests || []).filter(r => r.version !== latest)
        const newLatest = panel.panelRequests.length
          ? Math.max(...panel.panelRequests.map(r => r.version))
          : null
        panel.activeEditVersion = newLatest
        this.notifyFormChange()
      },
    })
  }

  // ── Legacy stubs — kept so old template refs don't crash during transition ──

  // eslint-disable-next-line no-unused-vars
  getPanelHasPendingRequest(_panelId) { return false }
  // eslint-disable-next-line no-unused-vars
  getPendingChangeDisplay(_panelId, _point) { return '' }
  // eslint-disable-next-line no-unused-vars
  getPendingTotal(_panelId, _point) { return 0 }
  getNextRequestVersion(panelId) { return this.getLatestVersionNumber(panelId) + 1 }
  // eslint-disable-next-line no-unused-vars
  getAvailableBaseVersions(_panelId) { return [] }
  // eslint-disable-next-line no-unused-vars
  getPendingBaseVersion(_panelId) { return 1 }
  // eslint-disable-next-line no-unused-vars
  setPendingBaseVersion(_panelId, _version) {}
  // eslint-disable-next-line no-unused-vars
  setPendingChange(_panelId, _point, _val) {}

  // ── Toile Actual helpers ─────────────────────────────────────────────────

  getActualVersionsForPanel(panelId) {
    return this.state.toileDocData?.[panelId]?.actualVersions || []
  }

  panelHasActuals(panelId) {
    return this.getActualVersionsForPanel(panelId).length > 0
  }

  getSelectedActualVersion(panelId) {
    const explicit = this.state.selectedActualVersions[panelId]
    if (explicit !== undefined && explicit !== null) return explicit
    const stored = this.state.toileDocData?.[panelId]?.selectedVersion
    if (stored !== undefined && stored !== null) return stored
    const versions = this.getActualVersionsForPanel(panelId)
    return versions.length ? versions[versions.length - 1].version : null
  }

  setSelectedActualVersion(panelId, version) {
    this.state.selectedActualVersions[panelId] = parseInt(version)
  }

  getActualValue(panelId, point) {
    const ver = this.getSelectedActualVersion(panelId)
    if (ver === null || ver === undefined) return "—"
    const found = this.getActualVersionsForPanel(panelId).find(v => v.version === ver)
    if (!found) return "—"
    const val = found.measurements?.[point]
    if (val === null || val === undefined || val === "") return "—"
    return parseFloat(val).toFixed(3)
  }

  cancelPendingRequest(panelId) {
    const panel = this.state.panels[panelId]
    if (!panel) return
    const hasConfirmed = panel.panelRequests?.length > 0
    this.dialogService.add(ConfirmationDialog, {
      title: 'Cancel Request',
      body: hasConfirmed
        ? 'Discard pending changes? Confirmed requests will be kept.'
        : 'Cancel this request? All pending changes will be discarded.',
      confirm: () => {
        panel.pendingChanges = {}
        if (!hasConfirmed) {
          panel.hasPendingRequest = false
        } else {
          panel.pendingBaseVersion = this.getLatestVersionNumber(panelId)
        }
        this.notifyFormChange()
      },
    })
  }

  deleteConfirmedRequest(panelId, version) {
    this.dialogService.add(ConfirmationDialog, {
      title: `Delete Request ${version}`,
      body: `Delete Request ${version}? This cannot be undone.`,
      confirm: () => {
        const panel = this.state.panels[panelId]
        if (!panel) return
        panel.panelRequests = (panel.panelRequests || []).filter(r => r.version !== version)
        if (panel.panelRequests.length === 0) {
          panel.hasPendingRequest = false
          panel.pendingChanges = {}
          panel.pendingBaseVersion = 1
        } else {
          panel.pendingBaseVersion = Math.max(...panel.panelRequests.map(r => r.version))
        }
        this.notifyFormChange()
      },
    })
  }
}

registry.category("fields").add("measurement_sheet_widget", {
  component: MeasurementSheetWidget,
  supportedTypes: ["json", "text", "char"], // match your field type
})

export default MeasurementSheetWidget
