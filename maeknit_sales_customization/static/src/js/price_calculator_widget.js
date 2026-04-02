"use client"

/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { registry } from "@web/core/registry"
import { Dialog } from "@web/core/dialog/dialog"

export class PriceCalculatorWidget extends Component {
  static template = "price_calculator_widget.PriceCalculatorWidget"
  static components = { Dialog }
  static props = {
    close: { type: Function, optional: true },
    action: { type: Object, optional: true },
  }

  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.actionService = useService("action")
    this.dialog = useService("dialog")

    this.state = useState({
      operations: [],
      materialCost: 0,
      marginPercent: 60,
      shippingCost: 0,
      totalCost: 0,
      relatedService: null,
      relatedServiceId: null,
      company: null,
      companyId: null,
      isUkCompany: false,
      isLoading: true,
      availableOperations: [],
      availableWorkcenters: [],
      availableEmployees: [],
      filteredWorkcenters: {},
    })

    const context = this.props.action?.context || {}
    this.saleOrderLineId = context.sale_order_line_id
    this.pricingId = context.pricing_id

    console.log("Widget initialized with line:", this.saleOrderLineId, "pricing:", this.pricingId)
    console.log("Full action:", this.props.action)
    console.log("Full context:", context)

    onWillStart(async () => {
      await this.loadData()
    })
  }

  async loadData() {
    const saleOrderLineId = this.saleOrderLineId
    const pricingId = this.pricingId

    console.log("Loading pricing data for line:", saleOrderLineId, "pricing:", pricingId)

    if (!saleOrderLineId) {
      console.error("No sale order line ID provided")
      this.notification.add("Invalid sale order line ID", { type: "danger" })
      this.state.isLoading = false
      return
    }

    try {
      console.log("Fetching line data...")
      const lineData = await this.orm.read("sale.order.line", [saleOrderLineId], ["rel_service", "order_id"])
      console.log("Line data:", lineData)

      if (lineData && lineData.length > 0) {
        this.state.relatedService = lineData[0].rel_service
        this.state.relatedServiceId = lineData[0].rel_service ? lineData[0].rel_service[0] : null
        console.log("Related service:", this.state.relatedService)

        if (lineData[0].order_id && lineData[0].order_id[0]) {
          console.log("Fetching order data...")
          const orderData = await this.orm.read("sale.order", [lineData[0].order_id[0]], ["company_id"])
          console.log("Order data:", orderData)
          if (orderData && orderData.length > 0) {
            this.state.company = orderData[0].company_id
            this.state.companyId = orderData[0].company_id ? orderData[0].company_id[0] : null
            this.state.isUkCompany = this.state.company
              ? this.state.company[1].toLowerCase().includes('uk')
              : false
            console.log("Company:", this.state.company, "isUkCompany:", this.state.isUkCompany)
          }
        }
      }

      console.log("Loading employees and workcenters filtered by company:", this.state.companyId)
      const [employees, workcenters] = await Promise.all([
        this.orm.searchRead("hr.employee", this.state.companyId ? [["company_id", "=", this.state.companyId]] : [], [
          "id",
          "name",
          "hourly_cost",
        ]),
        this.orm.searchRead("mrp.workcenter", this.state.companyId ? [["company_id", "=", this.state.companyId]] : [], [
          "id",
          "name",
          "costs_hour",
          "tag_ids",
        ]),
      ])

      this.state.availableEmployees = employees
      this.state.availableWorkcenters = workcenters
      this.outsourceWorkcenter = workcenters.find(
        (wc) => wc.name.toLowerCase() === 'outsource'
      ) || null
      console.log("Loaded employees:", employees.length, "workcenters:", workcenters.length,
        "outsource WC:", this.outsourceWorkcenter ? this.outsourceWorkcenter.name : 'not found')

      if (pricingId && pricingId > 0) {
        console.log("Loading existing pricing data...")
        const pricingData = await this.orm.read(
          "sale.order.line.pricing",
          [pricingId],
          ["material_cost", "margin_percentage", "shipping_cost", "operation_ids"],
        )

        if (pricingData && pricingData.length > 0) {
          this.state.materialCost = pricingData[0].material_cost || 0
          this.state.marginPercent = pricingData[0].margin_percentage || 0
          this.state.shippingCost = pricingData[0].shipping_cost || 0

          console.log(
            "Loaded pricing - Material:",
            this.state.materialCost,
            "Margin:",
            this.state.marginPercent,
            "Shipping:",
            this.state.shippingCost,
          )

          if (pricingData[0].operation_ids && pricingData[0].operation_ids.length > 0) {
            console.log("Loading operations...")
            const operations = await this.orm.read("sale.order.line.pricing.operation", pricingData[0].operation_ids, [
              "sequence",
              "operation_id",
              "workcenter_id",
              "employee_id",
              "expected_minutes",
              "hourly_rate",
              "workcenter_cost_per_hour",
              "total_cost",
              "is_outsourced",
              "outsource_amount",
            ])

            const validOperations = operations.filter((op) => {
              if (!op.operation_id || !op.operation_id[0]) {
                console.log("Skipping operation with no ID")
                return false
              }
              return true
            })

            this.state.operations = validOperations.sort((a, b) => a.sequence - b.sequence)
            console.log("Loaded existing operations:", validOperations.length)

            // Restore outsource WC reference for outsourced ops (they were saved with workcenter=false)
            for (const op of this.state.operations) {
              if (op.is_outsourced && this.outsourceWorkcenter) {
                op.workcenter_id = [this.outsourceWorkcenter.id, this.outsourceWorkcenter.name]
              }
            }

            for (let i = 0; i < this.state.operations.length; i++) {
              const op = this.state.operations[i]
              if (op.operation_id) {
                const filteredWCs = this.filterWorkcentersByOperation(op.operation_id[0])
                this.state.filteredWorkcenters[i] = filteredWCs
              }
            }
          }
        }
      }

      console.log("Loading available operations...")
      await this.loadAvailableOperations()
      console.log("Available operations:", this.state.availableOperations.length)

      if (this.state.operations.length === 0) {
        console.log("No existing operations, loading from template...")
        await this.loadOperationsFromTemplate()
        console.log("Loaded operations from template:", this.state.operations.length)
      }

      this.calculateTotal()
      this.state.isLoading = false
      console.log("Data loading complete. Total:", this.state.totalCost)
    } catch (error) {
      console.error("Error loading data:", error)
      this.notification.add(`Failed to load pricing data: ${error.message}`, { type: "danger" })
      this.state.isLoading = false
    }
  }

  async loadAvailableOperations() {
    try {
      let serviceType = null
      if (this.state.relatedService) {
        const serviceName = this.state.relatedService[1]
        if (serviceName.includes("Development")) {
          serviceType = "development"
        } else if (serviceName.includes("Grading")) {
          serviceType = "grading"
        } else if (serviceName.includes("Production")) {
          serviceType = "production"
        }
      }

      console.log("Service type detected:", serviceType)

      if (!serviceType) {
        this.state.availableOperations = []
        return
      }

      const domain = this.state.companyId ? [["company_id", "=", this.state.companyId]] : []

      const allOperations = await this.orm.searchRead("maeknit.shopfloor.operation", domain, [
        "id",
        "name",
        "workcenter_tag_ids",
      ])

      this.state.availableOperations = allOperations.map((op) => {
        console.log(`Operation "${op.name}" has tags:`, op.workcenter_tag_ids)
        return {
          ...op,
          displayName: op.name.replace(/\s+V\d+$/i, ""),
        }
      })

      console.log("Loaded available operations:", this.state.availableOperations.length)
    } catch (error) {
      console.error("Error loading operations:", error)
    }
  }

  async loadOperationsFromTemplate() {
    try {
      let serviceType = null
      if (this.state.relatedService) {
        const serviceName = this.state.relatedService[1]
        if (serviceName.includes("Development")) {
          serviceType = "development"
        } else if (serviceName.includes("Grading")) {
          serviceType = "grading"
        } else if (serviceName.includes("Production")) {
          serviceType = "production"
        }
      }

      console.log("Loading template for service:", serviceType, "company:", this.state.companyId)

      if (!serviceType || !this.state.companyId) {
        console.log("Cannot load template - missing service type or company")
        return
      }

      const domain = [
        ["related_service", "=", serviceType],
        ["company_id", "=", this.state.companyId],
      ]

      const templates = await this.orm.searchRead("maeknit.bom.operation.template", domain, ["line_ids"], { limit: 1 })

      console.log("Found templates:", templates.length)

      if (templates.length > 0 && templates[0].line_ids && templates[0].line_ids.length > 0) {
        const templateLines = await this.orm.read("maeknit.bom.operation.template.line", templates[0].line_ids, [
          "operation_id",
          "user_ids",
          "sequence",
        ])

        console.log("Template lines:", templateLines.length)

        let sequence = 10
        for (const line of templateLines.sort((a, b) => a.sequence - b.sequence)) {
          const operation = this.state.availableOperations.find((op) => op.id === line.operation_id[0])

          if (!operation) {
            console.log("Operation not found for template line:", line.operation_id)
            continue
          }

          console.log(`Loading template operation: "${operation.displayName}"`)

          let employeeId = null
          let hourlyRate = 30
          if (line.user_ids && line.user_ids.length > 0) {
            const employee = this.state.availableEmployees.find((emp) => emp.id === line.user_ids[0])
            if (employee) {
              employeeId = [employee.id, employee.name]
              hourlyRate = employee.hourly_cost || 30
              console.log(`  Employee: ${employee.name} @ $${hourlyRate}/hr`)
            }
          }

          let workcenterData = null
          let workcenterCost = 0

          if (operation.workcenter_tag_ids && operation.workcenter_tag_ids.length > 0) {
            console.log(`  Operation tags:`, operation.workcenter_tag_ids)
            const matchingWCs = this.state.availableWorkcenters.filter(
              (wc) => wc.tag_ids && wc.tag_ids.some((tag) => operation.workcenter_tag_ids.includes(tag)),
            )

            console.log(`  Found ${matchingWCs.length} matching workcenters`)

            if (matchingWCs.length > 0) {
              const firstWC = matchingWCs[0]
              workcenterData = [firstWC.id, firstWC.name]
              workcenterCost = firstWC.costs_hour || 0
              console.log(`  Auto-selected workcenter: ${firstWC.name} @ $${workcenterCost}/hr`)

              // Store filtered workcenters for this operation
              const currentIndex = this.state.operations.length
              this.state.filteredWorkcenters[currentIndex] = matchingWCs
            } else {
              console.log(`  No matching workcenters found for operation tags`)
            }
          } else {
            console.log(`  No tags on operation, cannot filter workcenters`)
          }

          const newOp = {
            id: `new_${Date.now()}_${sequence}`,
            sequence: sequence,
            operation_id: [operation.id, operation.displayName],
            workcenter_id: workcenterData,
            employee_id: employeeId,
            expected_minutes: 0,
            hourly_rate: hourlyRate,
            workcenter_cost_per_hour: workcenterCost,
            is_outsourced: false,
            outsource_amount: 0,
            total_cost: 0,
          }

          this.state.operations.push(newOp)
          sequence += 10
        }
      }
    } catch (error) {
      console.error("Error loading template operations:", error)
    }
  }

  addOperation() {
    const newOp = {
      id: `new_${Date.now()}`,
      sequence: (this.state.operations.length + 1) * 10,
      operation_id: null,
      workcenter_id: null,
      employee_id: null,
      expected_minutes: 0,
      hourly_rate: 30,
      workcenter_cost_per_hour: 0,
      is_outsourced: false,
      outsource_amount: 0,
      total_cost: 0,
    }
    this.state.operations.push(newOp)
  }

  removeOperation(index) {
    this.state.operations.splice(index, 1)
    this.calculateTotal()
  }

  filterWorkcentersByOperation(operationId) {
    if (!operationId) {
      console.log("No operation ID provided for filtering")
      return this.state.availableWorkcenters
    }

    const operation = this.state.availableOperations.find((op) => op.id === operationId)

    if (!operation) {
      console.log("Operation not found:", operationId)
      return this.state.availableWorkcenters
    }

    console.log(`Filtering workcenters for operation "${operation.displayName}" (ID: ${operationId})`)
    console.log("Operation tags:", operation.workcenter_tag_ids)

    if (!operation.workcenter_tag_ids || operation.workcenter_tag_ids.length === 0) {
      console.log("No tags found for operation, returning all workcenters")
      return this.state.availableWorkcenters
    }

    const operationTags = operation.workcenter_tag_ids

    const filtered = this.state.availableWorkcenters.filter((wc) => {
      console.log(`Checking workcenter "${wc.name}" with tags:`, wc.tag_ids)
      if (!wc.tag_ids || wc.tag_ids.length === 0) {
        return false
      }
      const hasMatch = operationTags.some((tag) => wc.tag_ids.includes(tag))
      console.log(`Workcenter "${wc.name}" matches:`, hasMatch)
      return hasMatch
    })

    // Always include OUTSOURCE work center for UK company, regardless of operation tags
    if (this.state.isUkCompany && this.outsourceWorkcenter && !filtered.find((wc) => wc.id === this.outsourceWorkcenter.id)) {
      filtered.push(this.outsourceWorkcenter)
    }

    console.log(
      `Filtered workcenters for "${operation.displayName}":`,
      filtered.length,
      "of",
      this.state.availableWorkcenters.length,
    )
    filtered.forEach((wc) => console.log(`  - ${wc.name}`))

    return filtered
  }

  updateOperation(index, field, value) {
    const op = this.state.operations[index]

    if (field === "operation_id") {
      const operation = this.state.availableOperations.find((o) => o.id === Number.parseInt(value))
      op.operation_id = operation ? [operation.id, operation.displayName] : null

      if (operation) {
        console.log(`Operation changed to "${operation.displayName}" at index ${index}`)

        const filteredWCs = this.filterWorkcentersByOperation(operation.id)
        this.state.filteredWorkcenters[index] = filteredWCs
        console.log("Updated filtered workcenters for index:", index, "count:", filteredWCs.length)

        if (filteredWCs.length > 0) {
          const firstWC = filteredWCs[0]
          op.workcenter_id = [firstWC.id, firstWC.name]
          op.workcenter_cost_per_hour = firstWC.costs_hour || 0
          console.log("Auto-selected first workcenter:", firstWC.name, "cost:", firstWC.costs_hour)
        } else {
          op.workcenter_id = null
          op.workcenter_cost_per_hour = 0
          console.log("No matching workcenters found for operation, cleared selection")
        }
      } else {
        this.state.filteredWorkcenters[index] = this.state.availableWorkcenters
      }
    } else if (field === "workcenter_id") {
      const selectedId = Number.parseInt(value)
      const isOutsource = this.outsourceWorkcenter && selectedId === this.outsourceWorkcenter.id
      if (isOutsource) {
        op.is_outsourced = true
        op.workcenter_id = [this.outsourceWorkcenter.id, this.outsourceWorkcenter.name]
        op.workcenter_cost_per_hour = 0
        console.log("Outsource workcenter selected for operation at index:", index)
      } else {
        op.is_outsourced = false
        op.outsource_amount = 0
        const wc = this.state.availableWorkcenters.find((w) => w.id === selectedId)
        op.workcenter_id = wc ? [wc.id, wc.name] : null
        op.workcenter_cost_per_hour = wc ? wc.costs_hour || 0 : 0
        console.log("Workcenter manually changed to:", wc?.name, "cost:", wc?.costs_hour)
      }
    } else if (field === "employee_id") {
      const emp = this.state.availableEmployees.find((e) => e.id === Number.parseInt(value))
      op.employee_id = emp ? [emp.id, emp.name] : null
      if (emp && emp.hourly_cost) {
        op.hourly_rate = emp.hourly_cost
        console.log("Employee changed, hourly rate updated to:", emp.hourly_cost)
      }
    } else {
      op[field] = Number.parseFloat(value) || 0
    }

    this.calculateOperationCost(op)
    this.calculateTotal()
  }

  updateOperationTime(index, value) {
    const op = this.state.operations[index]
    op.expected_minutes = Number.parseFloat(value) || 0
    this.calculateOperationCost(op)
    this.calculateTotal()
  }

  updateOperationEmployee(index, employeeId) {
    const op = this.state.operations[index]
    op.employee_id = employeeId
    const employee = this.state.availableEmployees.find((e) => e.id === employeeId)
    op.hourly_rate = employee ? employee.hourly_cost : 0
    console.log("Updated employee for operation", index, "New rate:", op.hourly_rate)
    this.calculateOperationCost(op)
    this.calculateTotal()
  }

  updateOperationWorkcenter(index, workcenterId) {
    const op = this.state.operations[index]
    op.workcenter_id = workcenterId
    const workcenter = this.state.availableWorkcenters.find((w) => w.id === workcenterId)
    op.workcenter_cost_per_hour = workcenter ? workcenter.costs_hour : 0
    console.log("Updated workcenter for operation", index, "New cost/hour:", op.workcenter_cost_per_hour)
    this.calculateOperationCost(op)
    this.calculateTotal()
  }

  updateOperationName(index, operationId) {
    const op = this.state.operations[index]
    const operation = this.state.availableOperations.find((o) => o.id === operationId)

    if (operation) {
      op.operation_id = [operation.id, operation.displayName]
      op.operation_name = operation.name
      op.operation_tags = operation.workcenter_tag_ids || []

      console.log("Operation changed to:", operation.name, "with tags:", op.operation_tags)

      const filteredWorkcenters = this.getFilteredWorkcentersForOperation(index)
      if (filteredWorkcenters.length > 0) {
        op.workcenter_id = [filteredWorkcenters[0].id, filteredWorkcenters[0].name]
        op.workcenter_cost_per_hour = filteredWorkcenters[0].costs_hour
        console.log("Auto-selected workcenter:", filteredWorkcenters[0].name)
      }

      this.calculateOperationCost(op)
      this.calculateTotal()
    }
  }

  calculateOperationCost(op) {
    if (op.is_outsourced) {
      op.total_cost = Math.round(op.outsource_amount || 0)
    } else {
      const hours = op.expected_minutes / 60.0
      const laborCost = hours * op.hourly_rate
      const workcenterCost = hours * (op.workcenter_cost_per_hour || 0)
      op.total_cost = Math.round(laborCost + workcenterCost)
    }
  }

  updateOutsourceAmount(index, value) {
    const op = this.state.operations[index]
    op.outsource_amount = Number.parseFloat(value) || 0
    this.calculateOperationCost(op)
    this.calculateTotal()
  }

  updateMaterialCost(value) {
    this.state.materialCost = Number.parseFloat(value) || 0
    this.calculateTotal()
  }

  updateMarginPercent(value) {
    this.state.marginPercent = Number.parseFloat(value) || 0
    this.calculateTotal()
  }

  updateShippingCost(value) {
    this.state.shippingCost = Number.parseFloat(value) || 0
    this.calculateTotal()
  }

  calculateTotal() {
    const operationsTotal = this.state.operations.reduce((sum, op) => sum + (op.total_cost || 0), 0)
    const material = Math.round(this.state.materialCost || 0)
    const shipping = Math.round(this.state.shippingCost || 0)

    const subtotal = operationsTotal + material
    const marginAmount = Math.round(subtotal * ((this.state.marginPercent || 0) / 100))
    this.state.totalCost = subtotal + marginAmount + shipping
  }

  async saveAndConfirm() {
    const pricingId = this.pricingId
    const saleOrderLineId = this.saleOrderLineId

    for (const op of this.state.operations) {
      if (!op.operation_id) {
        this.notification.add("All operations must have an operation name selected", { type: "warning" })
        return
      }
      if (!op.employee_id) {
        this.notification.add("All operations must have an assigned person", { type: "warning" })
        return
      }
      if (!op.workcenter_id && !op.is_outsourced) {
        this.notification.add("All operations must have a work center selected", { type: "warning" })
        return
      }
    }

    try {
      await this.orm.write("sale.order.line.pricing", [pricingId], {
        material_cost: this.state.materialCost,
        margin_percentage: this.state.marginPercent,
        shipping_cost: this.state.shippingCost,
      })

      const existingOps = await this.orm.searchRead(
        "sale.order.line.pricing.operation",
        [["pricing_id", "=", pricingId]],
        ["id"],
      )
      if (existingOps.length > 0) {
        await this.orm.unlink(
          "sale.order.line.pricing.operation",
          existingOps.map((op) => op.id),
        )
      }

      for (const op of this.state.operations) {
        await this.orm.create("sale.order.line.pricing.operation", [
          {
            pricing_id: pricingId,
            sequence: op.sequence,
            operation_id: op.operation_id ? op.operation_id[0] : false,
            workcenter_id: op.workcenter_id ? op.workcenter_id[0] : false,
            employee_id: op.employee_id ? op.employee_id[0] : false,
            expected_minutes: op.is_outsourced ? 0 : op.expected_minutes,
            hourly_rate: op.hourly_rate,
            is_outsourced: op.is_outsourced || false,
            outsource_amount: op.outsource_amount || 0,
          },
        ])
      }

      await this.orm.write("sale.order.line", [this.saleOrderLineId], {
        price_unit: Math.round(this.state.totalCost || 0),
      })

      this.notification.add("Pricing saved successfully", { type: "success" })

      this.closeDialog()
    } catch (error) {
      console.error("Error saving pricing:", error)
      this.notification.add(`Failed to save pricing data: ${error.message}`, { type: "danger" })
    }
  }

  async applyToAll() {
    const saleOrderLineId = this.saleOrderLineId

    try {
      await this.saveCurrentPricing()

      await this.orm.call("sale.order.line", "action_apply_pricing_to_all", [[saleOrderLineId]])

      this.notification.add("Pricing applied to all matching lines", { type: "success" })

      this.closeDialog()
    } catch (error) {
      console.error("Error applying to all:", error)
      this.notification.add("Failed to apply pricing to all lines", { type: "danger" })
    }
  }

  async saveCurrentPricing() {
    const pricingId = this.pricingId

    await this.orm.write("sale.order.line.pricing", [pricingId], {
      material_cost: this.state.materialCost,
      margin_percentage: this.state.marginPercent,
      shipping_cost: this.state.shippingCost,
    })

    const existingOps = await this.orm.searchRead(
      "sale.order.line.pricing.operation",
      [["pricing_id", "=", pricingId]],
      ["id"],
    )
    if (existingOps.length > 0) {
      await this.orm.unlink(
        "sale.order.line.pricing.operation",
        existingOps.map((op) => op.id),
      )
    }

    for (const op of this.state.operations) {
      await this.orm.create("sale.order.line.pricing.operation", [
        {
          pricing_id: pricingId,
          sequence: op.sequence,
          operation_id: op.operation_id ? op.operation_id[0] : false,
          workcenter_id: op.is_outsourced ? false : (op.workcenter_id ? op.workcenter_id[0] : false),
          employee_id: op.employee_id ? op.employee_id[0] : false,
          expected_minutes: op.is_outsourced ? 0 : op.expected_minutes,
          hourly_rate: op.hourly_rate,
          is_outsourced: op.is_outsourced || false,
          outsource_amount: op.outsource_amount || 0,
        },
      ])
    }

    await this.orm.write("sale.order.line", [this.saleOrderLineId], {
      price_unit: Math.round(this.state.totalCost || 0),
    })
  }

  closeDialog() {
    if (this.props.close) {
      this.props.close()
    } else {
      this.actionService.doAction({ type: "ir.actions.act_window_close" })
    }
  }

  getFilteredWorkcentersForOperation(index) {
    const op = this.state.operations[index]

    if (!op || !op.operation_id || !op.operation_id[0]) {
      console.log(`getFilteredWorkcentersForOperation(${index}): No operation selected, showing all workcenters`)
      return this.state.availableWorkcenters
    }

    // Check if we already have filtered workcenters cached for this index
    if (this.state.filteredWorkcenters[index]) {
      console.log(
        `getFilteredWorkcentersForOperation(${index}): Using cached filtered list (${this.state.filteredWorkcenters[index].length} workcenters)`,
      )
      return this.state.filteredWorkcenters[index]
    }

    // Otherwise filter now
    const filtered = this.filterWorkcentersByOperation(op.operation_id[0])
    this.state.filteredWorkcenters[index] = filtered
    console.log(
      `getFilteredWorkcentersForOperation(${index}): Filtered and cached (${filtered.length} workcenters)`,
    )
    return filtered
  }

  formatCurrency(value) {
    const symbol = this.state.isUkCompany ? '£' : '$'
    return `${symbol}${Math.round(value || 0)}`
  }

  handleKeyDown(event, rowIndex, columnType) {
    if (event.key === "Enter") {
      event.preventDefault()

      const nextRowIndex = rowIndex + 1

      // Check if there's a next row
      if (nextRowIndex < this.state.operations.length) {
        // Find the input/select in the next row for the same column
        const nextInput = document.querySelector(`[data-row="${nextRowIndex}"][data-column="${columnType}"]`)

        if (nextInput) {
          nextInput.focus()
        }
      }
    }
  }
}

registry.category("actions").add("price_calculator_widget", PriceCalculatorWidget)
