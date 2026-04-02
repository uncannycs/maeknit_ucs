/** @odoo-module **/

import { patch } from "@web/core/utils/patch"
import { MrpWorksheet } from "@mrp_workorder/mrp_display/mrp_record_line/mrp_worksheet"

patch(MrpWorksheet.prototype, {
  async onProgramClick(ev) {
    console.log(" Program Files clicked via patch")
    ev.preventDefault()
    ev.stopPropagation()

    const workorderId = this.props.record?.resId
    console.log(" Work order ID:", workorderId)

    if (!workorderId) return

    const { action } = this.env.services

    try {
      await action.doAction({
        type: "ir.actions.act_window",
        name: "Program Files Viewer",
        res_model: "mrp.program.files.wizard",
        view_mode: "form",
        views: [[false, "form"]],
        target: "new",
        context: {
          default_workorder_id: workorderId,
        },
      })
    } catch (error) {
      console.error(" Error opening program files wizard:", error)
    }
  },
  async onDownloadAllClick(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    console.log(" Download all PDFs");
  
    const workorderId = this.props.record?.resId;
    if (!workorderId) return;
  
    try {
      // Call backend method via ORM service
      const attachments = await this.env.services.orm.call(
        "mrp.workorder",
        "get_program_attachments_list",
        [workorderId]
      );
      
      for (const att of attachments) {
        const url = `/web/content/${att.id}?download=true`;
        const link = document.createElement("a");
        link.href = url;
        link.download = att.name || `attachment_${att.id}.pdf`; // ensure a filename
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    } catch (error) {
      console.error(" Error downloading PDFs:", error);
    }
  }
  
  
})

console.log(" MrpWorksheet patch applied successfully")
