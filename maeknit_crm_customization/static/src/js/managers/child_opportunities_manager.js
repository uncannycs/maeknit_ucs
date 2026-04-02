/** @odoo-module **/

import { safeErrorString } from "../utils/helpers"
import { DataManager } from "../managers/data_manager"

export class ChildOpportunitiesManager {
  constructor(orm, notification, state, props) {
    this.orm = orm
    this.notification = notification
    this.state = state
    this.props = props // To access record.resId
    this.dataManager = new DataManager(this.orm, this.notification, this.state, this.props)

  }

  async addChildOpportunityRow(freshParentId = null) {
    // Use the passed fresh parent ID or fall back to props.record.resId
    const parentId = freshParentId || (this.props.record ? this.props.record.resId : null)

    if (!parentId) {
      this.notification.add("Please save the main record first before adding child opportunities", { type: "warning" })
      return
    }

    const parentPartnerId = this.state.formData.partner_id ? this.state.formData.partner_id[0] : false
    const childName = `Garment ${this.state.childOpportunitiesRows.length + 1}`

    try {
      // Create the child lead — Python create() auto-generates style_family
      const childData = {
        name: childName,
        parent_id: parentId,
        partner_id: parentPartnerId,
        type: "opportunity",
        x_project_type: "style",
      }

      const createResult = await this.orm.create("crm.lead", [childData])
      const newChildId = Array.isArray(createResult) ? createResult[0] : createResult

      // Read back the auto-generated style_family from server
      const created = await this.orm.read("crm.lead", [newChildId], ["style_family"])
      const styleFamily = created.length ? created[0].style_family : ""

      const newRow = {
        tempId: this.state.nextTempId--,
        id: newChildId,
        name: childName,
        x_child_style_name: styleFamily,
        style_family: styleFamily,
      }

      // Add to the end of the array to ensure it appears at the bottom
      this.state.childOpportunitiesRows.push(newRow)

      this.notification.add("Child opportunity created successfully", { type: "success" })
      this.state.record.save()
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error creating child opportunity:", errorString)
      this.notification.add(`Error creating child opportunity: ${error.message || errorString}`, { type: "danger" })
      this.state.debugInfo.errors.push(`Child opportunity creation error: ${errorString}`)
      return
    }

    this.state.isChildOpportunitiesDirty = false // Set to false since we just saved
    this.state.isDirty = true
  }

  onChildFieldChange(event, tempId, fieldName) {
    if (fieldName === "name") {
      const value = event.target.value
      const row = this.state.childOpportunitiesRows.find((r) => r.tempId === tempId)
      if (row) {
        row[fieldName] = value
        this.state.isChildOpportunitiesDirty = true
        this.state.isDirty = true
      }
    }
  }

  async deleteChildOpportunity(tempId, childId) {
    if (!confirm("Are you sure you want to delete this child opportunity?")) return;

    // Optimistic UI (keep a copy for rollback)
    const prevRows = [...this.state.childOpportunitiesRows];
    const prevSelected = [...this.state.selectedChildLeads];

    this.state.childOpportunitiesRows = prevRows.filter(r => r.tempId !== tempId);
    this.state.selectedChildLeads = prevSelected.filter(id => id !== childId);
    this.state.isChildOpportunitiesDirty = true;
    this.state.isDirty = true;

    // Nothing else to do if it was a not-yet-saved row
    if (!childId) return;

    try {
      const leadId = this.props.record?.resId || null;

      // Preflight: make sure record still exists & (optionally) still linked to this lead
      const recs = await this.orm.searchRead(
        "crm.lead",
        [["id", "=", childId]],
        ["id", "parent_id"],
        { limit: 1 }
      );

      if (!recs.length) {
        // Already gone elsewhere; treat as success
        this.notification.add("Child opportunity was already removed.", { type: "warning" });
        return;
      }

      if (leadId && recs[0].parent_id && recs[0].parent_id[0] !== leadId) {
        // No longer belongs to this parent; remove locally and inform
        this.notification.add("Child no longer belongs to this lead; removed from list.", { type: "info" });
        return;
      }

      // Delete on server
      await this.orm.unlink("crm.lead", [childId]);
      this.notification.add("Child opportunity deleted successfully", { type: "success" });
    } catch (error) {
      const msg = safeErrorString(error);
      console.error("Error deleting child opportunity:", msg);

      // Roll back optimistic UI
      this.state.childOpportunitiesRows = prevRows;
      this.state.selectedChildLeads = prevSelected;

      this.notification.add(`Error deleting child opportunity: ${error.message || msg}`, { type: "danger" });
      this.state.debugInfo.errors.push(`Child opportunity deletion error: ${msg}`);
      return;
    } finally {
      // Sync from server so the list is 100% accurate
      try {
        await this.dataManager.fetchChildOpportunities();
      } catch (e) {
        console.warn("Refresh after delete failed:", safeErrorString(e));
      }
    }
  }

  async saveChildOpportunitiesInternal() {
    if (!this.props.record || !this.props.record.resId) {
      return false
    }

    const parentId = this.props.record.resId
    const parentPartnerId = this.state.formData.partner_id ? this.state.formData.partner_id[0] : false

    try {
      for (const row of this.state.childOpportunitiesRows) {
        if (row.id === null) {
          if (row.name.trim() === "") {
            continue
          }
          // New row — Python create() will auto-generate style_family
          const data = {
            name: row.name,
            parent_id: parentId,
            partner_id: parentPartnerId,
            type: "opportunity",
            x_project_type: "style",
          }
          const createResult = await this.orm.create("crm.lead", [data])
          const newId = Array.isArray(createResult) ? createResult[0] : createResult
          row.id = newId

          // Read back auto-generated style_family
          const created = await this.orm.read("crm.lead", [newId], ["style_family"])
          if (created.length) {
            row.style_family = created[0].style_family
            row.x_child_style_name = created[0].style_family
          }
        } else {
          // Existing row — only update name, never overwrite style_family
          await this.orm.write("crm.lead", [row.id], {
            name: row.name,
            parent_id: parentId,
            partner_id: parentPartnerId,
          })
        }
      }

      this.state.isChildOpportunitiesDirty = false
      return true
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error saving child opportunities:", errorString)
      this.state.debugInfo.errors.push(`Child opportunities save error: ${errorString}`)
      return false
    }
  }

  async saveChildOpportunities() {
    if (!this.props.record || !this.props.record.resId) {
      this.notification.add("Please save the main record first before saving child opportunities", { type: "warning" })
      return
    }

    this.state.isLoading = true

    try {
      const success = await this.saveChildOpportunitiesInternal()

      if (success) {
        this.notification.add("Child opportunities saved successfully", { type: "success" })
      } else {
        this.notification.add("Error saving some child opportunities", { type: "danger" })
      }
    } catch (error) {
      const errorString = safeErrorString(error)
      this.notification.add(`Error saving child opportunities: ${error.message || errorString}`, {
        type: "danger",
      })
    } finally {
      this.state.isLoading = false
    }
  }
}
