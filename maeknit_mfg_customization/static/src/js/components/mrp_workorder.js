/** @odoo-module */

export async function fetchOperationNote(component) {
    if (!component.props.record || !component.props.record.resId) {
      return ""
    }
  
    try {
      const result = await component.props.record.model.orm.read(
        "mrp.workorder",
        [component.props.record.resId],
        ["operation_note"],
      )
      return result[0]?.operation_note || ""
    } catch (error) {
      console.error("Error fetching operation note:", error)
      return ""
    }
  }
  