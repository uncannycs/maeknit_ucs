/** @odoo-module **/

import { ProjectProjectListRenderer } from "@project/views/project_project_list/project_project_list_renderer"
import { patch } from "@web/core/utils/patch"

patch(ProjectProjectListRenderer.prototype, {
  /**
   * Override onCellClicked to change row click behavior for project list.
   * If a regular cell is clicked, open tasks. If a button is clicked, let the button handle it.
   * @override
   */
  async onCellClicked(record, column, ev) {
    // If a button was clicked, let the original method handle it.
    // This ensures the "View Project" button (which was originally "View Tasks") works as intended.
    if (ev.target.closest("button")) {
      return this._super.apply(this, arguments)
    }

    // If the record is in edition or multi-edit mode, let the original method handle it.
    // This preserves Odoo's inline editing behavior.
    if ((this.props.list.model.multiEdit && record.selected) || this.isInlineEditable(record)) {
      return this._super.apply(this, arguments)
    }

    // For all other regular cell clicks, open the tasks for the clicked project.
    // Ensure record.resId is used for database queries.
    if (!this.props.archInfo.noOpen) {
      // Only proceed if the record has a valid database ID
      if (record.resId) {
        await this.env.services.action.doAction({
          type: "ir.actions.act_window",
          res_model: "project.task",
          views: [
            [false, "list"],
            [false, "form"],
          ], // Prefer list view for tasks
          domain: [["project_id", "=", record.resId]], // Use record.resId here
          context: {
            default_project_id: record.resId, // Use record.resId here
            search_default_project_id: record.resId, // Use record.resId here
            group_by: "state",
            group_expand: true, // Added to expand groups by default
          },
          name: `Tasks for ${record.data.display_name}`,
        })
      } else {
        // Optionally, handle cases where record.resId is not available (e.g., new unsaved record)
        // For now, we'll just prevent the action to avoid the error.
        console.warn("Cannot open tasks for a record without a database ID (resId).")
      }
      return // Prevent the original method from being called for this case
    }

    // If none of the above conditions are met, fall back to the original method.
    return this._super.apply(this, arguments)
  },
})
