/** @odoo-module **/

import { FormDataManager } from "../utils/form_data_manager"
import { sanitizeDecimalInput } from "../utils/helpers"

export class GradingTabManager {
  constructor(state) {
    this.state = state
  }

  _getOrCreateGradingDataForProduct(productId) {
    if (!this.state.formData.gradingData) {
      this.state.formData.gradingData = FormDataManager.getInitialFormData().gradingData
    }

    if (!this.state.formData.gradingData.items) {
      this.state.formData.gradingData.items = []
    }

    let gradingItem = this.state.formData.gradingData.items.find(
      (item) => item.id === productId || item.tempId === productId
    )

    if (!gradingItem) {
      const product = this.state.childOpportunitiesRows.find(
        (p) => p.id === productId || p.tempId === productId
      )

      if (product) {
        gradingItem = {
          id: product.id,
          tempId: product.tempId,
          name: product.name,
          styleCode: product.style_family,
          sizes: ["", ""],
          selected: false,
        }
        console.log("Adding new grading item:", gradingItem)
        this.state.formData.gradingData.items.push(gradingItem)
      }
    }

    return gradingItem
  }

  getGradingItems() {
    return this.state.formData.x_project_type === "collection"
      ? this.state.childOpportunitiesRows || []
      : []
  }

  getGradingSizes(productId) {
    const grading = this._getOrCreateGradingDataForProduct(productId)
    return grading ? grading.sizes : ["", ""]
  }

  addGradingSize(productId) {
    const grading = this._getOrCreateGradingDataForProduct(productId)
    if (grading) {
      grading.sizes.push("")
      this.state.isDirty = true
    }
  }

  removeGradingSize(productId, sizeIndex) {
    const grading = this._getOrCreateGradingDataForProduct(productId)
    if (grading && grading.sizes.length > 1) {
      grading.sizes.splice(sizeIndex, 1)
      this.state.isDirty = true
    }
  }

  onGradingSizeChange(event, productId, sizeIndex) {
    const grading = this._getOrCreateGradingDataForProduct(productId)
    if (grading && grading.sizes[sizeIndex] !== undefined) {
      const userInput = event.target.value
      grading.sizes[sizeIndex] = userInput.toUpperCase()  
      this.state.isDirty = true
    }
  }

  isGradingItemSelected(productId) {
    const selected = this.state.formData.gradingData?.selectedItems || []
    console.log("Selected items: 81", selected)
    console.log("Selected gradingData?.items: 82", this.state.formData.gradingData?.items || [])
    
    this.state.formData.gradingData.items.forEach((item) => {
      const id = item.tempId ?? item.id
      item.selected = this.state.formData.gradingData.selectedItems.includes(id)
    })

    console.log("Selected gradingData?.items: 89", this.state.formData.gradingData?.items || [])

    return selected.includes(productId)
  }

  onGradingItemSelect(event, productId) {
    const isChecked = event.target.checked
    const grading = this._getOrCreateGradingDataForProduct(productId)
    if (!grading) return

    if (!this.state.formData.gradingData.selectedItems) {
      this.state.formData.gradingData.selectedItems = []
    }

    const selected = this.state.formData.gradingData.selectedItems
    console.log("Selected items: 95", selected)
    if (isChecked && !selected.includes(productId)) {
      selected.push(productId)
      console.log("Added productId to selected items:", productId)
    } else if (!isChecked) {
      this.state.formData.gradingData.selectedItems = selected.filter((id) => id !== productId)
    }
    console.log("Updated selected items:", this.state.formData.gradingData.selectedItems)
    this.state.formData.gradingData.selectedItems = selected
    console.log("Final selected items:", this.state.formData.gradingData.selectedItems)
    this.state.isDirty = true
  }

  areAllGradesSelected() {
    const items = this.getGradingItems()
    const selected = this.state.formData.gradingData?.selectedItems || []
    return items.length > 0 && items.every((item) => selected.includes(item.id || item.tempId))
  }

  onToggleSelectAllGrades(event) {
    const shouldSelectAll = event.target.checked
    const items = this.getGradingItems()

    if (!this.state.formData.gradingData) {
      this.state.formData.gradingData = FormDataManager.getInitialFormData().gradingData
    }

    this.state.formData.gradingData.selectedItems = shouldSelectAll
      ? items.map((item) => item.id || item.tempId)
      : []

    this.state.isDirty = true
  }

  getGradingPricePerGrade() {
    if (!this.state.formData.gradingData) {
      this.state.formData.gradingData = FormDataManager.getInitialFormData().gradingData
    }

    // Return text value if it exists, otherwise format the numeric value
    if (this.state.formData.gradingData.pricePerGradeText !== undefined) {
      return this.state.formData.gradingData.pricePerGradeText
    }

    const numericPrice = this.state.formData.gradingData.pricePerGrade || 300
    return numericPrice.toFixed(2)
  }

  onGradingPricePerGradeInput(event) {
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
    if (!this.state.formData.gradingData) {
      this.state.formData.gradingData = FormDataManager.getInitialFormData().gradingData
    }

    this.state.formData.gradingData.pricePerGradeText = sanitized
    this.state.isDirty = true
  }

  onGradingPricePerGradeCommit() {
    if (!this.state.formData.gradingData) {
      this.state.formData.gradingData = FormDataManager.getInitialFormData().gradingData
    }

    const rawValue = this.state.formData.gradingData.pricePerGradeText ?? ""
    let parsedValue = 300
    if (rawValue !== "" && rawValue !== ".") {
      const candidate = Number.parseFloat(rawValue)
      if (Number.isFinite(candidate)) {
        parsedValue = candidate
      }
    }

    this.state.formData.gradingData.pricePerGrade = parsedValue
    this.state.formData.gradingData.pricePerGradeText = parsedValue.toFixed(2)
    this.state.isDirty = true
  }

  onGradingPricePerGradeChange(event) {
    const value = Number.parseFloat(event.target.value) || 0

    if (!this.state.formData.gradingData) {
      this.state.formData.gradingData = FormDataManager.getInitialFormData().gradingData
    }

    this.state.formData.gradingData.pricePerGrade = value
    this.state.isDirty = true
  }
}
