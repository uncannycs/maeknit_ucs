"use client"

/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl"
import { registry } from "@web/core/registry"
import { standardFieldProps } from "@web/views/fields/standard_field_props"
import { useRecordObserver } from "@web/model/relational_model/utils"
import { useService } from "@web/core/utils/hooks" // Import useService

export class MrpProductionOwlWidget extends Component {
  setup() {
    this.orm = useService("orm")
    this.state = useState({
      productName: "Loading Product Name...",
      samples: [], // Will hold either runs or swatches
      lastProductTmplId: false,
      lastRunId: false,
      lastSwatchId: false, // New state to track swatch_number_id
      lastProductCategory: false, // New state to track product_category
    })

    const loadAttributeData = async (record) => {
      if (record && record.data.product_id && record.data.product_tmpl_id) {
        const productTemplateId = record.data.product_tmpl_id[0]
        const productCategory = record.data.product_category
        this.state.productName = record.data.product_id[1] || "Unknown Product"

        let attributeValues = []
        try {
          if (productCategory === "garment") {
            const currentRunId = record.data.run_id ? record.data.run_id[0] : false
            attributeValues = await this.orm.call("mrp.production", "get_run_attributes_for_product_template", [
              productTemplateId,
              currentRunId,
            ])
          } else if (productCategory === "swatch") {
            const currentSwatchId = record.data.swatch_number_id ? record.data.swatch_number_id[0] : false
            attributeValues = await this.orm.call("mrp.production", "get_swatch_attributes_for_product_template", [
              productTemplateId,
              currentSwatchId,
            ])
          }
          this.state.samples = attributeValues
        } catch (error) {
          console.error("Error fetching attribute data:", error)
          this.state.samples = []
        }
      } else {
        this.state.productName = "No Product Selected"
        this.state.samples = []
      }
    }

    onWillStart(async () => {
      await loadAttributeData(this.props.record)
      this.state.lastProductTmplId = this.props.record.data.product_tmpl_id
        ? this.props.record.data.product_tmpl_id[0]
        : false
      this.state.lastRunId = this.props.record.data.run_id ? this.props.record.data.run_id[0] : false
      this.state.lastSwatchId = this.props.record.data.swatch_number_id
        ? this.props.record.data.swatch_number_id[0]
        : false
      this.state.lastProductCategory = this.props.record.data.product_category
    })

    useRecordObserver(async (record) => {
      const currentProductTmplId = record.data.product_tmpl_id ? record.data.product_tmpl_id[0] : false
      const currentRunId = record.data.run_id ? record.data.run_id[0] : false
      const currentSwatchId = record.data.swatch_number_id ? record.data.swatch_number_id[0] : false
      const currentProductCategory = record.data.product_category

      if (
        currentProductTmplId !== this.state.lastProductTmplId ||
        currentRunId !== this.state.lastRunId ||
        currentSwatchId !== this.state.lastSwatchId ||
        currentProductCategory !== this.state.lastProductCategory
      ) {
        this.state.lastProductTmplId = currentProductTmplId
        this.state.lastRunId = currentRunId
        this.state.lastSwatchId = currentSwatchId
        this.state.lastProductCategory = currentProductCategory
        await loadAttributeData(record)
      }
    })
  }
}

MrpProductionOwlWidget.template = "maeknit_mfg_customization.MrpProductionOwlWidget" // Corrected template name

MrpProductionOwlWidget.props = {
  ...standardFieldProps,
}

registry.category("view_widgets").add("mrp_production_owl_widget", {
  component: MrpProductionOwlWidget,
})
