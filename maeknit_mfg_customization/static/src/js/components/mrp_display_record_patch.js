"use client"

/** @odoo-module **/

import { patch } from "@web/core/utils/patch"
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record"
import { useState, onWillStart } from "@odoo/owl"

patch(MrpDisplayRecord.prototype, {
  setup() {
    super.setup()

    this.filesState = useState({
      programFiles: [],
      instructionFiles: [],
      isLoading: true,
    })

    onWillStart(async () => {
      if (this.resModel === "mrp.workorder") {
        console.log(" MrpDisplayRecord setup - Full record data:", this.props.record.data)
        console.log(" knit_attempt value:", this.props.record.data.knit_attempt)
        console.log(" program_version value:", this.props.record.data.program_version)
        console.log(" Record fields available:", Object.keys(this.props.record.data))

        if (this.props.record.data.knit_attempt === undefined || this.props.record.data.program_version === undefined) {
          console.log(" Custom fields missing, attempting to reload with explicit fields...")
          try {
            const workorderId = this.props.record.resId
            const fullRecord = await this.model.orm.read(
              "mrp.workorder",
              [workorderId],
              ["knit_attempt", "program_version"],
            )
            if (fullRecord && fullRecord.length > 0) {
              console.log(" Reloaded record data:", fullRecord[0])
              // Update the record data with the missing fields
              this.props.record.data.knit_attempt = fullRecord[0].knit_attempt
              this.props.record.data.program_version = fullRecord[0].program_version
              console.log(
                " Updated record with knit_attempt:",
                this.props.record.data.knit_attempt,
                "program_version:",
                this.props.record.data.program_version,
              )
            }
          } catch (error) {
            console.error(" Error reloading record with custom fields:", error)
          }
        }

        await this.loadAttachments()
      }
    })
  },

  async loadAttachments() {
    try {
      const workorderId = this.props.record.resId

      console.log(" Loading attachments for workorder ID:", workorderId)

      const programFiles = await this.model.orm.call("mrp.workorder", "get_program_attachments_list", [workorderId])
      const instructionFiles = await this.model.orm.call("mrp.workorder", "get_instruction_attachments_list", [
        workorderId,
      ])

      this.filesState.programFiles = programFiles || []
      this.filesState.instructionFiles = instructionFiles || []
      this.filesState.isLoading = false

      console.log(" Loaded program files:", programFiles)
      console.log(" Loaded instruction files:", instructionFiles)
    } catch (error) {
      console.error(" Error loading attachments:", error)
      this.filesState.isLoading = false
    }
  },

  async openProgramFiles(ev) {
    ev.preventDefault()
    ev.stopPropagation()

    const workorderId = this.props.record.resId

    try {
      await this.action.doAction({
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
      console.error(" Error opening program files:", error)
    }
  },

  async openInstructionFiles(ev) {
    ev.preventDefault()
    ev.stopPropagation()

    const workorderId = this.props.record.resId

    try {
      await this.action.doAction({
        type: "ir.actions.act_window",
        name: "Instruction Files Viewer",
        res_model: "mrp.program.files.wizard",
        view_mode: "form",
        views: [[false, "form"]],
        target: "new",
        context: {
          default_workorder_id: workorderId,
          default_file_type: "instruction",
        },
      })
    } catch (error) {
      console.error(" Error opening instruction files:", error)
    }
  },

  async downloadAllPrograms(ev) {
    ev.preventDefault()
    ev.stopPropagation()

    const files = this.filesState.programFiles

    if (!files || files.length === 0) {
      console.log(" No program files to download")
      return
    }

    for (const file of files) {
      const url = `/web/content/${file.id}?download=true`
      const link = document.createElement("a")
      link.href = url
      link.download = file.name
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)

      await new Promise((resolve) => setTimeout(resolve, 500))
    }
  },

  async downloadAllInstructions(ev) {
    ev.preventDefault()
    ev.stopPropagation()

    const files = this.filesState.instructionFiles

    if (!files || files.length === 0) {
      console.log(" No instruction files to download")
      return
    }

    for (const file of files) {
      const url = `/web/content/${file.id}?download=true`
      const link = document.createElement("a")
      link.href = url
      link.download = file.name
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)

      await new Promise((resolve) => setTimeout(resolve, 500))
    }
  },

  /**
   * Check if this is a Knit workorder (for showing Re-program button)
   */
  isKnitWorkorder() {
    if (this.resModel !== "mrp.workorder") return false
    const name = this.props.record.data.name || ""
    return name.toLowerCase().includes("knit")
  },

  /**
   * Open the Request New Program wizard for Knit workorders
   */
  async openRequestNewProgram(ev) {
    ev.preventDefault()
    ev.stopPropagation()

    const workorderId = this.props.record.resId

    console.log(" Opening Request New Program wizard for workorder ID:", workorderId)

    try {
      await this.action.doAction({
        type: "ir.actions.act_window",
        name: "Request New Program",
        res_model: "request.new.program.wizard",
        view_mode: "form",
        views: [[false, "form"]],
        target: "new",
        context: {
          default_workorder_id: workorderId,
        },
      })
    } catch (error) {
      console.error(" Error opening Request New Program wizard:", error)
    }
  },
})

console.log(" MrpDisplayRecord patch applied successfully")
