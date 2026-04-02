/** @odoo-module **/

import { registry } from "@web/core/registry"

registry.category("actions").add("download_attachments", async (env, action) => {
  const attachmentIds = action.params.attachment_ids || []
  const attachmentNames = action.params.attachment_names || []

  if (attachmentIds.length === 0) {
    console.log("No attachments to download")
    return
  }

  // Download each attachment sequentially with a delay
  for (let i = 0; i < attachmentIds.length; i++) {
    const attachmentId = attachmentIds[i]
    const attachmentName = attachmentNames[i] || `file_${i}`

    const url = `/web/content/${attachmentId}?download=true`
    const link = document.createElement("a")
    link.href = url
    link.download = attachmentName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)

    // Wait 500ms before downloading the next file
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
})
