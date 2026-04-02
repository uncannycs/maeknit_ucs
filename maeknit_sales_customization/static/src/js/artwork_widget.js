/** @odoo-module **/

import { Component, useState } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { registry } from "@web/core/registry"
import { standardFieldProps } from "@web/views/fields/standard_field_props"

export class ArtworkWidget extends Component {
  static template = "artwork_widget.ArtworkWidget"
  static props = {
    ...standardFieldProps,
  }

  setup() {
    this.orm = useService("orm")

    const rawValue = this.props.record?.data?.[this.props.name]
    let parsed = null
    if (rawValue) {
      try {
        parsed = typeof rawValue === "string" ? JSON.parse(rawValue) : rawValue
      } catch (e) {
        console.error("ArtworkWidget: error parsing data:", e)
      }
    }

    this.state = useState({
      items: parsed?.items?.length ? parsed.items : [{ filename: null, data: null, mimeType: null, notes: "" }],
    })
  }

  addItem() {
    this.state.items.push({ filename: null, data: null, mimeType: null, notes: "" })
  }

  removeItem(index) {
    if (this.state.items.length === 1) {
      this.state.items[0] = { filename: null, data: null, mimeType: null, notes: "" }
    } else {
      this.state.items.splice(index, 1)
    }
    this._save()
  }

  triggerFileInput(index) {
    const input = document.querySelector(`[data-artwork-input="${index}"]`)
    if (input) input.click()
  }

  handleFileUpload(index, event) {
    const file = event.target.files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (e) => {
      this.state.items[index].filename = file.name
      this.state.items[index].data = e.target.result
      this.state.items[index].mimeType = file.type || "application/octet-stream"
      this._save()
    }
    reader.readAsDataURL(file)
  }

  removeFile(index) {
    this.state.items[index].filename = null
    this.state.items[index].data = null
    this.state.items[index].mimeType = null
    this._save()
  }

  downloadFile(index) {
    const item = this.state.items[index]
    if (!item.data && !item.attachment_id) return
    const a = document.createElement("a")
    // Use /web/content for proper file download when stored as attachment
    a.href = item.attachment_id ? `/web/content/${item.attachment_id}` : item.data
    a.download = item.filename || "artwork_file"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  updateNotes(index, value) {
    this.state.items[index].notes = value
    this._save()
  }

  _save() {
    const data = JSON.stringify({ items: this.state.items })
    if (this.props.record && this.props.name) {
      this.props.record.update({ [this.props.name]: data })
    }
  }
}

registry.category("fields").add("artwork_widget", {
  component: ArtworkWidget,
  supportedTypes: ["json", "text", "char"],
})

export default ArtworkWidget
