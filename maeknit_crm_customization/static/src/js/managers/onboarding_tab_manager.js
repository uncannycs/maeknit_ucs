/** @odoo-module **/

export class OnboardingTabManager {
    constructor(state) {
      this.state = state
    }
  
    onGeneralFieldChange(event, field) {
      const value = event.target.value
      this.state.formData.onboardingData.general[field] = value
      this.state.isDirty = true
    }
  
    onArrayFieldChange(event, field, index) {
      const value = event.target.value
      this.state.formData.onboardingData.general[field][index] = value
      this.state.isDirty = true
    }
  
    addArrayItem(field) {
      this.state.formData.onboardingData.general[field].push("")
      this.state.isDirty = true
    }
  
    removeArrayItem(field, index) {
      if (this.state.formData.onboardingData.general[field].length > 1) {
        this.state.formData.onboardingData.general[field].splice(index, 1)
        this.state.isDirty = true
      }
    }
  
    onSwatchCountChange(event) {
      const count = Number.parseInt(event.target.value) || 3
      const currentSwatches = this.state.formData.onboardingData.swatchPackage.swatches
      const newSwatches = []
  
      for (let i = 0; i < count; i++) {
        if (i < currentSwatches.length) {
          newSwatches.push(currentSwatches[i])
        } else {
          newSwatches.push({ material: "", gauge: "", stitch: "", colorway: "" })
        }
      }
  
      this.state.formData.onboardingData.swatchPackage.numberOfSwatches = count
      this.state.formData.onboardingData.swatchPackage.swatches = newSwatches
      this.state.formData.onboardingData.swatchPackage.expandedSwatches = [0]
      this.state.isDirty = true
    }
  
    addSwatch() {
      const swatches = this.state.formData.onboardingData.swatchPackage.swatches
      swatches.push({ material: "", gauge: "", stitch: "", colorway: "" })
      this.state.formData.onboardingData.swatchPackage.numberOfSwatches = swatches.length
  
      const newSwatchIndex = swatches.length - 1
      if (!this.state.formData.onboardingData.swatchPackage.expandedSwatches) {
        this.state.formData.onboardingData.swatchPackage.expandedSwatches = []
      }
      this.state.formData.onboardingData.swatchPackage.expandedSwatches.push(newSwatchIndex)
  
      this.state.isDirty = true
    }
  
    isSwatchExpanded(swatchIndex) {
      if (!this.state.formData.onboardingData.swatchPackage.expandedSwatches) {
        this.state.formData.onboardingData.swatchPackage.expandedSwatches = [0]
      }
      return this.state.formData.onboardingData.swatchPackage.expandedSwatches.includes(swatchIndex)
    }
  
    toggleSwatch(event, swatchIndex) {
      event.preventDefault()
  
      if (!this.state.formData.onboardingData.swatchPackage.expandedSwatches) {
        this.state.formData.onboardingData.swatchPackage.expandedSwatches = [0]
      }
  
      const expandedSwatches = [...this.state.formData.onboardingData.swatchPackage.expandedSwatches]
      const isExpanded = expandedSwatches.includes(swatchIndex)
  
      if (isExpanded) {
        this.state.formData.onboardingData.swatchPackage.expandedSwatches = expandedSwatches.filter(
          (index) => index !== swatchIndex,
        )
      } else {
        expandedSwatches.push(swatchIndex)
        this.state.formData.onboardingData.swatchPackage.expandedSwatches = expandedSwatches
      }
    }
  
    onProductionFieldChange(event, field, index = null) {
      const value = event.target.value
  
      if (index !== null) {
        this.state.formData.onboardingData.production[field][index] = value
      } else {
        this.state.formData.onboardingData.production[field] = value
      }
  
      this.state.isDirty = true
    }
  
    addColorway() {
      this.state.formData.onboardingData.production.colorways.push("")
      this.state.isDirty = true
    }
  
    removeColorway(index) {
      if (this.state.formData.onboardingData.production.colorways.length > 1) {
        this.state.formData.onboardingData.production.colorways.splice(index, 1)
        this.state.isDirty = true
      }
    }
  
    addSize() {
      this.state.formData.onboardingData.production.sizes.push("")
      this.state.isDirty = true
    }
  
    removeSize(index) {
      if (this.state.formData.onboardingData.production.sizes.length > 1) {
        this.state.formData.onboardingData.production.sizes.splice(index, 1)
        this.state.isDirty = true
      }
    }
  
    onGeminiNotesChange(event) {
      this.state.formData.geminiNotes = event.target.value
      this.state.isDirty = true
    }
  }
  