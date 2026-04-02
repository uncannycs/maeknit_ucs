"use client"

/** @odoo-module **/

import { Component, useState } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { registry } from "@web/core/registry"
import { standardFieldProps } from "@web/views/fields/standard_field_props"

export class LinkingDialWidget extends Component {
  static template = "maeknit_bom_mfg_link.LinkingDialWidget"
  static props = {
    ...standardFieldProps,
  }

  setup() {
    this.state = useState({
      measurements: [],
      unit: "inches",
      isDirty: false,
    })

    this.orm = useService("orm")
    this.notification = useService("notification")

    const rawValue = this.props.record?.data?.[this.props.name]
    let parsedValue = null

    if (rawValue) {
      if (typeof rawValue === "string" && rawValue.trim() !== "") {
        try {
          parsedValue = JSON.parse(rawValue)
        } catch (e) {
          console.error("Error parsing linking_dial_measurements:", e)
        }
      } else if (typeof rawValue === "object" && rawValue !== null) {
        parsedValue = rawValue
      }
    }

    if (parsedValue && typeof parsedValue === "object") {
      this.state.measurements = parsedValue.measurements || this.getDefaultMeasurements()
      this.state.unit = parsedValue.unit || "inches"
    } else {
      this.state.measurements = this.getDefaultMeasurements()
      this.state.unit = "inches"
    }

    // Bind methods
    this.onUnitChange = this.onUnitChange.bind(this)
    this.onMeasurementChange = this.onMeasurementChange.bind(this)
    this.onLabelChange = this.onLabelChange.bind(this)
    this.addMeasurement = this.addMeasurement.bind(this)
    this.removeMeasurement = this.removeMeasurement.bind(this)
    this.notifyFormChange = this.notifyFormChange.bind(this)
    this.saveChanges = this.saveChanges.bind(this)
    this.setupSaveHook = this.setupSaveHook.bind(this)

    this.setupSaveHook()
  }

  getDefaultMeasurements() {
    return [
      { label: "Shoulder", value: "" },
      { label: "Neck hole", value: "" },
      { label: "Sleeve cuff", value: "" },
      { label: "Arm hole", value: "" },
      { label: "Side seam", value: "" },
      { label: "Bottom cuff", value: "" },
    ]
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
        measurements: this.state.measurements,
        unit: this.state.unit,
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
      console.error("Error saving linking dial measurements:", error)
      this.notification.add("Error saving linking dial measurements", {
        type: "danger",
      })
    }
  }

  onUnitChange(unit) {
    this.state.unit = unit
    this.notifyFormChange()
  }

  onMeasurementChange(index, value) {
    this.state.measurements[index].value = value
    this.notifyFormChange()
  }

  onLabelChange(index, label) {
    this.state.measurements[index].label = label
    this.notifyFormChange()
  }

  addMeasurement() {
    this.state.measurements.push({ label: "", value: "" })
    this.notifyFormChange()
  }

  removeMeasurement(index) {
    this.state.measurements.splice(index, 1)
    this.notifyFormChange()
  }
}

registry.category("fields").add("linking_dial_widget", {
  component: LinkingDialWidget,
  supportedTypes: ["json", "text", "char"],
})

export default LinkingDialWidget
