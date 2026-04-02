/** @odoo-module **/

import { registry } from "@web/core/registry"
import { CrmLeadOwlWidget } from "./components/crm_lead_widget"

// Register the widget in Odoo's registry
registry.category("view_widgets").add("crm_lead_owl_widget", {
  component: CrmLeadOwlWidget,
})

export default CrmLeadOwlWidget
