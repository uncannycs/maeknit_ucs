"use client"

/** @odoo-module **/

import { Component, useState } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { registry } from "@web/core/registry"
import { standardFieldProps } from "@web/views/fields/standard_field_props"

export class GarmentDocWidget extends Component {
  static template = "maeknit_bom_mfg_link.GarmentDocWidget"
  static props = {
    ...standardFieldProps,
  }

  setup() {
    // All hooks must be called at the top level
    this.orm = useService("orm")
    this.notification = useService("notification")

    this.state = useState({
      unit: "inches", // "inches" or "cm"
      np_settings: [{ np1: "", np2: "" }],
      wmf_settings: [{ wmf1: "", wmf2: "" }],
      takedown_measurements: {},
      panel_names: [],
      notes: "",
      isDirty: false,
      isLoaded: false,
      isSwatch: false,
    })

    // Bind methods
    this.toggleUnit = this.toggleUnit.bind(this)
    this.addNPRow = this.addNPRow.bind(this)
    this.removeNPRow = this.removeNPRow.bind(this)
    this.updateNPField = this.updateNPField.bind(this)
    this.addWMFRow = this.addWMFRow.bind(this)
    this.removeWMFRow = this.removeWMFRow.bind(this)
    this.updateWMFField = this.updateWMFField.bind(this)
    this.updateTakedownField = this.updateTakedownField.bind(this)
    this.updateNotes = this.updateNotes.bind(this)
    this.notifyFormChange = this.notifyFormChange.bind(this)
    this.saveChanges = this.saveChanges.bind(this)
    this.setupSaveHook = this.setupSaveHook.bind(this)
    this.loadPanelCADData = this.loadPanelCADData.bind(this)

    const productCategory = this.props.record?.data?.product_category
    this.state.isSwatch = productCategory === "swatch"

    // Load existing data into state with safe defaults
    const rawValue = this.props.record?.data?.[this.props.name]
    let parsedValue = null

    if (rawValue) {
      if (typeof rawValue === "string" && rawValue.trim() !== "") {
        try {
          parsedValue = JSON.parse(rawValue)
        } catch (e) {
          console.error("Error parsing garment_doc_data:", e)
        }
      } else if (typeof rawValue === "object" && rawValue !== null) {
        parsedValue = rawValue
      }
    }

    if (parsedValue && typeof parsedValue === "object") {
      this.state.unit = parsedValue.unit || "inches"

      if (parsedValue.np_settings && parsedValue.np_settings.length > 0) {
        this.state.np_settings = parsedValue.np_settings
      } else if (parsedValue.machine_settings && parsedValue.machine_settings.length > 0) {
        // Migrate old format
        this.state.np_settings = parsedValue.machine_settings.map((row) => ({
          np1: row.np1 || "",
          np2: row.np2 || "",
        }))
      }

      if (parsedValue.wmf_settings && parsedValue.wmf_settings.length > 0) {
        this.state.wmf_settings = parsedValue.wmf_settings
      } else if (parsedValue.machine_settings && parsedValue.machine_settings.length > 0) {
        // Migrate old format
        this.state.wmf_settings = parsedValue.machine_settings.map((row) => ({
          wmf1: row.wmf1 || "",
          wmf2: row.wmf2 || "",
        }))
      }

      this.state.takedown_measurements = parsedValue.takedown_measurements || {}
      this.state.panel_names = parsedValue.panel_names || []
      this.state.notes = parsedValue.notes || ""
    }

    // Load Panel CAD data on initialization
    this.loadPanelCADData()

    // Setup save hook
    this.setupSaveHook()
  }

  async loadPanelCADData() {
    try {
      const panelCADData = this.props.record?.data?.measurement_widget_data

      if (!panelCADData) {
        this.state.isLoaded = true
        return
      }

      let parsedPanelData = null
      if (typeof panelCADData === "string") {
        try {
          parsedPanelData = JSON.parse(panelCADData)
        } catch (e) {
          console.error("Error parsing Panel CAD data:", e)
          this.state.isLoaded = true
          return
        }
      } else if (typeof panelCADData === "object") {
        parsedPanelData = panelCADData
      }

      if (parsedPanelData) {
        const hiddenPanels = parsedPanelData.hiddenPanels || []

        const panelNames = []
        const takedownMeasurements = {}

        const standardPanels = ["front", "back", "sleeve", "collar"]

        standardPanels.forEach((panelKey) => {
          if (parsedPanelData[panelKey] && !hiddenPanels.includes(panelKey)) {
            const panelData = parsedPanelData[panelKey]

            panelNames.push({
              key: panelKey,
              name: panelData.name || panelKey.charAt(0).toUpperCase() + panelKey.slice(1),
            })

            if (!this.state.takedown_measurements[panelKey]) {
              takedownMeasurements[panelKey] = { height: "", width: "" }
            } else {
              takedownMeasurements[panelKey] = this.state.takedown_measurements[panelKey]
            }

            if (panelData.measurements && Array.isArray(panelData.measurements)) {
              panelData.measurements.forEach((measurement) => {
                const name = (measurement.name || "").toLowerCase()
                const value = measurement.value || ""

                if (name.includes("width") && !takedownMeasurements[panelKey].width) {
                  takedownMeasurements[panelKey].width = value
                }
                if (name.includes("height") && !takedownMeasurements[panelKey].height) {
                  takedownMeasurements[panelKey].height = value
                }
              })
            }
          }
        })

        if (parsedPanelData.customPanels && Array.isArray(parsedPanelData.customPanels)) {
          parsedPanelData.customPanels.forEach((customPanel) => {
            const panelKey = customPanel.id || customPanel.name?.toLowerCase().replace(/\s+/g, "_")

            if (panelKey && parsedPanelData[panelKey] && !hiddenPanels.includes(panelKey)) {
              const panelData = parsedPanelData[panelKey]

              panelNames.push({
                key: panelKey,
                name: panelData.name || customPanel.name,
              })

              if (!this.state.takedown_measurements[panelKey]) {
                takedownMeasurements[panelKey] = { height: "", width: "" }
              } else {
                takedownMeasurements[panelKey] = this.state.takedown_measurements[panelKey]
              }

              if (panelData.measurements && Array.isArray(panelData.measurements)) {
                panelData.measurements.forEach((measurement) => {
                  const name = (measurement.name || "").toLowerCase()
                  const value = measurement.value || ""

                  if (name.includes("width") && !takedownMeasurements[panelKey].width) {
                    takedownMeasurements[panelKey].width = value
                  }
                  if (name.includes("height") && !takedownMeasurements[panelKey].height) {
                    takedownMeasurements[panelKey].height = value
                  }
                })
              }
            }
          })
        }

        this.state.panel_names = panelNames
        this.state.takedown_measurements = takedownMeasurements
      }

      this.state.isLoaded = true
    } catch (error) {
      console.error("Error loading Panel CAD data:", error)
      this.state.isLoaded = true
    }
  }

  toggleUnit() {
    this.state.unit = this.state.unit === "inches" ? "cm" : "inches"
    this.notifyFormChange()
  }

  addNPRow() {
    this.state.np_settings.push({ np1: "", np2: "" })
    this.notifyFormChange()
  }

  removeNPRow(index) {
    if (this.state.np_settings.length > 1) {
      this.state.np_settings.splice(index, 1)
      this.notifyFormChange()
    }
  }

  updateNPField(index, field, value) {
    if (this.state.np_settings[index]) {
      this.state.np_settings[index][field] = value
      this.notifyFormChange()
    }
  }

  addWMFRow() {
    this.state.wmf_settings.push({ wmf1: "", wmf2: "" })
    this.notifyFormChange()
  }

  removeWMFRow(index) {
    if (this.state.wmf_settings.length > 1) {
      this.state.wmf_settings.splice(index, 1)
      this.notifyFormChange()
    }
  }

  updateWMFField(index, field, value) {
    if (this.state.wmf_settings[index]) {
      this.state.wmf_settings[index][field] = value
      this.notifyFormChange()
    }
  }

  updateTakedownField(panel, field, value) {
    if (!this.state.takedown_measurements[panel]) {
      this.state.takedown_measurements[panel] = { height: "", width: "" }
    }
    this.state.takedown_measurements[panel][field] = value
    this.notifyFormChange()
  }

  updateNotes(value) {
    this.state.notes = value
    this.notifyFormChange()
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
        unit: this.state.unit,
        np_settings: this.state.np_settings,
        wmf_settings: this.state.wmf_settings,
        takedown_measurements: this.state.takedown_measurements,
        panel_names: this.state.panel_names,
        notes: this.state.notes,
      }

      if (this.props.record && this.props.name && this.props.record.resId) {
        await this.orm.write(this.props.record.resModel, [this.props.record.resId], {
          [this.props.name]: fieldData,
        })

        this.props.record.data[this.props.name] = JSON.stringify(fieldData)

        if (this.props.update) {
          this.props.update(JSON.stringify(fieldData))
        }
      }

      this.state.isDirty = false
    } catch (error) {
      console.error("Error saving garment doc data:", error)
      this.notification.add("Error saving garment documentation", {
        type: "danger",
      })
    }
  }
}

registry.category("fields").add("garment_doc_widget", {
  component: GarmentDocWidget,
  supportedTypes: ["json", "text", "char"],
})

export default GarmentDocWidget
