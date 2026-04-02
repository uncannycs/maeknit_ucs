/** @odoo-module **/

import { FormDataManager } from "../utils/form_data_manager"
import { isServiceTypeSelected } from "../utils/helpers"

export class FormInputManager {
  constructor(state) {
    this.state = state
  }

  onInputChange(event) {
    const field = event.target.dataset.field
    if (field) {
      this.state.formData[field] = event.target.value
      this.state.isDirty = true
    }
  }

  onNumberChange(event) {
    const field = event.target.dataset.field
    if (field) {
      this.state.formData[field] = Number.parseFloat(event.target.value) || 0
      this.state.isDirty = true
    }
  }

  onPriorityChange(event) {
    this.state.formData.priority = event.target.value
    this.state.isDirty = true
  }

  onEmailChange(event) {
    // Email is read-only, so this is just a placeholder
    // The email is updated when the partner is selected
  }

  onProjectTypeChange(event) {
    this.state.formData.x_project_type = event.target.value
    this.state.isDirty = true

    if (this.state.formData.x_project_type === "collection") {
      this.state.formData.parent_id = false
      this.state.searchState.parentLeadSearch = ""
      this.state.formData.activeTab = "children"
    } else {
      this.state.formData.activeTab = "onboarding"
    }
  }

  onIncludeInQuoteChange(event, serviceType) {
    this.state.formData.x_include_development_in_quote = false
    this.state.formData.x_include_production_in_quote = false
    this.state.formData.x_include_swatch_in_quote = false
    this.state.formData.x_include_reverse_in_quote = false
    this.state.formData.x_include_grading_in_quote = false

    if (serviceType === "development") {
      this.state.formData.x_include_development_in_quote = true
    } else if (serviceType === "production") {
      this.state.formData.x_include_production_in_quote = true
    } else if (serviceType === "swatch") {
      this.state.formData.x_include_swatch_in_quote = true
    } else if (serviceType === "reverse") {
      this.state.formData.x_include_reverse_in_quote = true
    } else if (serviceType === "grading") {
      this.state.formData.x_include_grading_in_quote = true
    }

    this.state.isDirty = true
  }

  getServiceRevenue(tagId) {
    if (!this.state.formData.service_revenues) return 0
    return this.state.formData.service_revenues[tagId] || 0
  }

  onServiceRevenueChange(event, tagId) {
    const value = Number.parseFloat(event.target.value) || 0

    const serviceRevenues = { ...this.state.formData.service_revenues }
    serviceRevenues[tagId] = value

    this.state.formData.service_revenues = serviceRevenues
    this.state.formData.expected_revenue = Object.values(serviceRevenues).reduce((sum, val) => sum + val, 0)

    this.state.isDirty = true
  }

  isTagSelected(tagId) {
    if (!this.state.formData.tag_ids || !Array.isArray(this.state.formData.tag_ids)) {
      return false
    }

    return this.state.formData.tag_ids.some((tag) => {
      if (Array.isArray(tag) && tag.length > 0) {
        return tag[0] === tagId
      } else if (typeof tag === "number") {
        return tag === tagId
      }
      return false
    })
  }

  onTagChange(event, availableTags) {
    const tagId = Number.parseInt(event.target.dataset.tagId, 10)
    const isChecked = event.target.checked
    let currentTags = [...(this.state.formData.tag_ids || [])]

    if (isChecked) {
      if (!this.isTagSelected(tagId)) {
        const tagObj = availableTags.find((tag) => tag[0] === tagId)
        const tagName = tagObj ? tagObj[1] : `Tag ${tagId}`
        currentTags.push([tagId, tagName])

        const serviceRevenues = { ...this.state.formData.service_revenues }
        if (
          this.state.formData.hasExistingRevenue &&
          Object.values(serviceRevenues).every((value) => Number.parseFloat(value) === 0)
        ) {
          serviceRevenues[tagId] = this.state.formData.expected_revenue
          this.state.formData.hasExistingRevenue = false
        } else {
          serviceRevenues[tagId] = 0
        }
        this.state.formData.service_revenues = serviceRevenues
      }
    } else {
      currentTags = currentTags.filter((tag) => {
        if (Array.isArray(tag) && tag.length > 0) {
          return tag[0] !== tagId
        } else if (typeof tag === "number") {
          return tag !== tagId
        }
        return true
      })
      const tagObj = availableTags.find((tag) => tag[0] === tagId)
      const tagName = tagObj ? tagObj[1] : `Tag ${tagId}`

      if (tagName.includes("Swatch")) {
        this.state.formData.x_include_swatch_in_quote = false
      }
      if (tagName.includes("Production")) {
        this.state.formData.x_include_production_in_quote = false
      }
      if (tagName.includes("Development")) {
        this.state.formData.x_include_development_in_quote = false
      }
      if (tagName.includes("Reverse")) {
        this.state.formData.x_include_reverse_in_quote = false
      }
      if (tagName.includes("Grading")) {
        this.state.formData.x_include_grading_in_quote = false
      }

      const serviceRevenues = { ...this.state.formData.service_revenues }
      delete serviceRevenues[tagId]
      this.state.formData.service_revenues = serviceRevenues
    }

    this.state.formData.tag_ids = currentTags
    this.state.formData.expected_revenue = Object.values(this.state.formData.service_revenues).reduce(
      (sum, value) => sum + value,
      0,
    )
    this.state.isDirty = true
  }

  switchTab(tabName) {
    this.state.formData.activeTab = tabName
  }
  areAllServicesSelected() {
    if (!this.state.availableTags || this.state.availableTags.length === 0) {
      return false
    }

    return this.state.availableTags.every((tag) => this.isTagSelected(tag[0]))
  }

  onToggleSelectAllServices(event, availableTags) {
    const shouldSelectAll = event.target.checked

    if (shouldSelectAll) {
      // Select all services
      const allTags = availableTags.map((tag) => [tag[0], tag[1]])
      this.state.formData.tag_ids = allTags

      // Initialize service revenues for all tags
      const serviceRevenues = {}
      availableTags.forEach((tag) => {
        serviceRevenues[tag[0]] = 0
      })
      this.state.formData.service_revenues = serviceRevenues
    } else {
      // Deselect all services
      this.state.formData.tag_ids = []
      this.state.formData.service_revenues = {}

      // Reset all quote options
      this.state.formData.x_include_development_in_quote = false
      this.state.formData.x_include_production_in_quote = false
      this.state.formData.x_include_swatch_in_quote = false
      this.state.formData.x_include_reverse_in_quote = false
      this.state.formData.x_include_grading_in_quote = false
    }

    // Recalculate expected revenue
    this.state.formData.expected_revenue = Object.values(this.state.formData.service_revenues).reduce(
      (sum, value) => sum + value,
      0,
    )

    this.state.isDirty = true
  }
}
