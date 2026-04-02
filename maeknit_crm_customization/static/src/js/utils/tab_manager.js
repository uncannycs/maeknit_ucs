/** @odoo-module **/

// This file is now deprecated as its functions have been moved to managers.
// Keeping it here for reference if needed, but it's no longer imported by crm_lead_widget.js
// The functions are now directly in the relevant manager files.

export class TabManager {
  static getDefaultTab(projectType) {
    return projectType === "collection" ? "children" : "onboarding"
  }

  static getAvailableTabs(projectType) {
    const commonTabs = ["gemini"]

    if (projectType === "collection") {
      return ["children", "swatching", "development", "reverse", "grading", "production", ...commonTabs]
    } else {
      return ["onboarding", ...commonTabs]
    }
  }

  static isTabVisible(tabName, projectType) {
    const availableTabs = this.getAvailableTabs(projectType)
    return availableTabs.includes(tabName)
  }

  onGeneralFieldChange(event, field, state) {
    const value = event.target.value
    state.formData.onboardingData.general[field] = value
    state.isDirty = true
  }

  onArrayFieldChange(event, field, index, state) {
    const value = event.target.value
    state.formData.onboardingData.general[field][index] = value
    state.isDirty = true
  }

  addArrayItem(field, state) {
    state.formData.onboardingData.general[field].push("")
    state.isDirty = true
  }

  removeArrayItem(field, index, state) {
    if (state.formData.onboardingData.general[field].length > 1) {
      state.formData.onboardingData.general[field].splice(index, 1)
      state.isDirty = true
    }
  }

  onSwatchCountChange(event, state) {
    const count = Number.parseInt(event.target.value) || 3
    const currentSwatches = state.formData.onboardingData.swatchPackage.swatches
    const newSwatches = []

    for (let i = 0; i < count; i++) {
      if (i < currentSwatches.length) {
        newSwatches.push(currentSwatches[i])
      } else {
        newSwatches.push({ material: "", gauge: "", stitch: "", colorway: "" })
      }
    }

    state.formData.onboardingData.swatchPackage.numberOfSwatches = count
    state.formData.onboardingData.swatchPackage.swatches = newSwatches
    state.formData.onboardingData.swatchPackage.expandedSwatches = [0]
    state.isDirty = true
  }

  addSwatch(state) {
    const swatches = state.formData.onboardingData.swatchPackage.swatches
    swatches.push({ material: "", gauge: "", stitch: "", colorway: "" })
    state.formData.onboardingData.swatchPackage.numberOfSwatches = swatches.length

    const newSwatchIndex = swatches.length - 1
    if (!state.formData.onboardingData.swatchPackage.expandedSwatches) {
      state.formData.onboardingData.swatchPackage.expandedSwatches = []
    }
    state.formData.onboardingData.swatchPackage.expandedSwatches.push(newSwatchIndex)

    state.isDirty = true
  }

  isSwatchExpanded(swatchIndex, state) {
    if (!state.formData.onboardingData.swatchPackage.expandedSwatches) {
      state.formData.onboardingData.swatchPackage.expandedSwatches = [0]
    }
    return state.formData.onboardingData.swatchPackage.expandedSwatches.includes(swatchIndex)
  }

  toggleSwatch(event, swatchIndex, state) {
    event.preventDefault()

    if (!state.formData.onboardingData.swatchPackage.expandedSwatches) {
      state.formData.onboardingData.swatchPackage.expandedSwatches = [0]
    }

    const expandedSwatches = [...state.formData.onboardingData.swatchPackage.expandedSwatches]
    const isExpanded = expandedSwatches.includes(swatchIndex)

    if (isExpanded) {
      state.formData.onboardingData.swatchPackage.expandedSwatches = expandedSwatches.filter(
        (index) => index !== swatchIndex,
      )
    } else {
      expandedSwatches.push(swatchIndex)
      state.formData.onboardingData.swatchPackage.expandedSwatches = expandedSwatches
    }
  }

  onSwatchFieldChange(event, index, field, state) {
    const value = event.target.value
    state.formData.onboardingData.swatchPackage.swatches[index][field] = value
    state.isDirty = true
  }

  onProductionFieldChange(event, field, state, index = null) {
    const value = event.target.value

    if (index !== null) {
      state.formData.onboardingData.production[field][index] = value
    } else {
      state.formData.onboardingData.production[field] = value
    }

    state.isDirty = true
  }

  addColorway(state) {
    state.formData.onboardingData.production.colorways.push("")
    state.isDirty = true
  }

  removeColorway(index, state) {
    if (state.formData.onboardingData.production.colorways.length > 1) {
      state.formData.onboardingData.production.colorways.splice(index, 1)
      state.isDirty = true
    }
  }

  addSize(state) {
    state.formData.onboardingData.production.sizes.push("")
    state.isDirty = true
  }

  removeSize(index, state) {
    if (state.formData.onboardingData.production.sizes.length > 1) {
      state.formData.onboardingData.production.sizes.splice(index, 1)
      state.isDirty = true
    }
  }

  onGeminiNotesChange(event, state) {
    state.formData.geminiNotes = event.target.value
    state.isDirty = true
  }
}
