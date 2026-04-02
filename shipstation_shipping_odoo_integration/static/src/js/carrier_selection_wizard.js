"use client"

/** @odoo-module **/

import { Component, useState } from "@odoo/owl"
import { registry } from "@web/core/registry"
import { useService } from "@web/core/utils/hooks"

const STORAGE_KEY = "shipstation_carrier_selection_ids"

const safeParseInt = (value) => {
  const parsed = Number.parseInt(value)
  return Number.isNaN(parsed) ? undefined : parsed
}

const readStoredIds = () => {
  if (typeof window === "undefined") {
    return {}
  }
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEY)
    if (!stored) {
      return {}
    }
    return JSON.parse(stored)
  } catch (error) {
    console.warn("Unable to read stored wizard IDs:", error)
    return {}
  }
}

const readHashIds = () => {
  if (typeof window === "undefined" || !window.location.hash) {
    return {}
  }
  const params = new URLSearchParams(window.location.hash.substring(1))
  return {
    wizardId: safeParseInt(params.get("wizard_id")),
    pickingId: safeParseInt(params.get("picking_id")),
    packageId: safeParseInt(params.get("package_id")),
  }
}

const storeIds = (wizardId, pickingId, packageId) => {
  if (typeof window === "undefined" || !wizardId || !pickingId) {
    return
  }
  try {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ wizardId, pickingId, packageId }),
    )
  } catch (error) {
    console.warn("Unable to store wizard IDs:", error)
  }
}

class CarrierSelectionWizard extends Component {
  setup() {
    // Ensure hooks are called at the top level
    this.orm = useService("orm")
    this.action = useService("action")

    this.state = useState({
      step: "select_carriers",
      selectedCarriers: new Set(["combined"]),
      loading: false,
      rates: [],
      selectedRate: null,
      error: null,
      groupedRates: {},
      residential: false,
      pickingSummary: null,
    })

    this.activeAction = null

    const params = this.props.action?.params || {}
    this.wizardId = params.wizard_id
    this.pickingId = params.picking_id || params.active_id
    this.packageId = params.package_id

    if (!this.wizardId || !this.pickingId) {
      const stored = readStoredIds()
      this.wizardId ||= stored.wizardId
      this.pickingId ||= stored.pickingId
      this.packageId ||= stored.packageId
    }

    if (!this.wizardId || !this.pickingId) {
      const hash = readHashIds()
      this.wizardId ||= hash.wizardId
      this.pickingId ||= hash.pickingId
      this.packageId ||= hash.packageId
    }

    storeIds(this.wizardId, this.pickingId, this.packageId)

    console.log("Component setup - wizardId:", this.wizardId, "pickingId:", this.pickingId)
    console.log("Full props:", this.props)
    console.log("Action params:", this.props.action?.params)

    this.loadPickingSummary = this.loadPickingSummary.bind(this)
    this.toggleCarrier = this.toggleCarrier.bind(this)
    this.isCarrierSelected = this.isCarrierSelected.bind(this)
    this.fetchRates = this.fetchRates.bind(this)
    this.selectRate = this.selectRate.bind(this)
    this.applySelectedRate = this.applySelectedRate.bind(this)
    this.confirmSelection = this.confirmSelection.bind(this)
    this.generateLabel = this.generateLabel.bind(this)
    this.toggleResidential = this.toggleResidential.bind(this)
    this.closeWizard = this.closeWizard.bind(this)
    this.ensureShipstationOrder = this.ensureShipstationOrder.bind(this)
    this.back = this.back.bind(this)
    this.loadPickingSummary()
  }

  toggleCarrier(carrier) {
    const newCarriers = new Set(this.state.selectedCarriers)

    if (carrier === "combined") {
      newCarriers.clear()
      newCarriers.add("combined")
    } else {
      newCarriers.delete("combined")
      if (newCarriers.has(carrier)) {
        newCarriers.delete(carrier)
      } else {
        newCarriers.add(carrier)
      }
      if (newCarriers.size === 0) {
        newCarriers.add("combined")
      }
    }

    this.state.selectedCarriers = newCarriers
  }

  isCarrierSelected(carrier) {
    return this.state.selectedCarriers.has(carrier)
  }

  async fetchRates() {
    console.log("fetchRates called")
    console.log("wizardId:", this.wizardId)
    console.log("pickingId:", this.pickingId)
    console.log("selectedCarriers:", Array.from(this.state.selectedCarriers))

    if (!this.wizardId || !this.pickingId) {
      this.state.error = "Missing wizard or picking ID. Please try again."
      console.error("Missing IDs - wizardId:", this.wizardId, "pickingId:", this.pickingId)
      return
    }

    this.state.loading = true
    this.state.error = null

    const residential = this.state.residential
    try {
      const carriers = Array.from(this.state.selectedCarriers)
      console.log("Updating wizard with carriers:", carriers)

      const isCombined = carriers.includes("combined")

      // Get the carrier IDs from the carrier codes
      let carrierIds = []
      if (!isCombined) {
        const carrierRecords = await this.orm.searchRead(
          "shipstation.delivery.carrier",
          [["code", "in", carriers]],
          ["id"],
        )
        carrierIds = carrierRecords.map((c) => c.id)
      }

      await this.orm.write("shipstation.carrier.selection.wizard", [this.wizardId], {
        fetch_mode: isCombined ? "combined" : "specific",
        selected_carrier_ids: [[6, 0, carrierIds]], // Many2many write format
      })

      console.log("Calling action_fetch_rates")
      const result = await this.orm.call(
        "shipstation.carrier.selection.wizard",
        "action_fetch_rates",
        [this.wizardId],
        { residential },
      )
      console.log("action_fetch_rates result:", result)

      // Fetch the rates
      console.log("Fetching rates for picking:", this.pickingId)
      const rates = await this.orm.searchRead(
        "shipstation.shipping.charge",
        [["picking_id", "=", this.pickingId]],
        [
          "shipstation_service_name",
          "shipping_cost",
          "other_cost",
          "shipstation_provider",
          "shipstation_service_code",
          "id",
        ],
      )
      console.log("Rates fetched:", rates.length, rates)

      this.state.rates = rates
      this.groupRatesByCarrier()
      console.log("Grouped rates:", this.state.groupedRates)
      this.state.step = "view_rates"
      console.log("Changed step to view_rates")
    } catch (error) {
      console.error("Error in fetchRates:", error)
      this.state.error = error.message || "Failed to fetch rates"
    } finally {
      this.state.loading = false
      console.log("fetchRates completed, loading:", this.state.loading)
    }
  }

  async loadPickingSummary() {
    if (!this.pickingId) {
      return
    }

    try {
      const summary = await this.orm.call(
        "stock.picking",
        "get_shipstation_label_summary",
        [this.pickingId],
        this.packageId ? { context: { shipstation_package_id: this.packageId } } : {},
      )
      this.state.pickingSummary = summary
    } catch (error) {
      console.error("Unable to load picking summary:", error)
    }
  }

  groupRatesByCarrier() {
    const grouped = {}
    this.state.rates.forEach((rate) => {
      const carrier = rate.shipstation_provider || "other"
      if (!grouped[carrier]) {
        grouped[carrier] = []
      }
      grouped[carrier].push(rate)
    })

    // Sort rates within each carrier by cost
    Object.keys(grouped).forEach((carrier) => {
      grouped[carrier].sort((a, b) => a.shipping_cost - b.shipping_cost)
    })

    this.state.groupedRates = grouped
  }

  selectRate(rate) {
    this.state.selectedRate = rate
  }

  async applySelectedRate() {
    const rateId = this.state.selectedRate?.id
    if (!rateId) {
      throw new Error("Please select a shipping rate before continuing.")
    }
    await this.orm.call("shipstation.shipping.charge", "set_picking_service", [rateId])
  }

  async ensureShipstationOrder() {
    try {
      await this.orm.call("stock.picking", "ensure_shipstation_order", [this.pickingId])
    } catch (error) {
      throw new Error(error.message || "Unable to create ShipStation order")
    }
  }

  async confirmSelection() {
    if (!this.state.selectedRate) {
      this.state.error = "Select a rate before applying."
      return
    }

    this.activeAction = "apply"
    this.state.loading = true
    this.state.error = null
    try {
      await this.applySelectedRate()
      await this.action.doAction({ type: "ir.actions.act_window_close" })
    } catch (error) {
      this.state.error = error.message || "Failed to select rate"
      console.error("Error applying rate:", error)
    } finally {
      this.state.loading = false
      this.activeAction = null
    }
  }

  async generateLabel() {
    if (!this.state.selectedRate) {
      this.state.error = "Select a rate before generating a label."
      return
    }

    this.activeAction = "label"
    this.state.loading = true
    this.state.error = null

    try {
      await this.ensureShipstationOrder()
      await this.applySelectedRate()
      const labelAction = await this.orm.call("stock.picking", "generate_label_from_shipstation", [this.pickingId])
      if (labelAction) {
        await this.action.doAction(labelAction)
      }
      await this.action.doAction({ type: "ir.actions.act_window_close" })
    } catch (error) {
      this.state.error = error.message || "Failed to generate ShipStation label"
      console.error("Error generating label:", error)
    } finally {
      this.state.loading = false
      this.activeAction = null
    }
  }

  toggleResidential(value) {
    this.state.residential = value
  }

  closeWizard() {
    if (window && window.history && window.history.length > 1) {
      window.history.back()
      return
    }
    this.action.doAction({ type: "ir.actions.act_window_close" })
  }

  get isApplying() {
    return this.activeAction === "apply"
  }

  get isGeneratingLabel() {
    return this.activeAction === "label"
  }

  back() {
    this.state.step = "select_carriers"
    this.state.error = null
  }

  getCarrierDisplayName(carrier) {
    const names = {
      stamps_com: "USPS (Stamps.com)",
      ups_walleted: "UPS",
      fedex_walleted: "FedEx",
      other: "Other Carriers",
    }
    return names[carrier] || carrier
  }

  getCarrierColor(carrier) {
    const colors = {
      stamps_com: "#004B87",
      ups_walleted: "#351C15",
      fedex_walleted: "#FF6600",
      other: "#6c757d",
    }
    return colors[carrier] || "#6c757d"
  }
}

CarrierSelectionWizard.template = "shipstation_shipping_integration_vts.CarrierSelectionWizard"

registry.category("actions").add("carrier_selection_wizard", CarrierSelectionWizard)
