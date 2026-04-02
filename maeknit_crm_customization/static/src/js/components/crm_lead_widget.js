"use client"

/** @odoo-module **/

import { Component, useState, onWillStart, onWillUpdateProps, useRef, onMounted } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { useRecordObserver } from "@web/model/relational_model/utils"
import { standardFieldProps } from "@web/views/fields/standard_field_props"
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { FormDataManager } from "../utils/form_data_manager"
import { DataManager } from "../managers/data_manager"
import { FormInputManager } from "../managers/form_input_manager"
import { SearchDropdownManager } from "../managers/search_dropdown_manager"
import { ChildOpportunitiesManager } from "../managers/child_opportunities_manager"
import { OnboardingTabManager } from "../managers/onboarding_tab_manager"
import { SwatchingTabManager } from "../managers/swatching_tab_manager"
import { DevelopmentTabManager } from "../managers/development_tab_manager"
import { ReverseTabManager } from "../managers/reverse_tab_manager"
import { GradingTabManager } from "../managers/grading_tab_manager"
import { ProductionTabManager } from "../managers/production_tab_manager"
import { safeErrorString, formatCurrency, isServiceSelected, isServiceTypeSelected } from "../utils/helpers"

export class CrmLeadOwlWidget extends Component {
  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.actionService = useService("action")
    this.dialog = useService("dialog");

    this.state = useState({
      record: {},
      isLoading: true,
      isNewRecord: false,
      formData: FormDataManager.getInitialFormData(),
      isDirty: false,
      availableTags: [],
      availableUsers: [],
      availablePartners: [],
      availableProducts: [],
      availableLeads: [],
      availableCompanies: [],
      searchState: {
        userSearch: "",
        partnerSearch: "",
        productSearch: "",
        parentLeadSearch: "",
        companySearch: "",
        filteredUsers: [],
        filteredPartners: [],
        filteredProducts: [],
        filteredLeads: [],
        filteredCompanies: [],
        showUserDropdown: false,
        showPartnerDropdown: false,
        showProductDropdown: false,
        showParentLeadDropdown: false,
        showCompanyDropdown: false,
        selectedUserIndex: 0,
        selectedPartnerIndex: 0,
        selectedProductIndex: 0,
        selectedParentLeadIndex: 0,
        selectedCompanyIndex: 0,
        // Manual product search for Production tab
        manualProductSearch: "",
        filteredManualProducts: [],
        showManualProductDropdown: false,
        selectedManualProductIndex: 0,
      },
      debugInfo: {
        errors: [],
        directFetchData: null,
        availableFields: [],
        lastAction: "",
        lastMode: "",
      },
      selectedChildLeads: [],
      childOpportunitiesRows: [],
      isChildOpportunitiesDirty: false,
      nextTempId: -1,
      relatedSalesOrders: [],
    })

    this.userInput = useRef("user_input")
    this.partnerInput = useRef("partner_input")
    this.productInput = useRef("product_input")
    this.parentLeadInput = useRef("parent_lead_input")

    this.lastRecordId = null

    // Bind manager methods to `this` and pass `this.state`
    this.dataManager = new DataManager(this.orm, this.notification, this.state, this.props)
    this.formInputManager = new FormInputManager(this.state)
    this.searchDropdownManager = new SearchDropdownManager(this.orm, this.state)
    this.childOpportunitiesManager = new ChildOpportunitiesManager(this.orm, this.notification, this.state, this.props)
    this.onboardingTabManager = new OnboardingTabManager(this.state)
    this.swatchingTabManager = new SwatchingTabManager(this.orm, this.state)
    this.developmentTabManager = new DevelopmentTabManager(this.state)
    this.reverseTabManager = new ReverseTabManager(this.state)
    this.gradingTabManager = new GradingTabManager(this.state)
    this.productionTabManager = new ProductionTabManager(this.state, this.orm)

    onWillStart(async () => {
      this.state.debugInfo.lastAction = "onWillStart called"
      await this.dataManager.loadData()
    })

    onMounted(() => {
      console.log("Component mounted - setting up form view hooks")
      this.state.debugInfo.lastAction = "Component mounted"
      this.setupFormViewHooks()

      setTimeout(() => {
        const closeButton = document.querySelector(".o_form_button_cancel, .o_form_button_x")
        if (closeButton) {
          console.log("Found close button, adding event listener")
          closeButton.addEventListener("click", () => {
            console.log("Close button clicked, canceling changes")
            this.cancelChanges()
          })
        } else {
          console.log("Close button not found")
        }

        const dialogCloseButton = document.querySelector(".modal-header .btn-close")
        if (dialogCloseButton) {
          console.log("Found dialog close button, adding event listener")
          dialogCloseButton.addEventListener("click", () => {
            console.log("Dialog close button clicked, canceling changes")
            this.cancelChanges()
          })
        }
      }, 500)
    })

    onWillUpdateProps(async (nextProps) => {
      console.log("onWillUpdateProps called - checking for record changes", nextProps)
      this.state.debugInfo.lastAction = "onWillUpdateProps called"
      console.log("Current props:", this.props)

      const currentId = this.props.record && this.props.record.resId ? this.props.record.resId : null
      const nextId = nextProps.record && nextProps.record.resId ? nextProps.record.resId : null

      console.log("Record ID change check:", {
        currentId,
        nextId,
        lastRecordId: this.lastRecordId,
      })

      if (currentId !== nextId || (this.lastRecordId && !nextId)) {
        this.state.isLoading = true
        this.dataManager.props = nextProps // Update props for dataManager
        await this.dataManager.handleRecordChange(nextId, this.lastRecordId)
        this.lastRecordId = this.state.isNewRecord ? null : nextId // Update lastRecordId based on new state
        this.state.isLoading = false
      }
    })

    useRecordObserver((record) => {
      if (!record) return

      console.log("Record observer triggered", record)
      this.state.debugInfo.lastAction = "Record observer triggered"
      this.state.record = record

      const isCreateMode = record.model && record.model.root && record.model.root.mode === "create"
      const isNew = !record.resId || record.resId <= 0 || isCreateMode

      this.state.debugInfo.lastMode = record.model && record.model.root ? record.model.root.mode : "unknown"

      if (isNew !== this.state.isNewRecord) {
        this.state.isNewRecord = isNew
        if (isNew) {
          this.state.debugInfo.lastAction = "Record observer detected new record"
          this.dataManager.initializeNewRecord()
        } else if (record.resId && record.resId !== this.lastRecordId) {
          this.lastRecordId = record.resId
          this.dataManager.loadRecordData()
        }
      } else if (!isNew && record.resId && record.resId !== this.lastRecordId) {
        this.lastRecordId = record.resId
        this.dataManager.loadRecordData()
      }

      this.state.isDirty = false
    })

    this.setupSaveHook()
  }

  // --- Core Odoo Integration & Form Management ---
  setupFormViewHooks() {
    try {
      let parent = this.__owl__.parent
      let formController = null

      while (parent && !formController) {
        if (parent.component && parent.component.props && parent.component.props.record) {
          formController = parent.component
          break
        }
        parent = parent.__owl__.parent
      }

      if (formController) {
        this.formController = formController
        this.state.debugInfo.lastAction = "Found form controller"

        const originalCreate = formController.create
        if (typeof originalCreate === "function") {
          formController.create = (...args) => {
            console.log("Form controller create method called")
            this.state.debugInfo.lastAction = "Form controller create method called"
            this.state.isNewRecord = true
            this.dataManager.initializeNewRecord()
            return originalCreate.apply(formController, args)
          }
        }
      } else {
        console.log("Could not find form controller")
        this.state.debugInfo.lastAction = "Could not find form controller"
      }
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error setting up form view hooks:", errorString)
      this.state.debugInfo.errors.push("Error setting up form view hooks: " + errorString)
    }
  }

  setupSaveHook() {
    try {
      if (this.props.record && this.props.record.save) {
        const originalSave = this.props.record.save.bind(this.props.record)

        this.props.record.save = async (...args) => {
          console.log("Odoo save intercepted - saving child opportunities first")

          if (this.state.isChildOpportunitiesDirty && this.state.childOpportunitiesRows.length > 0) {
            await this.childOpportunitiesManager.saveChildOpportunitiesInternal()
          }

          const result = await originalSave(...args)

          if (this.props.record && this.props.record.resId) {
            await this.dataManager.fetchChildOpportunities()
          }

          return result
        }
      }
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error setting up save hook:", errorString)
      this.state.debugInfo.errors.push("Error setting up save hook: " + errorString)
    }
  }

  notifyFormChange() {
    if (this.props.record && this.props.record.model) {
      try {
        if (this.props.record.model.root) {
          this.props.record.model.root.dirty = true
        }

        const statusIndicator = document.querySelector(".o_form_status_indicator_buttons")
        if (statusIndicator && statusIndicator.classList.contains("invisible")) {
          statusIndicator.classList.remove("invisible")
        }

        const saveButton = document.querySelector(".o_form_button_save")
        if (saveButton && saveButton.hasAttribute("disabled")) {
          saveButton.removeAttribute("disabled")
        }
      } catch (error) {
        const errorString = safeErrorString(error)
        console.error("Error notifying form change:", errorString)
      }
    }
  }

  updateRecordOnChange() {
    if (!this.props.record) return

    try {
      if (this.props.record.update) {
        const changes = {
          name: this.state.formData.name,
          expected_revenue: this.totalServiceRevenue,
          priority: this.state.formData.priority,
          season_drop_date: this.state.formData.season_drop_date,
          x_service_revenues: JSON.stringify(this.state.formData.service_revenues),
          x_onboarding_data: JSON.stringify(this.state.formData.onboardingData),
          x_gemini_notes: this.state.formData.geminiNotes,
          x_include_development_in_quote: this.state.formData.x_include_development_in_quote,
          x_include_production_in_quote: this.state.formData.x_include_production_in_quote,
          x_include_swatch_in_quote: this.state.formData.x_include_swatch_in_quote,
          x_include_reverse_in_quote: this.state.formData.x_include_reverse_in_quote,
          x_include_grading_in_quote: this.state.formData.x_include_grading_in_quote,
          x_project_type: this.state.formData.x_project_type,
          x_selected_child_leads: JSON.stringify(this.state.selectedChildLeads),
          x_development_prices: JSON.stringify(this.state.formData.developmentData.itemPrices),
          x_swatch_data: JSON.stringify(this.state.formData.swatchData),
          x_grading_data: JSON.stringify(this.state.formData.gradingData),
          x_reverse_data: JSON.stringify(this.state.formData.reverseData),
        }

        if (this.state.formData.partner_id) {
          changes.partner_id = this.state.formData.partner_id
        } else if (this.state.formData.partner_name) {
          changes.partner_name = this.state.formData.partner_name
        }

        if (this.state.formData.user_id) {
          changes.user_id = this.state.formData.user_id
        }

        if (this.state.formData.company_id) {
          changes.company_id = this.state.formData.company_id
        }

        if (this.state.formData.parent_id) {
          changes.parent_id = this.state.formData.parent_id
        }

        if (this.state.formData.tag_ids && this.state.formData.tag_ids.length > 0) {
          const tagIds = this.state.formData.tag_ids.map((tag) => tag[0])
          changes.tag_ids = [[6, 0, tagIds]]
        } else {
          changes.tag_ids = [[6, 0, []]]
        }

        this.props.record.update(changes)
        this.notifyFormChange()
      }
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error updating record data:", errorString)
      this.state.debugInfo.errors.push("Error updating record data: " + errorString)
    }
  }

  async generateStyles() {
    console.log("Generate Styles button clicked - calling save functionality")
    console.log("Generate Styles button clicked - calling Odoo default save")
    if (this.props.record && this.props.record.save) {
      await this.props.record.save()
    } else {
      console.error("No record save method available")
      this.notification.add("Unable to save - no record available", { type: "danger" })
    }
  }

  // Adding Generate Quote methods for all service tabs
  async generateSwatchQuote() {
    console.log("Generate Swatch Quote button clicked - setting swatch flag and creating quotation")

    // Set only swatch service to be included in quote
    this.onIncludeInQuoteChange(null, "swatch")
    this.selectServiceTagForQuote("swatch")

    try {
      // Save changes first
      if (this.props.record && this.props.record.save) {
        console.log("Generate Swatch Quote button clicked - setting swatch flag and creating quotation")
        await this.props.record.save()
      }
      if (this.props.record && this.props.record.resId) {
        const action = await this.orm.call("crm.lead", "action_sale_quotations_new", [this.props.record.resId])

        if (action && typeof action === "object" && action.type) {
          await this.actionService.doAction(action)
        } else {
          this.notification.add("Could not open quotation action", { type: "warning" })
        }
      }
    } catch (error) {
      console.error("Error in generate Swatch Quote:", error)
    }
  }

  selectServiceTagForQuote(quoteType) {
    console.log("Selecting service tag for quote:", quoteType)
    console.log("Available tags:", this.state.availableTags)

    const serviceTagMap = {
      swatch: "Swatch Service",
      development: "Development",
      // reverse: "Reverse Engineering Service",
      grading: "Grading Service",
      production: "Production",
    }

    const serviceName = serviceTagMap[quoteType]
    if (!serviceName) {
      console.error("Unknown quote type:", quoteType)
      return
    }

    // Find the service tag
    const serviceTag = this.state.availableTags.find((tag) => tag[1] === serviceName)
    if (!serviceTag) {
      console.error("Service tag not found:", serviceName)
      return
    }

    const isAlreadySelected = this.state.formData.tag_ids.some((tag) => tag[0] === serviceTag[0])

    if (!isAlreadySelected) {
      this.state.formData.tag_ids.push(serviceTag)
      console.log("Added new service tag to existing selections")
    } else {
      console.log("Service tag already selected, no changes needed")
    }

    this.updateRecordOnChange()

    console.log("Tag selection completed, tag_ids:", this.state.formData.tag_ids)
  }

  async generateDevelopmentQuote() {
    this.onIncludeInQuoteChange(null, "development")
    this.selectServiceTagForQuote("development")
    try {
      if (this.props.record && this.props.record.save) {
        console.log("Generate Development Quote button clicked - setting development flag and creating quotation")
        await this.props.record.save()
      }

      if (this.props.record && this.props.record.resId) {
        const action = await this.orm.call("crm.lead", "action_sale_quotations_new", [this.props.record.resId])

        if (action && typeof action === "object" && action.type) {
          await this.actionService.doAction(action)
        } else {
          this.notification.add("Could not open quotation action", { type: "warning" })
        }
      }
    } catch (error) {
      console.error("Error in generate Development Quote:", error)
    }
  }

  async generateReverseQuote() {
    // Set only swatch service to be included in quote
    this.onIncludeInQuoteChange(null, "reverse")
    this.selectServiceTagForQuote("reverse")
    try {
      // Save changes first
      if (this.props.record && this.props.record.save) {
        console.log("Generate Reverse Quote button clicked - setting reverse flag and creating quotation")
        await this.props.record.save()
      }
      if (this.props.record && this.props.record.resId) {
        const action = await this.orm.call("crm.lead", "action_sale_quotations_new", [this.props.record.resId])

        if (action && typeof action === "object" && action.type) {
          await this.actionService.doAction(action)
        } else {
          this.notification.add("Could not open quotation action", { type: "warning" })
        }
      }
    } catch (error) {
      console.error("Error in generate Reverse Quote:", error)
    }
  }

  async generateGradingQuote() {
    // Set only swatch service to be included in quote
    this.onIncludeInQuoteChange(null, "grading")
    this.selectServiceTagForQuote("grading")
    try {
      // Save changes first
      if (this.props.record && this.props.record.save) {
        console.log("Generate Grading Quote button clicked - setting grading flag and creating quotation")
        await this.props.record.save()
      }
      if (this.props.record && this.props.record.resId) {
        const action = await this.orm.call("crm.lead", "action_sale_quotations_new", [this.props.record.resId])

        if (action && typeof action === "object" && action.type) {
          await this.actionService.doAction(action)
        } else {
          this.notification.add("Could not open quotation action", { type: "warning" })
        }
      }
    } catch (error) {
      console.error("Error in generate Grading Quote:", error)
    }
  }

  async generateProductionQuote() {
    // Set only swatch service to be included in quote
    this.onIncludeInQuoteChange(null, "production")
    this.selectServiceTagForQuote("production")

    try {
      // Save changes first
      if (this.props.record && this.props.record.save) {
        console.log("Generate Production Quote button clicked - setting production flag and creating quotation")
        await this.props.record.save()
      }
      if (this.props.record && this.props.record.resId) {
        const action = await this.orm.call("crm.lead", "action_sale_quotations_new", [this.props.record.resId])

        if (action && typeof action === "object" && action.type) {
          await this.actionService.doAction(action)
        } else {
          this.notification.add("Could not open quotation action", { type: "warning" })
        }
      }
    } catch (error) {
      console.error("Error in generate Production Quote:", error)
    }
  }

  getItemCssClasses(itemId, serviceType) {
    const isQuoted = this.isItemQuoted(itemId, serviceType)
    return isQuoted ? "quoted-item" : ""
  }

  isItemQuoted(itemId, styleFamily, serviceType) {
    if (!this.state.relatedSalesOrders || !itemId) {
      return false
    }

    // Check if any related sales order contains this item for the specified service type
    return this.state.relatedSalesOrders.some((order) => {
      console.log("Checking order:", order)
      console.log("Item ID:", itemId)
      console.log("Service type:", serviceType)
      console.log("Order items:", order.x_quoted_items || [])
      console.log('style')
      // Style family match
      const quotedStyles = (order.x_quoted_style_families || "")
        .split(",")
        .map(s => s.trim())
      console.log("Quoted styles:", quotedStyles)
      const hasStyleFamily = styleFamily && quotedStyles.includes(styleFamily)
      console.log("Has style family match:", hasStyleFamily)
      return hasStyleFamily
    })
  }

  async saveChanges() {
    if (!this.state.formData.name || this.state.formData.name.trim() === "") {
      this.notification.add("Collection Name is required", { type: "danger" })
      return
    }

    if (!this.state.formData.partner_id) {
      this.notification.add("Client is required", { type: "danger" })
      return
    }
    try {
      if (!this.state.isDirty) return

      const data = {
        name: this.state.formData.name,
        expected_revenue: this.totalServiceRevenue,
        priority: this.state.formData.priority,
        season_drop_date: this.state.formData.season_drop_date,
        x_service_revenues: JSON.stringify(this.state.formData.service_revenues),
        x_onboarding_data: JSON.stringify(this.state.formData.onboardingData),
        x_gemini_notes: this.state.formData.geminiNotes,
        x_include_development_in_quote: this.state.formData.x_include_development_in_quote,
        x_include_production_in_quote: this.state.formData.x_include_production_in_quote,
        x_include_swatch_in_quote: this.state.formData.x_include_swatch_in_quote,
        // x_include_reverse_in_quote: this.state.formData.x_include_reverse_in_quote,
        x_include_grading_in_quote: this.state.formData.x_include_grading_in_quote,
        x_project_type: this.state.formData.x_project_type,
        x_selected_child_leads: JSON.stringify(this.state.selectedChildLeads),
        x_development_prices: JSON.stringify(this.state.formData.developmentData.itemPrices),
        x_swatch_data: JSON.stringify(this.state.formData.swatchData),
        x_grading_data: JSON.stringify(this.state.formData.gradingData),
        // x_reverse_data: JSON.stringify(this.state.formData.reverseData),
      }

      if (this.state.formData.parent_id) {
        data.parent_id = this.state.formData.parent_id[0]
      } else {
        data.parent_id = false
      }

      if (this.state.formData.company_id) {
        data.company_id = this.state.formData.company_id[0]
      }

      if (this.state.formData.partner_id) {
        data.partner_id = this.state.formData.partner_id[0]
      } else if (this.state.formData.partner_name) {
        data.partner_name = this.state.formData.partner_name
      }

      if (this.state.formData.user_id) {
        data.user_id = this.state.formData.user_id[0]
      }

      if (this.state.formData.tag_ids && this.state.formData.tag_ids.length > 0) {
        data.tag_ids = [[6, 0, this.state.formData.tag_ids.map((tag) => tag[0])]]
      } else {
        data.tag_ids = [[6, 0, []]]
      }

      if (this.state.formData.product_ids && this.state.formData.product_ids.length > 0) {
        data.product_ids = [[6, 0, this.state.formData.product_ids.map((product) => product[0])]]
      } else {
        data.product_ids = [[6, 0, []]]
      }

      let model = "crm.lead"
      let recordId = null

      try {
        if (
          this.props.record &&
          this.props.record.model &&
          this.props.record.model.root &&
          this.props.record.model.root.resModel
        ) {
          model = this.props.record.model.root.resModel
        }
      } catch (e) {
        console.error("Error getting model from record:", safeErrorString(e))
      }

      if (this.state.isNewRecord || !this.props.record || !this.props.record.resId) {
        console.log("Creating new record")

        try {
          recordId = await this.orm.create(model, [data])
          console.log("New record created with ID:", recordId)

          this.state.isNewRecord = false
          this.lastRecordId = recordId

          this.notification.add("New record created successfully", { type: "success" })

          const baseUrl = window.location.href.split("/new")[0]
          const newUrl = `${baseUrl}/${recordId}?mode=edit`

          window.location.href = newUrl

          return
        } catch (e) {
          const errorString = safeErrorString(e)
          console.error("Error creating record:", errorString)
          this.notification.add("Error creating record: " + (e.message || errorString), { type: "danger" })
          this.state.debugInfo.errors.push("Error creating record: " + errorString)
        }
      } else {
        recordId = this.props.record.resId
        console.log("Updating existing record ID:", recordId)

        await this.orm.write(model, [recordId], data)

        await this.dataManager.loadRecordData()

        this.notification.add("Changes saved successfully", { type: "success" })
      }

      this.state.isDirty = false
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error saving changes:", errorString)
      this.notification.add("Error saving changes: " + (error.message || errorString), { type: "danger" })
      this.state.debugInfo.errors.push("Error saving changes: " + errorString)
    }
  }

  cancelChanges() {
    if (this.state.isNewRecord) {
      this.dataManager.initializeNewRecord()
    } else {
      this.dataManager.loadRecordData()
    }
    this.state.isDirty = false
  }

  manualReset() {
    console.log("Manual reset triggered")
    this.dataManager.initializeNewRecord()
    this.notification.add("Form manually reset", { type: "info" })
  }

  // --- Computed Properties ---
  get priorityOptions() {
    return [
      { value: "0", label: "None" },
      { value: "1", label: "Low" },
      { value: "2", label: "Medium" },
      { value: "3", label: "High" },
    ]
  }

  get priorityStars() {
    const priority = Number.parseInt(this.state.formData.priority || "0", 10)
    return "★".repeat(priority) + "☆".repeat(3 - priority)
  }

  get formattedRevenue() {
    return formatCurrency(this.state.formData.expected_revenue)
  }

  get totalServiceRevenue() {
    if (!this.state.formData.service_revenues) return 0

    return Object.values(this.state.formData.service_revenues).reduce((sum, value) => {
      return sum + (Number.parseFloat(value) || 0)
    }, 0)
  }

  get formattedTotalServiceRevenue() {
    return formatCurrency(this.totalServiceRevenue)
  }

  // --- General Form Input Handlers (delegated to FormInputManager) ---
  onInputChange(event) {
    this.formInputManager.onInputChange(event)
    this.updateRecordOnChange()
  }

  async onNameBlur() {
    const name = this.state.formData.name
    const partnerId = this.state.formData.partner_id
    if (name && name.trim() && partnerId && this.props.record && this.props.record.save) {
      await this.props.record.save()
    }
  }

  onNumberChange(event) {
    this.formInputManager.onNumberChange(event)
    this.updateRecordOnChange()
  }

  onPriorityChange(event) {
    this.formInputManager.onPriorityChange(event)
    this.updateRecordOnChange()
  }

  onEmailChange(event) {
    this.formInputManager.onEmailChange(event)
    // No updateRecordOnChange needed as email is read-only
  }

  onProjectTypeChange(event) {
    this.formInputManager.onProjectTypeChange(event)
    this.updateRecordOnChange()
  }

  onIncludeInQuoteChange(event, serviceType) {
    this.formInputManager.onIncludeInQuoteChange(event, serviceType)
    this.updateRecordOnChange()
  }

  getServiceRevenue(tagId) {
    return this.formInputManager.getServiceRevenue(tagId)
  }

  onServiceRevenueChange(event, tagId) {
    this.formInputManager.onServiceRevenueChange(event, tagId)
    this.updateRecordOnChange()
  }

  isTagSelected(tagId) {
    return this.formInputManager.isTagSelected(tagId)
  }

  onTagChange(event) {
    this.formInputManager.onTagChange(event, this.state.availableTags)
    this.updateRecordOnChange()
  }

  areAllServicesSelected() {
    return this.formInputManager.areAllServicesSelected()
  }

  onToggleSelectAllServices(event) {
    this.formInputManager.onToggleSelectAllServices(event, this.state.availableTags)
    this.updateRecordOnChange()
  }

  // --- Search Dropdown Handlers (delegated to SearchDropdownManager) ---
  onUserSearchChange(event) {
    this.searchDropdownManager.onUserSearchChange(event, this.state.availableUsers)
    this.updateRecordOnChange()
  }
  onUserFocus() {
    this.searchDropdownManager.onUserFocus(this.state.availableUsers)
  }
  onUserBlur() {
    this.searchDropdownManager.onUserBlur()
  }
  onUserKeyDown(event) {
    this.searchDropdownManager.onUserKeyDown(event)
  }
  onUserItemHover(index) {
    this.searchDropdownManager.onUserItemHover(index)
  }
  onUserSelect(userId, userName) {
    this.searchDropdownManager.onUserSelect(userId, userName)
    this.updateRecordOnChange()
  }

  onPartnerSearchChange(event) {
    this.searchDropdownManager.onPartnerSearchChange(event, this.state.availablePartners)
    this.updateRecordOnChange()
  }
  onPartnerFocus() {
    this.searchDropdownManager.onPartnerFocus(this.state.availablePartners)
  }
  onPartnerBlur() {
    this.searchDropdownManager.onPartnerBlur()
  }
  onPartnerKeyDown(event) {
    this.searchDropdownManager.onPartnerKeyDown(event)
  }
  onPartnerItemHover(index) {
    this.searchDropdownManager.onPartnerItemHover(index)
  }
  async onPartnerSelect(partnerId, partnerName) {
    this.searchDropdownManager.onPartnerSelect(partnerId, partnerName, this.state.availablePartners)
    this.updateRecordOnChange()
    const name = this.state.formData.name
    if (name && name.trim() && this.props.record && this.props.record.save) {
      await this.props.record.save()
    }
  }

  onParentLeadSearchChange(event) {
    this.searchDropdownManager.onParentLeadSearchChange(event, this.props.record?.resId)
    this.updateRecordOnChange()
  }
  onParentLeadFocus() {
    this.searchDropdownManager.onParentLeadFocus(this.props.record?.resId)
  }
  onParentLeadBlur() {
    this.searchDropdownManager.onParentLeadBlur()
  }
  onParentLeadKeyDown(event) {
    this.searchDropdownManager.onParentLeadKeyDown(event)
  }
  onParentLeadItemHover(index) {
    this.searchDropdownManager.onParentLeadItemHover(index)
  }
  onParentLeadSelect(leadId, leadName) {
    this.searchDropdownManager.onParentLeadSelect(leadId, leadName)
    this.updateRecordOnChange()
  }

  onCompanySearchChange(event) {
    this.searchDropdownManager.onCompanySearchChange(event, this.state.availableCompanies)
    this.updateRecordOnChange()
  }
  onCompanyFocus() {
    this.searchDropdownManager.onCompanyFocus(this.state.availableCompanies)
  }
  onCompanyBlur() {
    this.searchDropdownManager.onCompanyBlur()
  }
  onCompanyKeyDown(event) {
    this.searchDropdownManager.onCompanyKeyDown(event)
  }
  onCompanyItemHover(index) {
    this.searchDropdownManager.onCompanyItemHover(index)
  }
  onCompanySelect(companyId, companyName) {
    this.searchDropdownManager.onCompanySelect(companyId, companyName)
    this.updateRecordOnChange()
  }

  async createContactInline() {
    this.dialog.add(FormViewDialog, {
      resModel: "res.partner",
      title: "Create Contact",
      size: "m",                 // large base size
      dialogClass: "mk-60vw",     // class on .modal-dialog

      context: {
        form_view_ref: "maeknit_crm_customization.view_partner_quick_create",
        default_is_company: false,
        default_type: "contact",
        default_email: this.state.formData.email_from || "",
        default_contact_type: "brand",
      },
      onRecordSaved: async (record) => {
        try {
          // Build a safe payload (don’t pass record.data raw)
          const vals = {
            name: record.data.name,
            email: record.data.email || "",
            phone: record.data.phone || "",
            mobile: record.data.mobile || "",
            // make sure these match your field/domain rules
            is_company: !!record.data.is_company,
            contact_type: record.data.contact_type || "brand",
          };
      
          // Create partner and get its id
          const res = await this.orm.create("res.partner", [vals]); // returns [id] or id
          const newId = Array.isArray(res) ? res[0] : res;
      
          // Read display fields instead of name_get
          const [p] = await this.orm.read("res.partner", [newId], ["id", "display_name", "name", "email"]);
          const display = p.display_name || p.name || `#${p.id}`;
          const email = p.email || "";
      
          // 1) Select it on the form
          this.state.formData.partner_id = [p.id, display];
          if (!this.state.formData.email_from && email) this.state.formData.email_from = email;
      
          // 2) Refresh dropdown data source so searching finds it immediately
          // keep structure [id, label, email] to match your SearchDropdownManager
          this.state.availablePartners = [
            ...this.state.availablePartners.filter(x => x && x[0] !== p.id),
            [p.id, display, email],
          ];
          this.state.searchState.partnerSearch = display;
          this.state.searchState.filteredPartners =
            this.searchDropdownManager._filterItems(this.state.availablePartners, display);
          this.state.searchState.showPartnerDropdown = false;
      
          await this.updateRecordOnChange();
      
          // Give the new lead an id if needed and refresh only this record
          await this.props.record.save({ stayInEdit: true });
          await this.props.record.load();
      
          this.notification.add(`Contact "${display}" created and selected`, { type: "success" });
        } catch (e) {
          console.error(e);
          this.notification.add("Contact created, but refresh failed", { type: "warning" });
        }
      }
    });      
  }
  
  
  // --- Child Opportunities Tab Handlers (delegated to ChildOpportunitiesManager) ---
  async addChildOpportunityRow() {
    let freshParentId = null

    if (this.props.record && this.props.record.save) {
      const saveResult = await this.props.record.save()
      // Try to get the ID from the save result or the updated record
      freshParentId = saveResult?.resId || this.props.record.resId || this.props.record.data.id
    }

    // Pass the fresh parent ID to the manager
    await this.childOpportunitiesManager.addChildOpportunityRow(freshParentId)
    this.updateRecordOnChange()
    if (this.props.record && this.props.record.save) {
      await this.props.record.save()}
  }

  onChildFieldChange(event, tempId, fieldName) {
    this.childOpportunitiesManager.onChildFieldChange(event, tempId, fieldName)
    this.updateRecordOnChange()
  }

  deleteChildOpportunity(tempId, childId) {
    this.childOpportunitiesManager.deleteChildOpportunity(tempId, childId)
    this.updateRecordOnChange()
  }

  // --- Tab Switching ---
  switchTab(tabName) {
    this.formInputManager.switchTab(tabName)

    // When switching to a service tab, fetch related sales orders
    const serviceTabs = ["development", "swatching", "grading", "production"]
    if (serviceTabs.includes(tabName)) {
      // Ensure selectedChildLeads are synced to developmentData.selectedItems when entering these tabs
      this.state.formData.developmentData.selectedItems = [...this.state.selectedChildLeads]

      if (tabName === "grading" && (!this.state.formData.gradingData || !this.state.formData.gradingData.items)) {
        this.state.formData.gradingData = { items: [], pricePerGrade: 300 }
        // Populate grading items based on current child opportunities
        this.gradingTabManager.getGradingItems()
      }

      if (tabName === "production") {
        // Load production grid when switching to production tab
        this.onProductionTabActive()
      }

      // Auto-select all items for first-time visits to service tabs (when no prior selections exist)
      this.autoSelectAllForFirstTimeVisit(tabName)

      this.dataManager.fetchRelatedSalesOrders(tabName)
    }
  }

  // Helper method to auto-select all items for first-time visits
  autoSelectAllForFirstTimeVisit(tabName) {
    try {
      switch (tabName) {
        case "swatching":
          // Check if there are no prior swatch selections
          const swatchItems = this.swatchingTabManager.getSwatchItems()
          const hasSwatchSelections = swatchItems.some((item) =>
            this.swatchingTabManager.isSwatchItemSelected(item.tempId),
          )

          if (swatchItems.length > 0 && !hasSwatchSelections) {
            // Auto-select all swatches
            swatchItems.forEach((item) => {
              if (!this.swatchingTabManager.isSwatchItemSelected(item.tempId)) {
                // Simulate checkbox event to select the item
                const fakeEvent = { target: { checked: true } }
                this.swatchingTabManager.onSwatchItemSelect(fakeEvent, item.tempId)
              }
            })
            this.updateRecordOnChange()
          }
          break

        case "development":
          // Check if there are no prior development selections
          const devItems = this.developmentTabManager.getProductItems()
          const hasDevSelections = devItems.some((item) =>
            this.developmentTabManager.isDevelopmentItemSelected(item.id),
          )

          if (devItems.length > 0 && !hasDevSelections) {
            // Auto-select all development items
            devItems.forEach((item) => {
              if (!this.developmentTabManager.isDevelopmentItemSelected(item.id)) {
                // Simulate checkbox event to select the item
                const fakeEvent = { target: { checked: true } }
                this.developmentTabManager.onDevelopmentItemSelect(fakeEvent, item.id)
              }
            })
            this.updateRecordOnChange()
          }
          break

        case "grading":
          // Check if there are no prior grading selections
          const gradingItems = this.gradingTabManager.getGradingItems()
          const hasGradingSelections = gradingItems.some((item) =>
            this.gradingTabManager.isGradingItemSelected(item.tempId),
          )

          if (gradingItems.length > 0 && !hasGradingSelections) {
            // Auto-select all grading items
            gradingItems.forEach((item) => {
              if (!this.gradingTabManager.isGradingItemSelected(item.tempId)) {
                // Simulate checkbox event to select the item
                const fakeEvent = { target: { checked: true } }
                this.gradingTabManager.onGradingItemSelect(fakeEvent, item.tempId)
              }
            })
            this.updateRecordOnChange()
          }
          break

        case "production":
          // Production tab uses grid-based UI, no auto-selection needed
          break
      }
    } catch (error) {
      console.error(`Error auto-selecting items for ${tabName} tab:`, error)
    }
  }

  // --- Onboarding Tab Handlers (delegated to OnboardingTabManager) ---
  onGeneralFieldChange(event, field) {
    this.onboardingTabManager.onGeneralFieldChange(event, field)
    this.updateRecordOnChange()
  }
  onArrayFieldChange(event, field, index) {
    this.onboardingTabManager.onArrayFieldChange(event, field, index)
    this.updateRecordOnChange()
  }
  addArrayItem(field) {
    this.onboardingTabManager.addArrayItem(field)
    this.updateRecordOnChange()
  }
  removeArrayItem(field, index) {
    this.onboardingTabManager.removeArrayItem(field, index)
    this.updateRecordOnChange()
  }
  onSwatchCountChange(event) {
    this.onboardingTabManager.onSwatchCountChange(event)
    this.updateRecordOnChange()
  }
  addSwatch() {
    this.onboardingTabManager.addSwatch()
    this.updateRecordOnChange()
  }
  isSwatchExpanded(swatchIndex) {
    return this.onboardingTabManager.isSwatchExpanded(swatchIndex)
  }
  toggleSwatch(event, swatchIndex) {
    this.onboardingTabManager.toggleSwatch(event, swatchIndex)
    this.updateRecordOnChange()
  }
  onProductionFieldChange(event, field, index = null) {
    this.onboardingTabManager.onProductionFieldChange(event, field, index)
    this.updateRecordOnChange()
  }
  addColorway() {
    this.onboardingTabManager.addColorway()
    this.updateRecordOnChange()
  }
  removeColorway(index) {
    this.onboardingTabManager.removeColorway(index)
    this.updateRecordOnChange()
  }
  addSize() {
    this.onboardingTabManager.addSize()
    this.updateRecordOnChange()
  }
  removeSize(index) {
    this.onboardingTabManager.removeSize(index)
    this.updateRecordOnChange()
  }
  onGeminiNotesChange(event) {
    this.onboardingTabManager.onGeminiNotesChange(event)
    this.updateRecordOnChange()
  }

  // --- Swatching Tab Handlers (delegated to SwatchingTabManager) ---
  getSwatchItems() {
    return this.swatchingTabManager.getSwatchItems()
  }
  addSwatchItem() {
    this.swatchingTabManager.addSwatchItem()
    this.updateRecordOnChange()
  }
  removeSwatchItem(tempId) {
    this.swatchingTabManager.removeSwatchItem(tempId)
    this.updateRecordOnChange()
  }
  onSwatchFieldChange(event, tempId, field) {
    this.swatchingTabManager.onSwatchFieldChange(event, tempId, field)
    this.updateRecordOnChange()
  }
  isSwatchItemSelected(tempId) {
    return this.swatchingTabManager.isSwatchItemSelected(tempId)
  }
  areAllSwatchesSelected() {
    return this.swatchingTabManager.areAllSwatchesSelected()
  }
  onToggleSelectAllSwatches(event) {
    this.swatchingTabManager.onToggleSelectAllSwatches(event)
    this.updateRecordOnChange()
  }
  onSwatchItemSelect(event, tempId) {
    this.swatchingTabManager.onSwatchItemSelect(event, tempId)
    this.updateRecordOnChange()
  }
  getSwatchServicePrice() {
    return this.swatchingTabManager.getSwatchServicePrice()
  }
  onSwatchServicePriceInput(event) {
    this.swatchingTabManager.onSwatchServicePriceInput(event)
    this.updateRecordOnChange()
  }
  onSwatchServicePriceCommit() {
    this.swatchingTabManager.onSwatchServicePriceCommit()
    this.updateRecordOnChange()
  }

  // --- Development Tab Handlers (delegated to DevelopmentTabManager) ---
  getProductItems() {
    return this.developmentTabManager.getProductItems()
  }
  isDevelopmentItemSelected(itemId) {
    return this.developmentTabManager.isDevelopmentItemSelected(itemId)
  }
  onDevelopmentItemSelect(event, itemId) {
    this.developmentTabManager.onDevelopmentItemSelect(event, itemId)
    this.updateRecordOnChange()
  }
  areAllDevItemsSelected() {
    return this.developmentTabManager.areAllDevItemsSelected()
  }
  onToggleSelectAllDevItems(event) {
    this.developmentTabManager.onToggleSelectAllDevItems(event)
    this.updateRecordOnChange()
  }
  getDevelopmentPrice(itemId) {
    return this.developmentTabManager.getDevelopmentPrice(itemId)
  }
  onDevelopmentPriceInput(event, itemId) {
    this.developmentTabManager.onDevelopmentPriceInput(event, itemId)
    this.updateRecordOnChange()
  }
  onDevelopmentPriceCommit(itemId) {
    this.developmentTabManager.onDevelopmentPriceCommit(itemId)
    this.updateRecordOnChange()
  }

  // --- Reverse Engineering Tab Handlers (delegated to ReverseTabManager) ---
  getReverseItems() {
    return this.reverseTabManager.getReverseItems()
  }
  isReverseItemSelected(itemId) {
    return this.reverseTabManager.isReverseItemSelected(itemId)
  }
  onReverseItemSelect(event, itemId) {
    this.reverseTabManager.onReverseItemSelect(event, itemId)
    this.updateRecordOnChange()
  }
  areAllReverseItemsSelected() {
    return this.reverseTabManager.areAllReverseItemsSelected()
  }
  onToggleSelectAllReverseItems(event) {
    this.reverseTabManager.onToggleSelectAllReverseItems(event)
    this.updateRecordOnChange()
  }
  getReversePrice(itemId) {
    return this.reverseTabManager.getReversePrice(itemId)
  }
  onReversePriceInput(event, itemId) {
    this.reverseTabManager.onReversePriceInput(event, itemId)
    this.updateRecordOnChange()
  }
  onReversePriceCommit(itemId) {
    this.reverseTabManager.onReversePriceCommit(itemId)
    this.updateRecordOnChange()
  }

  // --- Grading Tab Handlers (delegated to GradingTabManager) ---
  getGradingItems() {
    return this.gradingTabManager.getGradingItems()
  }
  getGradingSizes(childId) {
    return this.gradingTabManager.getGradingSizes(childId)
  }
  addGradingItem() {
    this.gradingTabManager.addGradingItem()
    this.updateRecordOnChange()
  }
  removeGradingItem(tempId) {
    this.gradingTabManager.removeGradingItem(tempId)
    this.updateRecordOnChange()
  }
  onGradingFieldChange(event, tempId, field) {
    this.gradingTabManager.onGradingFieldChange(event, tempId, field)
    this.updateRecordOnChange()
  }
  onGradingItemSelect(event, productId) {
    this.gradingTabManager.onGradingItemSelect(event, productId);
    this.updateRecordOnChange();
  }
  addGradingSize(tempId) {
    console.log('tempId', tempId);
    this.gradingTabManager.addGradingSize(tempId)
    this.updateRecordOnChange()
  }
  removeGradingSize(tempId, sizeIndex) {
    this.gradingTabManager.removeGradingSize(tempId, sizeIndex)
    this.updateRecordOnChange()
  }
  onGradingSizeChange(event, tempId, sizeIndex) {
    this.gradingTabManager.onGradingSizeChange(event, tempId, sizeIndex)
    this.updateRecordOnChange()
  }
  isGradingItemSelected(tempId) {
    return this.gradingTabManager.isGradingItemSelected(tempId)
  }
  areAllGradesSelected() {
    return this.gradingTabManager.areAllGradesSelected()
  }
  onToggleSelectAllGrades(event) {
    this.gradingTabManager.onToggleSelectAllGrades(event)
    this.updateRecordOnChange()
  }
  onGradingPricePerGradeInput(event) {
    this.gradingTabManager.onGradingPricePerGradeInput(event)
    this.updateRecordOnChange()
  }
  onGradingPricePerGradeCommit() {
    this.gradingTabManager.onGradingPricePerGradeCommit()
    this.updateRecordOnChange()
  }
  getGradingPricePerGrade() {
    return this.gradingTabManager.getGradingPricePerGrade()
  }

  // --- Production Tab Handlers (delegated to ProductionTabManager) ---
  // Production tab now uses grid-based UI with quantity/price inputs per cell
  // Grid cell handlers are in the template directly

  // --- Helper functions (delegated to utils/helpers.js) ---
  formatCurrency(amount) {
    return formatCurrency(amount)
  }
  isServiceSelected(serviceName) {
    return isServiceSelected(serviceName, this.state)
  }
  isServiceTypeSelected(serviceType) {
    return isServiceTypeSelected(serviceType, this.state)
  }

  // ===== Production Grid Methods =====

  async loadProductionGrid() {
    if (!this.props.record || !this.props.record.resId) {
      return
    }
    await this.productionTabManager.loadProductionGrid(this.props.record.resId)
  }

  async onProductionTabActive() {
    // Load grid when production tab becomes active
    await this.loadProductionGrid()
  }

  async createProductsForProduction() {
    if (!this.props.record || !this.props.record.resId) {
      return
    }
    try {
      await this.productionTabManager.createProductsForProduction(this.props.record.resId)
      this.notification.add("Products created successfully!", { type: "success" })
    } catch (error) {
      this.notification.add("Error creating products: " + error.message, { type: "danger" })
    }
  }

  onProductionGridCellChange(productId, sizeId, colorwayId, field, event) {
    const value = event.target.value
    this.productionTabManager.onGridCellChange(productId, sizeId, colorwayId, field, value)
  }

  getProductionGridCellValue(productId, sizeId, colorwayId, field) {
    return this.productionTabManager.getGridCellValue(productId, sizeId, colorwayId, field)
  }

  getProductRowspan(product) {
    return this.productionTabManager.getProductRowspan(product)
  }

  async saveProductionGrid() {
    if (!this.props.record || !this.props.record.resId) {
      return
    }
    try {
      const result = await this.productionTabManager.saveProductionGrid(this.props.record.resId)
      if (result) {
        this.notification.add("Production grid saved successfully!", { type: "success" })
      }
    } catch (error) {
      console.error("Error saving production grid:", error)
      this.notification.add("Error saving production grid: " + error.message, { type: "danger" })
    }
  }

  async generateQuoteFromProductionGrid() {
    if (!this.props.record || !this.props.record.resId) {
      return
    }

    try {
      // Save grid first
      await this.saveProductionGrid()

      // Generate quote
      const action = await this.productionTabManager.generateQuoteFromGrid(this.props.record.resId)

      if (action && typeof action === "object" && action.type) {
        await this.actionService.doAction(action)
      } else if (action && action.params) {
        // Notification action
        this.notification.add(action.params.message, { type: action.params.type || "info" })
      }
    } catch (error) {
      console.error("Error generating quote from grid:", error)
      this.notification.add("Error generating quote: " + error.message, { type: "danger" })
    }
  }

  async generatePricesFromCost() {
    if (!this.props.record || !this.props.record.resId) {
      return
    }
    try {
      const result = await this.productionTabManager.generatePricesFromCost(this.props.record.resId)
      if (result && result.params) {
        this.notification.add(result.params.message, { type: result.params.type || "success" })
      }
      // Reload the production grid so updated prices are visible
      await this.loadProductionGrid()
    } catch (error) {
      console.error("Error generating prices from cost:", error)
      this.notification.add("Error generating prices: " + error.message, { type: "danger" })
    }
  }

  hasProductionGridData() {
    return (
      this.state.formData.productionGrid &&
      this.state.formData.productionGrid.has_products &&
      this.state.formData.productionGrid.products &&
      this.state.formData.productionGrid.products.length > 0
    )
  }

  openSalesOrder(orderId) {
    if (!orderId) {
      return
    }
    this.actionService.doAction({
      type: "ir.actions.act_window",
      res_model: "sale.order",
      res_id: orderId,
      views: [[false, "form"]],
      target: "current",
    })
  }

  async openVariantWizard(productId) {
    if (!this.props.record || !this.props.record.resId) {
      return
    }
    try {
      const action = await this.orm.call("crm.lead", "action_open_variant_wizard", [[this.props.record.resId], productId])
      if (action && action.type) {
        await this.actionService.doAction(action, {
          onClose: async () => {
            // Reload production grid after wizard closes
            await this.productionTabManager.loadProductionGrid(this.props.record.resId)
          },
        })
      }
    } catch (error) {
      console.error("Error opening variant wizard:", error)
      this.notification.add("Error opening variant wizard: " + error.message, { type: "danger" })
    }
  }

  _applyProductionGridData(result) {
    // Must be called from within the component to ensure OWL reactive state update triggers re-render
    if (result && result !== false) {
      this.state.formData.productionGrid = {
        products: result.products || [],
        has_products: result.has_products || false,
        all_colorways: result.all_colorways || [],
        all_sizes: result.all_sizes || [],
        grid_data: result.grid_data || {},
        currency_symbol: result.currency_symbol || '$',
        is_dirty: false,
      }
    }
  }

  async removeProductFromProduction(productId) {
    if (!this.props.record || !this.props.record.resId) {
      return
    }
    try {
      const result = await this.productionTabManager.removeProductFromProduction(this.props.record.resId, productId)
      this._applyProductionGridData(result)
      this.notification.add("Product removed from production.", { type: "info" })
    } catch (error) {
      this.notification.add("Error removing product: " + error.message, { type: "danger" })
    }
  }

  // ===== Manual Product Search for Production Tab =====

  async onManualProductSearchInput(event) {
    const searchTerm = event.target.value
    this.state.searchState.manualProductSearch = searchTerm

    if (!searchTerm || searchTerm.trim().length < 1) {
      this.state.searchState.filteredManualProducts = []
      this.state.searchState.showManualProductDropdown = false
      return
    }

    if (!this.props.record || !this.props.record.resId) {
      return
    }

    try {
      const results = await this.productionTabManager.searchProductsForProduction(
        this.props.record.resId,
        searchTerm
      )
      this.state.searchState.filteredManualProducts = results
      this.state.searchState.showManualProductDropdown = results.length > 0
      this.state.searchState.selectedManualProductIndex = 0
    } catch (error) {
      console.error("Error searching products:", error)
      this.state.searchState.filteredManualProducts = []
      this.state.searchState.showManualProductDropdown = false
    }
  }

  onManualProductSearchBlur() {
    setTimeout(() => {
      this.state.searchState.showManualProductDropdown = false
    }, 200)
  }

  onManualProductHover(index) {
    this.state.searchState.selectedManualProductIndex = index
  }

  async selectManualProduct(productId, productName) {
    this.state.searchState.manualProductSearch = ""
    this.state.searchState.showManualProductDropdown = false
    this.state.searchState.filteredManualProducts = []

    if (!this.props.record || !this.props.record.resId) {
      return
    }

    try {
      const result = await this.productionTabManager.addProductToProduction(
        this.props.record.resId,
        productId
      )
      this._applyProductionGridData(result)
      if (result) {
        this.notification.add(`"${productName}" added to production.`, { type: "success" })
      }
    } catch (error) {
      console.error("Error adding product:", error)
      this.notification.add("Error adding product: " + error.message, { type: "danger" })
    }
  }
}

CrmLeadOwlWidget.template = "crm_lead_widget.CrmLeadWidget"
CrmLeadOwlWidget.props = {
  ...standardFieldProps,
  name: { type: String, optional: true },
  record: { type: Object, optional: true },
  tag_ids_widget: { type: String, optional: true },
  show_all_fields: { type: Boolean, optional: true },
  custom_title: { type: String, optional: true },
}
