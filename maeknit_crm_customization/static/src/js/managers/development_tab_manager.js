/** @odoo-module **/

import { FormDataManager } from "../utils/form_data_manager"
import { sanitizeDecimalInput } from "../utils/helpers"

export class DevelopmentTabManager {
  constructor(state) {
    this.state = state
  }

  getProductItems() {
    if (this.state.formData.x_project_type === "collection") {
      return this.state.childOpportunitiesRows || []
    }
    return []
  }  
  areAllDevItemsSelected() {
    const items = this.getProductItems()
    const selected = this.state.selectedChildLeads || []
    return (
      items.length > 0 &&
      items.every((item) => {
        const itemId = item.id !== undefined ? item.id : item.tempId
        return selected.includes(itemId)
      })
    )
  }
  
  onToggleSelectAllDevItems(event) {
    const shouldSelectAll = event.target.checked
    const items = this.getProductItems()
  
    if (!this.state.formData.developmentData) {
      this.state.formData.developmentData = FormDataManager.getInitialFormData().developmentData
    }
  
    const itemIds = items.map((item) => item.id !== undefined ? item.id : item.tempId)
  
    this.state.formData.developmentData.selectedItems = shouldSelectAll ? itemIds : []
    this.state.selectedChildLeads = shouldSelectAll ? itemIds : []
  
    this.state.isDirty = true
  }
  
  
  
  isDevelopmentItemSelected(itemId) {
    if (!this.state.formData.developmentData || !this.state.formData.developmentData.selectedItems) {
      return false
    }
    return this.state.formData.developmentData.selectedItems.includes(itemId)
  }

  onDevelopmentItemSelect(event, itemId) {
    const isChecked = event.target.checked
    if (!this.state.formData.developmentData) {
      this.state.formData.developmentData = FormDataManager.getInitialFormData().developmentData
    }

    if (!this.state.formData.developmentData.selectedItems) {
      this.state.formData.developmentData.selectedItems = []
    }

    if (isChecked) {
      if (!this.state.formData.developmentData.selectedItems.includes(itemId)) {
        this.state.formData.developmentData.selectedItems.push(itemId)
      }
      if (!this.state.selectedChildLeads.includes(itemId)) {
        this.state.selectedChildLeads.push(itemId)
      }
    } else {
      this.state.formData.developmentData.selectedItems = this.state.formData.developmentData.selectedItems.filter(
        (id) => id !== itemId,
      )
      this.state.selectedChildLeads = this.state.selectedChildLeads.filter((id) => id !== itemId)
    }

    this.state.isDirty = true
  }

  getDevelopmentPrice(itemId) {
    if (!this.state.formData.developmentData) {
      this.state.formData.developmentData = FormDataManager.getInitialFormData().developmentData
    }

    if (!this.state.formData.developmentData.itemPricesText) {
      this.state.formData.developmentData.itemPricesText = {}
    }

    // Return text value if it exists, otherwise format the numeric value
    if (this.state.formData.developmentData.itemPricesText[itemId] !== undefined) {
      return this.state.formData.developmentData.itemPricesText[itemId]
    }

    const numericPrice = this.state.formData.developmentData.itemPrices?.[itemId] || 0
    return numericPrice.toFixed(2)
  }

  onDevelopmentPriceInput(event, itemId) {
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
    if (!this.state.formData.developmentData) {
      this.state.formData.developmentData = FormDataManager.getInitialFormData().developmentData
    }

    if (!this.state.formData.developmentData.itemPricesText) {
      this.state.formData.developmentData.itemPricesText = {}
    }

    this.state.formData.developmentData.itemPricesText[itemId] = sanitized
    this.state.isDirty = true
  }

  onDevelopmentPriceCommit(itemId) {
    if (!this.state.formData.developmentData) {
      this.state.formData.developmentData = FormDataManager.getInitialFormData().developmentData
    }

    if (!this.state.formData.developmentData.itemPrices) {
      this.state.formData.developmentData.itemPrices = {}
    }

    if (!this.state.formData.developmentData.itemPricesText) {
      this.state.formData.developmentData.itemPricesText = {}
    }

    const rawValue = this.state.formData.developmentData.itemPricesText[itemId] ?? ""
    let parsedValue = 0
    if (rawValue !== "" && rawValue !== ".") {
      const candidate = Number.parseFloat(rawValue)
      if (Number.isFinite(candidate)) {
        parsedValue = candidate
      }
    }

    this.state.formData.developmentData.itemPrices[itemId] = parsedValue
    this.state.formData.developmentData.itemPricesText[itemId] = parsedValue.toFixed(2)
    this.state.isDirty = true
  }

  onDevelopmentPriceChange(event, itemId) {
    const value = Number.parseFloat(event.target.value) || 0

    if (!this.state.formData.developmentData) {
      this.state.formData.developmentData = FormDataManager.getInitialFormData().developmentData
    }

    if (!this.state.formData.developmentData.itemPrices) {
      this.state.formData.developmentData.itemPrices = {}
    }

    this.state.formData.developmentData.itemPrices[itemId] = value
    this.state.isDirty = true
  }
}
