/** @odoo-module */

import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog"
import DocumentViewer from "@mrp_workorder/components/viewer"

export class MrpProgramFilesDialog extends ConfirmationDialog {
    static props = {
    ...ConfirmationDialog.props,
    body: { optional: true },
    programFiles: [Array, Boolean],
    operationNote: Object,
  }

  static template = "mrp_workorder.MrpProgramFilesDialog"
  static components = {
    ...ConfirmationDialog.components,
    DocumentViewer,
  }
  downloadFile(attachment) {
    if (attachment.url) {
      window.open(attachment.url, "_blank")
    } else if (attachment.datas) {
      const link = document.createElement("a")
      link.href = `data:${attachment.mimetype};base64,${attachment.datas}`
      link.download = attachment.name
      link.click()
    }
  }
}
