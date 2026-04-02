/** @odoo-module **/

import { FormDataManager } from "../utils/form_data_manager"
import { sanitizeDecimalInput } from "../utils/helpers"

export class SwatchingTabManager {
  constructor(orm, state) {
    this.orm = orm
    this.state = state
  }

  getSwatchItems() {
    if (!this.state.formData.swatchData || !this.state.formData.swatchData.items) {
      return []
    }
    return this.state.formData.swatchData.items
  }

  async addSwatchItem() {
    if (!this.state.formData.swatchData) {
      this.state.formData.swatchData = FormDataManager.getInitialFormData().swatchData
    }
    const sd = this.state.formData.swatchData
    const swatchNumber = sd.nextSwatchNumber
    const styleCode = await this.orm.call("crm.lead", "get_next_swatch_style_sequence", [])
  
    const newSwatch = {
      tempId: this.state.nextTempId--,
      name: `Swatch ${swatchNumber}`,
      styleCode,
    }
  
    sd.items.push(newSwatch)
    sd.nextSwatchNumber++
    sd.selectedItems = sd.selectedItems || []
    if (!sd.selectedItems.includes(newSwatch.tempId)) sd.selectedItems.push(newSwatch.tempId)  // <- select by default
    this.state.isDirty = true
  }

  removeSwatchItem(tempId) {
    if (!this.state.formData.swatchData || !this.state.formData.swatchData.items) {
      return
    }

    this.state.formData.swatchData.items = this.state.formData.swatchData.items.filter((item) => item.tempId !== tempId)

    this.state.formData.swatchData.selectedItems = this.state.formData.swatchData.selectedItems.filter(
      (id) => id !== tempId,
    )

    this.state.isDirty = true
  }

  onSwatchFieldChange(event, tempId, field) {
    if (!this.state.formData.swatchData || !this.state.formData.swatchData.items) {
      return
    }

    const swatch = this.state.formData.swatchData.items.find((item) => item.tempId === tempId)
    if (swatch) {
      swatch[field] = event.target.value
      this.state.isDirty = true
    }
  }

  isSwatchItemSelected(tempId) {
    if (!this.state.formData.swatchData || !this.state.formData.swatchData.selectedItems) {
      return false
    }
    return this.state.formData.swatchData.selectedItems.includes(tempId)
  }

  areAllSwatchesSelected() {
    const items = this.getSwatchItems()
    const selected = this.state.formData.swatchData?.selectedItems || []
    return items.length > 0 && items.every((item) => selected.includes(item.tempId))
  }

  onToggleSelectAllSwatches(event) {
    const shouldSelectAll = event.target.checked
    const items = this.getSwatchItems()

    if (!this.state.formData.swatchData) {
      this.state.formData.swatchData = FormDataManager.getInitialFormData().swatchData
    }

    if (shouldSelectAll) {
      this.state.formData.swatchData.selectedItems = items.map((item) => item.tempId)
    } else {
      this.state.formData.swatchData.selectedItems = []
    }

    this.state.isDirty = true
  }

  onSwatchItemSelect(event, tempId) {
    const isChecked = event.target.checked

    if (!this.state.formData.swatchData) {
      this.state.formData.swatchData = FormDataManager.getInitialFormData().swatchData
    }

    if (!this.state.formData.swatchData.selectedItems) {
      this.state.formData.swatchData.selectedItems = []
    }

    if (isChecked) {
      if (!this.state.formData.swatchData.selectedItems.includes(tempId)) {
        this.state.formData.swatchData.selectedItems.push(tempId)
      }
    } else {
      this.state.formData.swatchData.selectedItems = this.state.formData.swatchData.selectedItems.filter(
        (id) => id !== tempId,
      )
    }

    this.state.isDirty = true
  }

  _ensureSwatchData() {
    if (!this.state.formData.swatchData) {
      this.state.formData.swatchData = FormDataManager.getInitialFormData().swatchData
    }
    return this.state.formData.swatchData
  }

  getSwatchServicePrice() {
    const swatchData = this._ensureSwatchData()
    if (
      swatchData.servicePriceText === undefined ||
      swatchData.servicePriceText === null
    ) {
      const price =
        typeof swatchData.servicePrice === "number"
          ? swatchData.servicePrice
          : 0
      swatchData.servicePriceText = price.toFixed(2)
    }
    return swatchData.servicePriceText
  }

  onSwatchServicePriceInput(event) {
    const input = event.target
    const cursorStart = input.selectionStart
    const rawValue = input.value
    const sanitized = sanitizeDecimalInput(rawValue, 2)

    if (sanitized === "" && rawValue !== "") {
      return
    }

    // Calculate cursor offset based on characters removed
    const lengthDiff = rawValue.length - sanitized.length
    const newCursorPos = Math.max(0, cursorStart - lengthDiff)

    // Update input value directly
    input.value = sanitized

    // Restore cursor position
    input.setSelectionRange(newCursorPos, newCursorPos)

    // Update state
    const swatchData = this._ensureSwatchData()
    swatchData.servicePriceText = sanitized
    this.state.isDirty = true
  }

  onSwatchServicePriceCommit() {
    const swatchData = this._ensureSwatchData()
    const rawValue = swatchData.servicePriceText ?? ""
    let parsedValue = 0
    if (rawValue !== "" && rawValue !== ".") {
      const candidate = Number.parseFloat(rawValue)
      if (Number.isFinite(candidate)) {
        parsedValue = candidate
      }
    }
    swatchData.servicePrice = parsedValue
    swatchData.servicePriceText = parsedValue.toFixed(2)
    this.state.isDirty = true
  }
}
