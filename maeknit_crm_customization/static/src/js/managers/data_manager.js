/** @odoo-module **/

import { FormDataManager } from "../utils/form_data_manager"
import { formatDecimalDisplay, parseDecimalValue, safeErrorString } from "../utils/helpers"

export class DataManager {
  constructor(orm, notification, state, props) {
    this.orm = orm
    this.notification = notification
    this.state = state
    this.props = props // Keep a reference to props for record ID
  }

  async loadData() {
    try {
      this.state.debugInfo.lastAction = "loadData called"

      await this.fetchRelatedData()

      const isNew = this.checkIfNewRecord()
      this.state.debugInfo.lastMode =
        this.props.record && this.props.record.model ? this.props.record.model.root.mode : "unknown"
      this.state.isNewRecord = isNew

      if (isNew) {
        this.state.debugInfo.lastAction = "Initializing new record"
        this.initializeNewRecord()
      } else if (this.props.record && this.props.record.resId) {
        this.state.lastRecordId = this.props.record.resId
        await this.loadRecordData()
      }

      this.state.isLoading = false
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error during component initialization:", errorString)
      this.state.debugInfo.errors.push("Initialization error: " + errorString)
      this.state.isLoading = false
    }
  }

  async handleRecordChange(nextId, lastRecordId) {
    const isNew =
      !nextId ||
      nextId <= 0 ||
      (this.props.record && this.props.record.model && this.props.record.model.root.mode === "create")

    this.state.debugInfo.lastMode =
      this.props.record && this.props.record.model ? this.props.record.model.root.mode : "unknown"

    if (isNew) {
      console.log("Switching to a new record - initializing with default values")
      this.state.debugInfo.lastAction = "Switching to new record"
      this.state.isNewRecord = true
      this.initializeNewRecord()
    } else if (nextId) {
      this.state.debugInfo.lastAction = "Switching to existing record"
      this.state.isNewRecord = false
      this.state.lastRecordId = nextId
      await this.loadRecordData()
    }
  }

  initializeNewRecord() {
    this.state.formData = FormDataManager.getInitialFormData()
    this.state.formData.onboardingData.swatchPackage.expandedSwatches = [0]
    this.state.formData.activeTab =
      this.state.formData.x_project_type === "collection" ? "children" : "onboarding"
    this.state.searchState.userSearch = ""
    this.state.searchState.partnerSearch = ""
    this.state.searchState.productSearch = ""
    this.state.searchState.parentLeadSearch = ""
    this.state.searchState.companySearch = ""
    this.state.childOpportunitiesRows = []
    this.state.isChildOpportunitiesDirty = false
    this.state.selectedChildLeads = []
    this.state.formData.developmentData.selectedItems = []
    this.state.nextTempId = -1
    this.state.lastRecordId = null
    this.state.isDirty = false
    console.log("New record initialized with default values")
  }

  async fetchRelatedData() {
    try {
      const tags = await this.orm.call("crm.tag", "search_read", [[]], {
        fields: ["id", "name"],
      })
      this.state.availableTags = tags.map((tag) => [tag.id, tag.name])

      const users = await this.orm.call("res.users", "search_read", [[["share", "=", false]]], {
        fields: ["id", "name"],
      })
      this.state.availableUsers = users.map((user) => [user.id, user.name])
      this.state.searchState.filteredUsers = [...this.state.availableUsers].slice(0, 5)

      const partners = await this.orm.call("res.partner", "search_read", [], {
        fields: ["id", "name", "email"],
      })
      this.state.availablePartners = partners.map((partner) => [partner.id, partner.name, partner.email || ""])
      this.state.searchState.filteredPartners = [...this.state.availablePartners].slice(0, 5)

      const products = await this.orm.call("product.product", "search_read", [[]], {
        fields: ["id", "name", "list_price", "standard_price"],
      })
      this.state.availableProducts = products.map((product) => [
        product.id,
        product.name,
        product.list_price || 0,
        product.standard_price || 0,
      ])
      this.state.searchState.filteredProducts = [...this.state.availableProducts].slice(0, 5)

      const companies = await this.orm.call("res.company", "search_read", [[]], {
        fields: ["id", "name"],
      })
      this.state.availableCompanies = companies.map((company) => [company.id, company.name])
      this.state.searchState.filteredCompanies = [...this.state.availableCompanies].slice(0, 5)
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error fetching related data:", errorString)
      this.notification.add("Error loading form data", { type: "danger" })
      this.state.debugInfo.errors.push("Error fetching related data: " + errorString)
    }
  }

  async loadRecordData() {
    if (!this.props.record || !this.props.record.resId) {
      console.log("No record ID available")
      return
    }

    try {
      const recordId = this.props.record.resId
      let model = "crm.lead"

      try {
        if (this.props.record.model && this.props.record.model.root && this.props.record.model.root.resModel) {
          model = this.props.record.model.root.resModel
        }
      } catch (e) {
        console.error("Error getting model from record:", safeErrorString(e))
      }

      const recordData = await this.orm.call(model, "read", [[recordId]], {
        fields: [
          "name",
          "expected_revenue",
          "partner_id",
          "partner_name",
          "priority",
          "user_id",
          "tag_ids",
          "season_drop_date",
          "x_service_revenues",
          "x_onboarding_data",
          "x_gemini_notes",
          "x_service_revenues",
          "x_include_development_in_quote",
          "x_include_production_in_quote",
          "x_include_swatch_in_quote",
          "x_include_reverse_in_quote",
          "x_include_grading_in_quote",
          "parent_id",
          "product_ids",
          "child_ids",
          "company_id",
          "x_project_type",
          "style_family",
          "x_child_style_name",
          "x_selected_child_leads",
          "x_development_prices",
          "x_swatch_data",
          "x_grading_data",
          "x_reverse_data",
        ],
      })

      if (recordData && recordData.length > 0) {
        this.state.debugInfo.directFetchData = recordData[0]

        const formData = FormDataManager.getInitialFormData()
        formData.name = recordData[0].name || ""
        formData.expected_revenue = recordData[0].expected_revenue || 0
        formData.priority = recordData[0].priority || "0"
        formData.partner_name = recordData[0].partner_name || ""
        formData.season_drop_date = recordData[0].season_drop_date || ""
        formData.geminiNotes = recordData[0].x_gemini_notes || ""
        formData.x_include_development_in_quote = recordData[0].x_include_development_in_quote || false
        formData.x_include_production_in_quote = recordData[0].x_include_production_in_quote || false
        formData.x_include_swatch_in_quote = recordData[0].x_include_swatch_in_quote || false
        formData.x_include_reverse_in_quote = recordData[0].x_include_reverse_in_quote || false
        formData.x_include_grading_in_quote = recordData[0].x_include_grading_in_quote || false
        formData.child_ids = recordData[0].child_ids || []
        formData.x_project_type = recordData[0].x_project_type || "style"

        formData.activeTab = formData.x_project_type === "collection" ? "children" : "onboarding"

        // Fetch currency symbol
        try {
          const currencySymbol = await this.orm.call(model, "get_currency_symbol", [[recordId]])
          formData.currency_symbol = currencySymbol || "$"
        } catch (e) {
          console.error("Error fetching currency symbol:", safeErrorString(e))
          formData.currency_symbol = "$"
        }

        formData.x_selected_child_leads = recordData[0].x_selected_child_leads || "[]"
        try {
          this.state.selectedChildLeads = JSON.parse(formData.x_selected_child_leads)
          formData.developmentData.selectedItems = [...this.state.selectedChildLeads]
        } catch (e) {
          console.error("Error parsing x_selected_child_leads:", safeErrorString(e))
          this.state.selectedChildLeads = []
          formData.developmentData.selectedItems = []
        }

        if (recordData[0].x_swatch_data) {
          try {
            formData.swatchData = JSON.parse(recordData[0].x_swatch_data)
            if (formData.swatchData.items) {
              formData.swatchData.items.forEach((item) => {
                delete item.colorways
                delete item.price
              })
            }
            const parsedPrice =
              typeof formData.swatchData.servicePrice === "number"
                ? formData.swatchData.servicePrice
                : Number.parseFloat(formData.swatchData.servicePrice) || 0
            formData.swatchData.servicePrice = Number.isFinite(parsedPrice) ? parsedPrice : 0
            if (typeof formData.swatchData.servicePriceText !== "string") {
              formData.swatchData.servicePriceText = formData.swatchData.servicePrice.toFixed(2)
            }
          } catch (e) {
            const errorString = safeErrorString(e)
            console.error("Error parsing swatch data:", errorString)
            this.state.debugInfo.errors.push("Error parsing swatch data: " + errorString)
            formData.swatchData = FormDataManager.getInitialFormData().swatchData
          }
        }

        if (recordData[0].x_grading_data) {
          try {
            formData.gradingData = JSON.parse(recordData[0].x_grading_data)
          } catch (e) {
            const errorString = safeErrorString(e)
            console.error("Error parsing grading data:", errorString)
            this.state.debugInfo.errors.push("Error parsing grading data: " + errorString)
            formData.gradingData = FormDataManager.getInitialFormData().gradingData
          }
        }

        if (recordData[0].x_reverse_data) {
          try {
            formData.reverseData = JSON.parse(recordData[0].x_reverse_data)
            const priceMap = formData.reverseData.itemPrices || {}
            const numericMap = {}
            const textMap = {}
            Object.entries(priceMap).forEach(([key, value]) => {
              const numberValue = parseDecimalValue(value, 0)
              numericMap[key] = numberValue
              textMap[key] = formatDecimalDisplay(numberValue) || "0"
            })
            formData.reverseData.itemPrices = numericMap
            formData.reverseData.itemPriceTexts = textMap
          } catch (e) {
            const errorString = safeErrorString(e)
            console.error("Error parsing reverse data:", errorString)
            this.state.debugInfo.errors.push("Error parsing reverse data: " + errorString)
            formData.reverseData = FormDataManager.getInitialFormData().reverseData
          }
        }

        if (recordData[0].x_onboarding_data) {
          try {
            const parsedData = JSON.parse(recordData[0].x_onboarding_data)

            if (parsedData) {
              if (parsedData.general) {
                formData.onboardingData.general = {
                  ...formData.onboardingData.general,
                  ...parsedData.general,
                }

                if (!formData.onboardingData.general.rawMaterials) {
                  formData.onboardingData.general.rawMaterials = [formData.onboardingData.general.rawMaterial || ""]
                }
                if (!formData.onboardingData.general.colors) {
                  formData.onboardingData.general.colors = [formData.onboardingData.general.color || ""]
                }
                if (!formData.onboardingData.general.stitchConstructions) {
                  formData.onboardingData.general.stitchConstructions = [
                    formData.onboardingData.general.stitchConstruction || "",
                  ]
                }
              }

              if (parsedData.swatchPackage) {
                formData.onboardingData.swatchPackage = {
                  ...formData.onboardingData.swatchPackage,
                  ...parsedData.swatchPackage,
                }
              } else if (parsedData.services && parsedData.services["Swatch Packages"]) {
                formData.onboardingData.swatchPackage = {
                  numberOfSwatches: parsedData.services["Swatch Packages"].numberOfSwatches || 3,
                  swatches: parsedData.services["Swatch Packages"].swatches || [
                    { material: "", gauge: "", stitch: "", colorway: "" },
                    { material: "", gauge: "", stitch: "", colorway: "" },
                    { material: "", gauge: "", stitch: "", colorway: "" },
                    { material: "", gauge: "", stitch: "", colorway: "" },
                  ],
                }
              }

              if (parsedData.production) {
                formData.onboardingData.production = {
                  ...formData.onboardingData.production,
                  ...parsedData.production,
                }
              } else if (parsedData.services && parsedData.services["Production"]) {
                formData.onboardingData.production = {
                  colorways: parsedData.services["Production"].colorways || ["", "", ""],
                  sizes: parsedData.services["Production"].sizes || ["", ""],
                  budgetPerStyle: parsedData.services["Production"].budgetPerStyle || 0,
                  units: parsedData.services["Production"].units || 0,
                  countryOfProduction: parsedData.services["Production"].countryOfProduction || "",
                }
              }
            }
          } catch (e) {
            const errorString = safeErrorString(e)
            console.error("Error parsing onboarding data:", errorString)
            this.state.debugInfo.errors.push("Error parsing onboarding data: " + errorString)
            formData.service_revenues = {}
          }
        }

        if (recordData[0].x_development_prices) {
          try {
            const parsedMap = JSON.parse(recordData[0].x_development_prices)
            const numericMap = {}
            const textMap = {}
            Object.entries(parsedMap || {}).forEach(([key, value]) => {
              const numberValue = parseDecimalValue(value, 0)
              numericMap[key] = numberValue
              textMap[key] = formatDecimalDisplay(numberValue) || "0"
            })
            formData.developmentData.itemPrices = numericMap
            formData.developmentData.itemPriceTexts = textMap
          } catch (e) {
            const errorString = safeErrorString(e)
            console.error("Error parsing development prices:", errorString)
            this.state.debugInfo.errors.push("Error parsing development prices: " + errorString)
            formData.developmentData.itemPrices = {}
            formData.developmentData.itemPriceTexts = {}
          }
        } else {
          formData.developmentData.itemPrices = {}
          formData.developmentData.itemPriceTexts = {}
        }

        if (recordData[0].parent_id) {
          if (Array.isArray(recordData[0].parent_id)) {
            formData.parent_id = recordData[0].parent_id
            this.state.searchState.parentLeadSearch = recordData[0].parent_id[1] || ""
          } else {
            const parentId = recordData[0].parent_id
            try {
              const parentData = await this.orm.call("crm.lead", "read", [[parentId]], {
                fields: ["id", "name"],
              })
              if (parentData && parentData.length > 0) {
                formData.parent_id = [parentData[0].id, parentData[0].name]
                this.state.searchState.parentLeadSearch = parentData[0].name || ""
              }
            } catch (e) {
              const errorString = safeErrorString(e)
              console.error("Error fetching specific parent:", errorString)
              this.state.debugInfo.errors.push("Error fetching specific parent: " + errorString)
            }
          }
        }

        if (recordData[0].company_id) {
          if (Array.isArray(recordData[0].company_id)) {
            formData.company_id = recordData[0].company_id
            this.state.searchState.companySearch = recordData[0].company_id[1] || ""
          } else {
            const companyId = recordData[0].company_id
            const company = this.state.availableCompanies.find((c) => c[0] === companyId)
            formData.company_id = company || [companyId, `Company ${companyId}`]
            this.state.searchState.companySearch = formData.company_id[1] || ""
          }
        }

        if (recordData[0].partner_id) {
          if (Array.isArray(recordData[0].partner_id)) {
            formData.partner_id = recordData[0].partner_id
            this.state.searchState.partnerSearch = recordData[0].partner_id[1] || ""

            try {
              const partnerData = await this.orm.call("res.partner", "read", [[recordData[0].partner_id[0]]], {
                fields: ["email"],
              })
              if (partnerData && partnerData.length > 0) {
                formData.email = partnerData[0].email || ""
              }
            } catch (e) {
              const errorString = safeErrorString(e)
              console.error("Error fetching partner email:", errorString)
              this.state.debugInfo.errors.push("Error fetching partner email: " + errorString)
            }
          } else {
            const partnerId = recordData[0].partner_id

            let partner = this.state.availablePartners.find((p) => p[0] === partnerId)

            if (!partner) {
              try {
                const partnerData = await this.orm.call("res.partner", "read", [[partnerId]], {
                  fields: ["id", "name", "email"],
                })
                if (partnerData && partnerData.length > 0) {
                  partner = [partnerData[0].id, partnerData[0].name, partnerData[0].email || ""]
                  formData.email = partnerData[0].email || ""
                }
              } catch (e) {
                const errorString = safeErrorString(e)
                console.error("Error fetching specific partner:", errorString)
                this.state.debugInfo.errors.push("Error fetching specific partner: " + errorString)
              }
            } else {
              formData.email = partner[2] || ""
            }

            formData.partner_id = partner || [partnerId, recordData[0].partner_name || `Partner ${partnerId}`, ""]
            this.state.searchState.partnerSearch = formData.partner_id[1] || ""
          }
        }

        if (recordData[0].user_id) {
          if (Array.isArray(recordData[0].user_id)) {
            formData.user_id = recordData[0].user_id
            this.state.searchState.userSearch = recordData[0].user_id[1] || ""
          } else {
            const userId = recordData[0].user_id
            const user = this.state.availableUsers.find((u) => u[0] === userId)
            formData.user_id = user || [userId, `User ${userId}`]
            this.state.searchState.userSearch = formData.user_id[1] || ""
          }
        }

        if (recordData[0].product_ids && recordData[0].product_ids.length > 0) {
          try {
            const productData = await this.orm.call("crm.lead.product", "read", [recordData[0].product_ids], {
              fields: ["id", "product_id", "quantity", "price", "cost"],
            })

            formData.product_ids = productData.map((product) => {
              const productId = Array.isArray(product.product_id) ? product.product_id[0] : product.product_id
              const productName = Array.isArray(product.product_id) ? product.product_id[1] : `Product ${productId}`
              return [product.id, productId, productName, product.quantity, product.price, product.cost]
            })
          } catch (e) {
            const errorString = safeErrorString(e)
            console.error("Error fetching product data:", errorString)
            this.state.debugInfo.errors.push("Error fetching product data: " + errorString)
          }
        }

        if (recordData[0].child_ids && recordData[0].child_ids.length > 0) {
          await this.fetchChildOpportunities()
        } else {
          this.state.childOpportunitiesRows = []
        }

        if (recordData[0].tag_ids && recordData[0].tag_ids.length > 0) {
          formData.tag_ids = recordData[0].tag_ids.map((tagId) => {
            const foundTag = this.state.availableTags.find((tag) => tag[0] === tagId)
            return foundTag || [tagId, `Tag ${tagId}`]
          })
        }

        let hasServiceRevenues = false
        let totalServiceRevenue = 0
        if (recordData[0].x_service_revenues) {
          try {
            formData.service_revenues = JSON.parse(recordData[0].x_service_revenues) || {}
            Object.values(formData.service_revenues).forEach((value) => {
              const numValue = Number.parseFloat(value) || 0
              totalServiceRevenue += numValue
              if (numValue > 0) {
                hasServiceRevenues = true
              }
            })
          } catch (e) {
            const errorString = safeErrorString(e)
            console.error("Error parsing service revenues:", errorString)
            this.state.debugInfo.errors.push("Error parsing service revenues: " + errorString)
            formData.service_revenues = {}
          }
        }
        if (
          recordData[0].expected_revenue > 0 &&
          (!hasServiceRevenues || Math.abs(totalServiceRevenue - recordData[0].expected_revenue) > 0.01)
        ) {
          formData.hasExistingRevenue = true

          if (formData.tag_ids && formData.tag_ids.length > 0) {
            const firstTagId = formData.tag_ids[0][0].toString()
            formData.service_revenues[firstTagId] = recordData[0].expected_revenue
            formData.hasExistingRevenue = false
          }
        }

        if (formData.tag_ids && formData.tag_ids.length > 0) {
          formData.tag_ids.forEach((tag) => {
            const tagId = tag[0].toString()
            if (!formData.service_revenues[tagId]) {
              formData.service_revenues[tagId] = 0
            }
          })
        }

        this.state.formData = formData
        console.log("Form data after direct load:", this.state.formData)
      }
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error loading record data directly:", errorString)
      this.state.debugInfo.errors.push("Error loading record data: " + errorString)
    }
  }

  async fetchChildOpportunities() {
    if (!this.props.record || !this.props.record.resId) {
      this.state.childOpportunitiesRows = []
      console.log("DEBUG: fetchChildOpportunities - No record or resId, clearing childOpportunitiesRows.")
      return
    }
    try {
      const parentData = await this.orm.call("crm.lead", "read", [[this.props.record?.resId]], {
        fields: ["id", "name", "child_ids"],
      })
      const childList = parentData[0]?.child_ids || []
      const childIds = Array.isArray(childList) ? childList.filter((id) => typeof id === "number") : []

      if (childIds.length === 0) {
        this.state.childOpportunitiesRows = []
        console.log("DEBUG: fetchChildOpportunities - No child IDs to fetch, clearing childOpportunitiesRows.")
        return
      }

      const idsDesc = [...childIds].reverse();
      const childData = await this.orm.call("crm.lead", "read", [idsDesc], {
        fields: ["id","name","expected_revenue","partner_id","tag_ids","style_family","x_child_style_name"],
      });

      this.state.childOpportunitiesRows = childData.map((child) => ({
        tempId: child.id,
        id: child.id,
        name: child.name,
        x_child_style_name: child.x_child_style_name || "",
        style_family: child.style_family,
      }))
      this.state.isChildOpportunitiesDirty = false
    } catch (e) {
      const errorString = safeErrorString(e)
      console.error("Error fetching child opportunities:", errorString)
      this.state.debugInfo.errors.push("Error fetching child opportunities: " + errorString)
    }
  }

  async fetchRelatedSalesOrders(tabName = null) {
    if (!this.props.record || !this.props.record.resId) {
      this.state.relatedSalesOrders = []
      return
    }

    try {
      const domain = [
        ["opportunity_id", "=", this.props.record.resId],
        ["state", "in", ["draft", "sent", "sale", "done"]],
      ]
      const serviceTypeMap = {
        development: "development",
        swatching: "swatch",
        reverse: "reverse",
        grading: "grading",
        production: "production",
      }
      const serviceType = serviceTypeMap[tabName] || null
      if (serviceType) {
        domain.push(["x_rel_services", "ilike", serviceType])
      }

      const salesOrders = await this.orm.call("sale.order", "search_read", [domain], {
        fields: ["id", "name", "state", "amount_total", "date_order", "partner_id", "x_quoted_style_families", "x_rel_services"],
        order: "date_order desc",
      })

      this.state.relatedSalesOrders = salesOrders.map((order) => {
        const stateMap = {
          draft: "Draft",
          sent: "Quotation Sent",
          sale: "Sales Order",
          done: "Locked",
          cancel: "Cancelled",
        }
        return {
          ...order,
          state_display: stateMap[order.state] || order.state,
          date_order: order.date_order ? new Date(order.date_order).toLocaleDateString() : "",
        }
      })
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error fetching related sales orders:", errorString)
      this.state.debugInfo.errors.push("Error fetching related sales orders: " + errorString)
      this.state.relatedSalesOrders = []
    }
  }

  checkIfNewRecord() {
    const noRecord = !this.props.record
    const noResId = this.props.record && !this.props.record.resId
    const zeroResId = this.props.record && this.props.record.resId <= 0
    const isCreate =
      this.props.record &&
      this.props.record.model &&
      this.props.record.model.root &&
      this.props.record.model.root.mode === "create"

    const createContext =
      this.props.record && this.props.record.context && this.props.record.context.form_view_initial_mode === "create"

    console.log("New record check details:", {
      noRecord,
      noResId,
      zeroResId,
      isCreate,
      createContext,
      props: this.props,
    })

    return noRecord || noResId || zeroResId || isCreate || createContext
  }
}
