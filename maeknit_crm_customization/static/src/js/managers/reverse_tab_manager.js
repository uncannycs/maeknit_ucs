/** @odoo-module **/

import { FormDataManager } from "../utils/form_data_manager"
import { sanitizeDecimalInput } from "../utils/helpers"

export class ReverseTabManager {
  constructor(state) {
    this.state = state
  }

  getReverseItems() {
    if (this.state.formData.x_project_type === "collection") {
      return this.state.childOpportunitiesRows || []
    }
    return []
  }

  isReverseItemSelected(itemId) {
    if (!this.state.formData.reverseData || !this.state.formData.reverseData.selectedItems) {
      return false
    }
    return this.state.formData.reverseData.selectedItems.includes(itemId)
  }

  areAllReverseItemsSelected() {
    const items = this.getReverseItems()
    const selected = this.state.formData.reverseData?.selectedItems || []
    return items.length > 0 && items.every((item) => selected.includes(item.id || item.tempId))
  }

  onToggleSelectAllReverseItems(event) {
    const shouldSelectAll = event.target.checked
    const items = this.getReverseItems()

    if (!this.state.formData.reverseData) {
      this.state.formData.reverseData = FormDataManager.getInitialFormData().reverseData
    }

    this.state.formData.reverseData.selectedItems = shouldSelectAll
      ? items.map((item) => item.id || item.tempId)
      : []

    this.state.isDirty = true
  }

  onReverseItemSelect(event, itemId) {
    const isChecked = event.target.checked

    if (!this.state.formData.reverseData) {
      this.state.formData.reverseData = FormDataManager.getInitialFormData().reverseData
    }

    if (!this.state.formData.reverseData.selectedItems) {
      this.state.formData.reverseData.selectedItems = []
    }

    if (isChecked) {
      if (!this.state.formData.reverseData.selectedItems.includes(itemId)) {
        this.state.formData.reverseData.selectedItems.push(itemId)
      }
    } else {
      this.state.formData.reverseData.selectedItems = this.state.formData.reverseData.selectedItems.filter(
        (id) => id !== itemId,
      )
    }

    this.state.isDirty = true
  }

  getReversePrice(itemId) {
    if (!this.state.formData.reverseData) {
      this.state.formData.reverseData = FormDataManager.getInitialFormData().reverseData
    }

    if (!this.state.formData.reverseData.itemPricesText) {
      this.state.formData.reverseData.itemPricesText = {}
    }

    // Return text value if it exists, otherwise format the numeric value
    if (this.state.formData.reverseData.itemPricesText[itemId] !== undefined) {
      return this.state.formData.reverseData.itemPricesText[itemId]
    }

    const numericPrice = this.state.formData.reverseData.itemPrices?.[itemId] || 0
    return numericPrice.toFixed(2)
  }

  onReversePriceInput(event, itemId) {
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
    if (!this.state.formData.reverseData) {
      this.state.formData.reverseData = FormDataManager.getInitialFormData().reverseData
    }

    if (!this.state.formData.reverseData.itemPricesText) {
      this.state.formData.reverseData.itemPricesText = {}
    }

    this.state.formData.reverseData.itemPricesText[itemId] = sanitized
    this.state.isDirty = true
  }

  onReversePriceCommit(itemId) {
    if (!this.state.formData.reverseData) {
      this.state.formData.reverseData = FormDataManager.getInitialFormData().reverseData
    }

    if (!this.state.formData.reverseData.itemPrices) {
      this.state.formData.reverseData.itemPrices = {}
    }

    if (!this.state.formData.reverseData.itemPricesText) {
      this.state.formData.reverseData.itemPricesText = {}
    }

    const rawValue = this.state.formData.reverseData.itemPricesText[itemId] ?? ""
    let parsedValue = 0
    if (rawValue !== "" && rawValue !== ".") {
      const candidate = Number.parseFloat(rawValue)
      if (Number.isFinite(candidate)) {
        parsedValue = candidate
      }
    }

    this.state.formData.reverseData.itemPrices[itemId] = parsedValue
    this.state.formData.reverseData.itemPricesText[itemId] = parsedValue.toFixed(2)
    this.state.isDirty = true
  }

  onReversePriceChange(event, itemId) {
    const value = Number.parseFloat(event.target.value) || 0

    if (!this.state.formData.reverseData) {
      this.state.formData.reverseData = FormDataManager.getInitialFormData().reverseData
    }

    if (!this.state.formData.reverseData.itemPrices) {
      this.state.formData.reverseData.itemPrices = {}
    }

    this.state.formData.reverseData.itemPrices[itemId] = value
    this.state.isDirty = true
  }
}
