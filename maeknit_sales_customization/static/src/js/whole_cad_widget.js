"use client"

/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { registry } from "@web/core/registry"
import { standardFieldProps } from "@web/views/fields/standard_field_props"
import { Dialog } from "@web/core/dialog/dialog"
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog"

export class AddRowsDialog extends Component {
  static template = "whole_cad_widget.AddRowsDialog"
  static components = { Dialog }
  static props = {
    close: Function,
    onConfirm: Function,
    startIndex: Number,
    getPointLabel: Function,
  }

  setup() {
    this.state = useState({ count: 5 })
    this.countInput = useRef("countInput")
    onMounted(() => {
      if (this.countInput.el) {
        this.countInput.el.focus()
        this.countInput.el.select()
      }
    })
  }

  get startLabel() {
    if (!this.isValid) return ""
    return this.props.getPointLabel(this.props.startIndex)
  }

  get endLabel() {
    if (!this.isValid) return ""
    return this.props.getPointLabel(this.props.startIndex + this.state.count - 1)
  }

  get isValid() {
    const count = parseInt(this.state.count, 10)
    return isFinite(count) && count >= 1
  }

  onInput(ev) {
    this.state.count = parseInt(ev.target.value, 10) || 0
  }

  onKeydown(ev) {
    if (ev.key === "Enter" && this.isValid) this.onConfirm()
    if (ev.key === "Escape") this.props.close()
  }

  onConfirm() {
    if (!this.isValid) return
    this.props.onConfirm(parseInt(this.state.count, 10))
    this.props.close()
  }
}

export class WholeCadWidget extends Component {
  static template = "whole_cad_widget.WholeCadWidget"
  static props = {
    ...standardFieldProps,
  }

  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.dialogService = useService("dialog")

    this.letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    this.state = useState({
      viewMode: "single", // 'single' or 'compare'
      currentVersion: 1,
      compareVersionA: 1,
      compareVersionB: 2,
      maxVersion: 1,
      measurements: [],
      image: null,
      unit: "inches",
      isDirty: false,
      zoomLevel: 1.0,
    })

    this.dragState = {
      isDragging: false,
      startX: 0,
      startY: 0,
      scrollLeft: 0,
      scrollTop: 0,
      container: null,
    }

    // Load existing data
    const rawValue = this.props.record?.data?.[this.props.name]
    let parsedValue = null

    if (rawValue && typeof rawValue === "string") {
      try {
        parsedValue = JSON.parse(rawValue)
      } catch (e) {
        console.error("Error parsing whole CAD data:", e)
      }
    } else if (rawValue && typeof rawValue === "object") {
      parsedValue = rawValue
    }

    if (parsedValue) {
      console.log("Parsed whole CAD data:", parsedValue)
      console.log("Image value:", parsedValue.image ? `${parsedValue.image.substring(0, 50)}...` : "null")
      console.log("Image attachment ID:", parsedValue.image_attachment_id)
      this.state.maxVersion = parsedValue.max_version || 0
      console.log("Max version set to: " + this.state.maxVersion)
      this.state.currentVersion = this.state.maxVersion > 0 ? this.state.maxVersion : 0
      this.state.compareVersionA = Math.max(1, this.state.maxVersion - 1)
      this.state.compareVersionB = this.state.maxVersion
      this.state.measurements = parsedValue.measurements || []
      this.state.unit = parsedValue.unit || "inches"
      
      // Handle image - if it's a URL, fetch it
      const imageValue = parsedValue.image
      if (imageValue && typeof imageValue === 'string') {
        if (imageValue.startsWith('/maeknit/whole_cad/image/')) {
          // It's a URL - fetch the actual image data
          console.log("Fetching image from URL:", imageValue)
          this.state.image = null // Start with null while loading
          this.fetchImageFromUrl(imageValue)
        } else if (imageValue.startsWith('data:image')) {
          // It's already a data URL
          this.state.image = imageValue
        } else {
          this.state.image = null
        }
      } else {
        this.state.image = null
      }

      if (this.state.measurements.length < 2) {
        this.ensureMinRows()
      }

      // Ensure all measurements have version fields up to maxVersion
      this.state.measurements.forEach((m) => {
        for (let v = 1; v <= this.state.maxVersion; v++) {
          if (m[`v${v}`] === undefined) {
            m[`v${v}`] = ""
          }
        }
      })
    } else {
      this.state.maxVersion = 0
      this.seedMeasurements()
    }

    // Bind methods
    this.addMeasurement = this.addMeasurement.bind(this)
    this.addMultipleRows = this.addMultipleRows.bind(this)
    this.removeMeasurement = this.removeMeasurement.bind(this)
    this.updateMeasurement = this.updateMeasurement.bind(this)
    this.handleImageUpload = this.handleImageUpload.bind(this)
    this.triggerFileInput = this.triggerFileInput.bind(this)
    this.deleteImage = this.deleteImage.bind(this)
    this.notifyFormChange = this.notifyFormChange.bind(this)
    this.saveChanges = this.saveChanges.bind(this)
    this.toggleUnit = this.toggleUnit.bind(this)
    this.calculateDifference = this.calculateDifference.bind(this)
    this.isOutOfTolerance = this.isOutOfTolerance.bind(this)
    this.adjustZoom = this.adjustZoom.bind(this)
    this.resetZoom = this.resetZoom.bind(this)
    this.fitToContainer = this.fitToContainer.bind(this)
    this.handleWheel = this.handleWheel.bind(this)
    this.handleMouseDown = this.handleMouseDown.bind(this)
    this.handleMouseMove = this.handleMouseMove.bind(this)
    this.handleMouseUp = this.handleMouseUp.bind(this)
    this.handleDrop = this.handleDrop.bind(this)
    this.onVersionChange = this.onVersionChange.bind(this)
    this.switchViewMode = this.switchViewMode.bind(this)
    this.onCompareVersionAChange = this.onCompareVersionAChange.bind(this)
    this.onCompareVersionBChange = this.onCompareVersionBChange.bind(this)
    this.calculateVersionDifference = this.calculateVersionDifference.bind(this)
    this.handleInputKeyDown = this.handleInputKeyDown.bind(this)
    this.handleInputFocus = this.handleInputFocus.bind(this)
    this.handleInputBlur = this.handleInputBlur.bind(this)
    this.downloadImage = this.downloadImage.bind(this)
    this.downloadCSV = this.downloadCSV.bind(this)

    this.setupSaveHook()
  }

  getVersionNumbers() {
    const versions = []
    for (let i = 1; i <= this.state.maxVersion; i++) {
      versions.push(i)
    }
    return versions
  }

  seedMeasurements() {
    const numRows = 2 // Default: A and B rows only
    this.state.measurements = []

    for (let i = 0; i < numRows; i++) {
      const measurement = {
        point: this.getPointLabel(i),
        name: "",
        tolerance: "",
        request: "",
      }

      for (let v = 1; v <= this.state.maxVersion; v++) {
        measurement[`v${v}`] = ""
      }

      this.state.measurements.push(measurement)
    }
  }

  ensureMinRows() {
    const currentLength = this.state.measurements.length
    const minRows = 2

    if (currentLength < minRows) {
      for (let i = currentLength; i < minRows; i++) {
        const measurement = {
          point: this.getPointLabel(i),
          name: "",
          tolerance: "",
          request: "",
        }

        for (let v = 1; v <= this.state.maxVersion; v++) {
          measurement[`v${v}`] = ""
        }

        this.state.measurements.push(measurement)
      }
    }

    this.resequencePoints()
  }

  getPointLabel(index) {
    // 0->A, 1->B, ... 25->Z, 26->A2, 27->B2, ... 51->Z2, 52->A3, ...
    const cycle = Math.floor(index / 26)
    const letter = this.letters[index % 26]
    return cycle === 0 ? letter : letter + (cycle + 1)
  }

  getNextPoint() {
    const usedPoints = new Set(this.state.measurements.map((m) => m?.point || "").filter(Boolean))
    for (let i = 0; ; i++) {
      const label = this.getPointLabel(i)
      if (!usedPoints.has(label)) return label
    }
  }

  resequencePoints() {
    this.state.measurements.forEach((measurement, index) => {
      measurement.point = this.getPointLabel(index)
    })
  }

  addMeasurement() {
    const nextPoint = this.getNextPoint()
    const measurement = {
      point: nextPoint,
      name: "",
      tolerance: "",
      request: "",
    }
    // Add version fields
    for (let v = 1; v <= this.state.maxVersion; v++) {
      measurement[`v${v}`] = ""
    }
    this.state.measurements.push(measurement)
    this.notifyFormChange()
  }

  addMultipleRows() {
    const startIndex = this.state.measurements.length
    this.dialogService.add(AddRowsDialog, {
      startIndex,
      getPointLabel: (idx) => this.getPointLabel(idx),
      onConfirm: (count) => {
        const usedPoints = new Set(this.state.measurements.map((m) => m?.point || "").filter(Boolean))
        let added = 0
        for (let i = 0; added < count; i++) {
          const label = this.getPointLabel(i)
          if (usedPoints.has(label)) continue
          usedPoints.add(label)
          added++
          const measurement = {
            point: label,
            name: "",
            tolerance: "",
            request: "",
          }
          for (let v = 1; v <= this.state.maxVersion; v++) {
            measurement[`v${v}`] = ""
          }
          this.state.measurements.push(measurement)
        }
        this.notifyFormChange()
      },
    })
  }

  removeMeasurement(index) {
    if (index < 0 || index >= this.state.measurements.length) return
    const m = this.state.measurements[index]
    const label = m.point ? `point ${m.point}` : "this row"
    this.dialogService.add(ConfirmationDialog, {
      title: "Delete Row",
      body: `Are you sure you want to delete ${label}?`,
      confirm: () => {
        this.state.measurements.splice(index, 1)
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

  handleRowDrop(ev, targetIndex) {
    ev.preventDefault()
    const sourceIndex = this._dragSourceIndex
    this._dragSourceIndex = null
    if (sourceIndex === null || sourceIndex === undefined || sourceIndex === targetIndex) return

    const [removed] = this.state.measurements.splice(sourceIndex, 1)
    this.state.measurements.splice(targetIndex, 0, removed)
    this.notifyFormChange()
  }

  handleRowDragEnd() {
    this._dragSourceIndex = null
  }

  updateMeasurement(index, field, value) {
    if (!this.state.measurements[index]) return
    this.state.measurements[index][field] = value
    this.notifyFormChange()
  }

  handleInputKeyDown(index, field, ev) {
    if (ev.key !== "Enter") return
    ev.preventDefault()

    // Format value if it's a numeric field
    if (field !== "name" && field !== "point") {
      this.formatValue(index, field)
    }

    // Find all inputs in this column
    const table = ev.currentTarget.closest("table")
    const columnInputs = Array.from(table.querySelectorAll(`tbody input[data-field="${field}"]`))

    if (columnInputs.length === 0) {
      this.props.record?.save?.()
      return
    }

    const currentPos = columnInputs.indexOf(ev.currentTarget)

    // Move to next row in same column
    if (currentPos > -1 && currentPos < columnInputs.length - 1) {
      const nextInput = columnInputs[currentPos + 1]
      nextInput?.focus()
      nextInput?.select()
      this.props.record?.save?.()
      return
    }

    // Last row → save
    this.props.record?.save?.()
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


  formatValue(index, field) {
    const m = this.state.measurements[index]
    if (!m || m[field] === "" || m[field] === null) return
    m[field] = this.convertSnap(m[field], this.state.unit, this.state.unit)
  }

  calculateDifference(request, vValue) {
    const req = Number.parseFloat(request)
    const vVal = Number.parseFloat(vValue)
    if (!isFinite(req) || !isFinite(vVal)) return ""
    const diff = vVal - req
    return diff.toFixed(3)
  }

  calculateVersionDifference(vValueA, vValueB) {
    const vA = Number.parseFloat(vValueA)
    const vB = Number.parseFloat(vValueB)
    if (!isFinite(vA) || !isFinite(vB)) return ""
    const diff = vB - vA
    return diff.toFixed(3)
  }

  isOutOfTolerance(request, vValue, tolerance) {
    const req = Number.parseFloat(request)
    const vVal = Number.parseFloat(vValue)
    const tol = Number.parseFloat(tolerance)

    if (!isFinite(req) || !isFinite(vVal) || !isFinite(tol)) return false

    const diff = Math.abs(vVal - req)
    return diff > tol
  }

  async fetchImageFromUrl(url) {
    try {
      console.log("Fetching whole CAD image from:", url)
      const response = await fetch(url)
      if (!response.ok) {
        console.error("Failed to fetch image:", response.status)
        return
      }
      
      const data = await response.json()
      if (data.dataURL) {
        console.log("Successfully loaded image from URL")
        this.state.image = data.dataURL
      } else {
        console.error("No dataURL in response")
      }
    } catch (error) {
      console.error("Error fetching whole CAD image:", error)
    }
  }

  getWholeCadData() {
    const rawValue = this.props.record?.data?.whole_cad_data
    if (!rawValue) {
      return null
    }
    if (typeof rawValue === "string") {
      try {
        return JSON.parse(rawValue)
      } catch (error) {
        console.error("Error parsing whole CAD data for download:", error)
        return null
      }
    }
    return rawValue
  }

  getWholeCadDownloadUrl() {
    const data = this.getWholeCadData()
    const attachmentId =
      data?.image_attachment_id || this.props.record?.data?.whole_cad_image_id
    if (attachmentId) {
      return `/web/content/${attachmentId}?download=1`
    }
    return this.state.image && this.state.image.startsWith("data:")
      ? this.state.image
      : null
  }

  downloadImage() {
    const data = this.getWholeCadData()
    const attachmentId = data?.image_attachment_id || this.props.record?.data?.whole_cad_image_id
    if (attachmentId) {
      const a = document.createElement('a')
      a.href = `/web/content/${attachmentId}?download=1`
      a.download = 'whole_cad_image'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      return
    }
    if (this.state.image && this.state.image.startsWith('data:')) {
      const a = document.createElement('a')
      a.href = this.state.image
      a.download = 'whole_cad_image'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }
  }

  downloadCSV() {
    const unit = this.state.unit
    const measurements = this.state.measurements
    let headers, rows

    if (this.state.maxVersion === 0) {
      headers = ['Point', 'Measurement Name', 'Tolerance', `Request (${unit})`]
      rows = measurements.map((m) => [
        m.point || '',
        m.name || '',
        m.tolerance || '',
        m.request || '',
      ])
    } else if (this.state.viewMode === 'single') {
      const v = this.state.currentVersion
      headers = ['Point', 'Measurement Name', 'Tolerance', `Request (${unit})`, `Actual:${v}`, '+/-']
      rows = measurements.map((m) => [
        m.point || '',
        m.name || '',
        m.tolerance || '',
        m.request || '',
        m[`v${v}`] || '',
        this.calculateDifference(m.request, m[`v${v}`]),
      ])
    } else {
      const a = this.state.compareVersionA
      const b = this.state.compareVersionB
      headers = ['Point', 'Measurement Name', 'Tolerance', `Request (${unit})`, `Actual:${a}`, `Actual:${b}`, `Diff(${b}-${a})`]
      rows = measurements.map((m) => [
        m.point || '',
        m.name || '',
        m.tolerance || '',
        m.request || '',
        m[`v${a}`] || '',
        m[`v${b}`] || '',
        this.calculateVersionDifference(m[`v${a}`], m[`v${b}`]),
      ])
    }

    const csv = [headers, ...rows]
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

  handleImageUpload(event) {
    const file = event.target.files[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      this.state.image = e.target.result
      this.notifyFormChange()
    }
    reader.readAsDataURL(file)
  }

  handleDrop(event) {
    event.preventDefault()
    event.stopPropagation()

    const files = event.dataTransfer.files
    if (files.length > 0) {
      const file = files[0]
      if (file.type.startsWith("image/")) {
        const reader = new FileReader()
        reader.onload = (e) => {
          this.state.image = e.target.result
          this.notifyFormChange()
        }
        reader.readAsDataURL(file)
      }
    }
  }

  deleteImage() {
    if (!confirm("Delete this image?")) return
    this.state.image = null
    this.state.isDirty = true
    this.saveChanges()
  }

  triggerFileInput() {
    const fileInput = this.__owl__.refs.fileInput
    if (fileInput) {
      fileInput.click()
    }
  }

  adjustZoom(delta) {
    const newZoom = Math.min(5, Math.max(0.5, this.state.zoomLevel + delta))
    this.state.zoomLevel = newZoom

    const wrapper = document.querySelector(".whole-cad-image-wrapper")
    if (wrapper) {
      wrapper.style.transform = `scale(${newZoom})`
    }
  }

  resetZoom() {
    this.state.zoomLevel = 1.0
    const wrapper = document.querySelector(".whole-cad-image-wrapper")
    const container = document.querySelector(".whole-cad-zoom-container")

    if (wrapper) {
      wrapper.style.transform = "scale(1)"
      wrapper.style.left = "0px"
      wrapper.style.top = "0px"
    }

    if (container) {
      container.scrollTop = 0
      container.scrollLeft = 0
    }
  }

  fitToContainer() {
    this.state.zoomLevel = 1.0
    const wrapper = document.querySelector(".whole-cad-image-wrapper")
    const container = document.querySelector(".whole-cad-zoom-container")

    if (wrapper) {
      wrapper.style.transform = "scale(1)"
      wrapper.style.left = "0px"
      wrapper.style.top = "0px"
    }

    if (container) {
      container.scrollTop = 0
      container.scrollLeft = 0
    }
  }

  handleWheel(event) {
    event.preventDefault()
    const delta = event.deltaY < 0 ? 0.1 : -0.1
    this.adjustZoom(delta)
  }

  handleMouseDown(event) {
    if (event.button !== 0) return

    const wrapper = document.querySelector(".whole-cad-image-wrapper")
    if (!wrapper) return

    this.dragState.isDragging = true
    this.dragState.startX = event.clientX
    this.dragState.startY = event.clientY

    const currentLeft = Number.parseFloat(wrapper.style.left || "0")
    const currentTop = Number.parseFloat(wrapper.style.top || "0")

    this.dragState.scrollLeft = currentLeft
    this.dragState.scrollTop = currentTop

    document.addEventListener("mousemove", this.handleMouseMove)
    document.addEventListener("mouseup", this.handleMouseUp)
    event.preventDefault()
  }

  handleMouseMove(event) {
    if (!this.dragState.isDragging) return
    event.preventDefault()

    const wrapper = document.querySelector(".whole-cad-image-wrapper")
    if (!wrapper) return

    const deltaX = event.clientX - this.dragState.startX
    const deltaY = event.clientY - this.dragState.startY

    const newLeft = this.dragState.scrollLeft + deltaX
    const newTop = this.dragState.scrollTop + deltaY

    wrapper.style.left = `${newLeft}px`
    wrapper.style.top = `${newTop}px`
  }

  handleMouseUp() {
    if (!this.dragState.isDragging) return
    this.dragState.isDragging = false
    document.removeEventListener("mousemove", this.handleMouseMove)
    document.removeEventListener("mouseup", this.handleMouseUp)
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

  notifyFormChange() {
    try {
      if (this.props.record && this.props.record.model) {
        if (this.props.record.model.root) {
          this.props.record.model.root.dirty = true
        }
      }

      const statusIndicator = document.querySelector(".o_form_status_indicator_buttons")
      if (statusIndicator && statusIndicator.classList.contains("invisible")) {
        statusIndicator.classList.remove("invisible")
      }

      const saveButton = document.querySelector(".o_form_button_save")
      if (saveButton && saveButton.hasAttribute("disabled")) {
        saveButton.removeAttribute("disabled")
      }

      this.state.isDirty = true
    } catch (error) {
      console.error("Error notifying form change:", error)
    }
  }

  setupSaveHook() {
    try {
      if (this.props.record && this.props.record.save) {
        const originalSave = this.props.record.save.bind(this.props.record)

        this.props.record.save = async (...args) => {
          if (this.state.isDirty) {
            await this.saveChanges()
          }
          const result = await originalSave(...args)
          this.state.isDirty = false
          return result
        }
      }
    } catch (error) {
      console.error("Error setting up save hook:", error)
    }
  }

  async saveChanges() {
    try {
      if (!this.state.isDirty) return

      const fieldData = {
        max_version: this.state.maxVersion,
        measurements: this.state.measurements,
        image: this.state.image,
        unit: this.state.unit,
      }

      if (this.props.record && this.props.name && this.props.record.resId) {
        const fieldMapping = {
          whole_cad_data_with_images: 'whole_cad_data',
          cad_pom_data_with_images: 'cad_pom_data',
        }
        const saveFieldName = fieldMapping[this.props.name] || this.props.name

        await this.orm.write(this.props.record.resModel, [this.props.record.resId], {
          [saveFieldName]: fieldData,
        })

        // Update both fields in the record data so the UI reflects the saved data
        this.props.record.data[saveFieldName] = JSON.stringify(fieldData)
        if (this.props.name !== saveFieldName) {
          this.props.record.data[this.props.name] = JSON.stringify(fieldData)
        }

        if (this.props.update) {
          this.props.update(JSON.stringify(fieldData))
        }
      }

      this.state.isDirty = false
    } catch (error) {
      console.error("Error saving whole CAD data:", error)
      this.notification.add("Error saving whole CAD data", {
        type: "danger",
      })
    }
  }

  onVersionChange(event) {
    const newVersion = Number.parseInt(event.target.value, 10)
    if (newVersion >= 1 && newVersion <= this.state.maxVersion) {
      this.state.currentVersion = newVersion
    }
  }

  switchViewMode(mode) {
    this.state.viewMode = mode
  }

  onCompareVersionAChange(event) {
    const newVersion = Number.parseInt(event.target.value, 10)
    if (newVersion >= 1 && newVersion <= this.state.maxVersion) {
      this.state.compareVersionA = newVersion
    }
  }

  onCompareVersionBChange(event) {
    const newVersion = Number.parseInt(event.target.value, 10)
    if (newVersion >= 1 && newVersion <= this.state.maxVersion) {
      this.state.compareVersionB = newVersion
    }
  }

  getCurrentVersionKey() {
    return `v${this.state.currentVersion}`
  }

  getCurrentVersionDiff() {
    const vKey = this.getCurrentVersionKey()
    return this.state.measurements.map((m) => {
      return this.calculateDifference(m.request, m[vKey])
    })
  }

  toRounded(value, unit) {
    const num = parseFloat(value);
    if (isNaN(num)) return 0;
    return Number(num.toFixed(3));
  }
  
  
/*
  toRounded(value, unit) {
    const num = Number.parseFloat(value)
    return num;
    /*
    if (!isFinite(num)) return value

    if (unit === "inches") {
      // Round to nearest 0.25
      return Math.round(num / 0.25) * 0.25
    }

    if (unit === "cm") {
      // Round to nearest 0.5 (special handling)
      const base = Math.floor(num)
      const fraction = num - base

      let adj
      if (fraction < 0.25) adj = 0
      else if (fraction < 0.75) adj = 0.5
      else adj = 1

      return Number.parseFloat((base + adj).toFixed(1))
    }

    return value
    
  }
*/
  convertSnap(value, fromUnit, toUnit) {
    const num = parseFloat(value);
    if (!isFinite(num)) return value;
  
    let converted = num;
  
    // Convert only when unit changes
    if (fromUnit !== toUnit) {
      if (fromUnit === "inches" && toUnit === "cm") {
        converted = num * 2.54;
      } else if (fromUnit === "cm" && toUnit === "inches") {
        converted = num / 2.54;
      }
    }
  
    // Always keep 2 decimals
    return Number(converted.toFixed(3));
  }
  

  convertAllMeasurements(toUnit) {
    const fromUnit = this.state.unit
    if (fromUnit === toUnit) return

    this.state.measurements = this.state.measurements.map((m) => {
      const converted = { ...m }

      // Convert tolerance, request, and all version fields
      if (m.tolerance !== "" && m.tolerance !== null) {
        converted.tolerance = this.convertSnap(m.tolerance, fromUnit, toUnit)
      }
      if (m.request !== "" && m.request !== null) {
        converted.request = this.convertSnap(m.request, fromUnit, toUnit)
      }

      // Convert all version fields (v1, v2, v3, etc.)
      for (let v = 1; v <= this.state.maxVersion; v++) {
        const vKey = `v${v}`
        if (m[vKey] !== "" && m[vKey] !== null) {
          converted[vKey] = this.convertSnap(m[vKey], fromUnit, toUnit)
        }
      }

      return converted
    })

    this.state.unit = toUnit
  }
}

registry.category("fields").add("whole_cad_widget", {
  component: WholeCadWidget,
  supportedTypes: ["json", "text", "char"],
})

export default WholeCadWidget
