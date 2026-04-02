/** @odoo-module **/

import { Component, useState } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { registry } from "@web/core/registry"
import { standardFieldProps } from "@web/views/fields/standard_field_props"
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog"


export class ToileDocWidget extends Component {
  static template = "maeknit_sales_customization.ToileDocWidget"
  static props = { ...standardFieldProps }

  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.dialogService = useService("dialog")

    this.state = useState({
      // Single panel for toile
      panel: null,          // { id, name, measurements: [{point, name, requestValue}], image }
      // Actual inputs: { point: value }
      pendingActuals: {},
      // New request overrides: { point: value } — user-edited points tracked in editedNewReq
      newRequestOverrides: {},
      editedNewReq: {},     // { point: true } — tracks user-manually-edited points (shown yellow)
      // Historical actual versions
      docData: {},          // { [panelId]: { actualVersions: [...], selectedVersion: N } }
      isDirty: false,
    })

    // Bind all methods accessed from templates so `this` is never lost inside lambdas
    this.getChange = this.getChange.bind(this)
    this.isChangeNonZero = this.isChangeNonZero.bind(this)
    this.getActualVersions = this.getActualVersions.bind(this)
    this.getSelectedVersion = this.getSelectedVersion.bind(this)
    this.getSelectedActualMeasurements = this.getSelectedActualMeasurements.bind(this)
    this.setSelectedVersion = this.setSelectedVersion.bind(this)
    this.setPendingActual = this.setPendingActual.bind(this)
    this.setNewRequest = this.setNewRequest.bind(this)
    this.hasPendingData = this.hasPendingData.bind(this)
    this.hasAnyNewRequestEdit = this.hasAnyNewRequestEdit.bind(this)
    this.deleteActualVersion = this.deleteActualVersion.bind(this)
    this.onNewReqKeyDown = this.onNewReqKeyDown.bind(this)
    this._commitActuals = this._commitActuals.bind(this)
    this._save = this._save.bind(this)

    this._loadData()
    this._setupSaveHook()
  }

  // ── Data Loading ────────────────────────────────────────────────────────────

  _loadData() {
    const panelCADRaw = this.props.record?.data?.measurement_widget_data_with_images
      || this.props.record?.data?.measurement_widget_data
    const docRaw = this.props.record?.data?.[this.props.name]

    const panelCAD = this._parseJSON(panelCADRaw) || {}
    const docData = this._parseJSON(docRaw) || {}

    // Find the first (and only) panel
    const customPanels = panelCAD.customPanels || []
    let firstPanelKey = null
    let firstPanelSrc = null
    let firstPanelName = null

    for (const cp of customPanels) {
      if (cp.id && panelCAD[cp.id]) {
        firstPanelKey = cp.id
        firstPanelSrc = panelCAD[cp.id]
        firstPanelName = cp.name || cp.id
        break
      }
    }

    // Fallback: legacy keys
    if (!firstPanelKey) {
      for (const key of ["front", "back", "sleeve", "collar"]) {
        if (panelCAD[key]) {
          firstPanelKey = key
          firstPanelSrc = panelCAD[key]
          firstPanelName = key[0].toUpperCase() + key.slice(1)
          break
        }
      }
    }

    if (firstPanelKey && firstPanelSrc) {
      const requestValues = this._getLatestRequestValues(firstPanelSrc)
      const measurements = (firstPanelSrc.measurements || []).map(m => ({
        point: m.point,
        name: m.name || "",
        requestValue: requestValues[m.point] ?? parseFloat(m.value) ?? 0,
      }))

      this.state.panel = {
        id: firstPanelKey,
        name: firstPanelSrc.name || firstPanelName,
        measurements,
        image: firstPanelSrc.image || null,
      }

      // Init pending actuals and new request overrides
      const pending = {}
      const overrides = {}
      const edited = {}
      for (const m of measurements) {
        pending[m.point] = ""
        overrides[m.point] = m.requestValue  // default = last request
        edited[m.point] = false
      }
      this.state.pendingActuals = pending
      this.state.newRequestOverrides = overrides
      this.state.editedNewReq = edited
    }

    this.state.docData = docData
  }

  _parseJSON(raw) {
    if (!raw) return null
    if (typeof raw === "object") return raw
    try { return JSON.parse(raw) } catch { return null }
  }

  _getLatestRequestValues(panelSrc) {
    const base = {}
    for (const m of panelSrc.measurements || []) {
      base[m.point] = parseFloat(m.value) || 0
    }
    const requests = panelSrc.panelRequests || []
    if (!requests.length) return base

    const latestVersion = Math.max(...requests.map(r => r.version))
    return this._computeAtVersion(panelSrc, latestVersion, base)
  }

  _computeAtVersion(panelSrc, version, base) {
    if (version <= 1) return base
    const req = (panelSrc.panelRequests || []).find(r => r.version === version)
    if (!req) return base
    const baseVersion = req.baseVersion !== undefined ? req.baseVersion : version - 1
    const baseValues = this._computeAtVersion(panelSrc, baseVersion, base)
    const result = { ...baseValues }
    for (const [point, delta] of Object.entries(req.changes || {})) {
      if (result[point] !== undefined) {
        result[point] = parseFloat((result[point] + (parseFloat(delta) || 0)).toFixed(3))
      }
    }
    return result
  }

  // ── Computed helpers ────────────────────────────────────────────────────────

  // Change = newRequest - lastRequest  (formatted to 3dp, sign included)
  getChange(point) {
    const panel = this.state.panel
    if (!panel) return 0
    const m = panel.measurements.find(m => m.point === point)
    if (!m) return 0
    const newReq = parseFloat(this.state.newRequestOverrides[point]) || 0
    const lastReq = parseFloat(m.requestValue) || 0
    return parseFloat((newReq - lastReq).toFixed(3))
  }

  isChangeNonZero(point) {
    return this.getChange(point) !== 0
  }

  getActualVersions() {
    const panel = this.state.panel
    if (!panel) return []
    return (this.state.docData[panel.id] || {}).actualVersions || []
  }

  getSelectedVersion() {
    const panel = this.state.panel
    if (!panel) return null
    const d = this.state.docData[panel.id] || {}
    if (d.selectedVersion !== null && d.selectedVersion !== undefined) return d.selectedVersion
    const versions = d.actualVersions || []
    return versions.length ? versions[versions.length - 1].version : null
  }

  getSelectedActualMeasurements() {
    const ver = this.getSelectedVersion()
    if (ver === null) return {}
    const found = this.getActualVersions().find(v => v.version === ver)
    return found ? found.measurements : {}
  }

  setSelectedVersion(version) {
    const panel = this.state.panel
    if (!panel) return
    if (!this.state.docData[panel.id]) this.state.docData[panel.id] = { actualVersions: [], selectedVersion: null }
    this.state.docData[panel.id].selectedVersion = parseInt(version)
  }

  setPendingActual(point, value) {
    this.state.pendingActuals[point] = value
    this.state.isDirty = true
    this._save()
  }

  setNewRequest(point, value) {
    this.state.newRequestOverrides[point] = value
    this.state.editedNewReq[point] = true
    this.state.isDirty = true
    this._save()
  }

  onNewReqKeyDown(ev) {
    if (ev.key !== 'Enter') return
    ev.preventDefault()
    const colClass = ev.target.closest('td')?.dataset?.col
    const selector = colClass ? `td[data-col="${colClass}"] input` : null
    if (!selector) return
    const colInputs = Array.from(ev.target.closest('table')?.querySelectorAll(selector) || [])
    const idx = colInputs.indexOf(ev.target)
    if (idx !== -1 && idx + 1 < colInputs.length) {
      colInputs[idx + 1].focus()
      colInputs[idx + 1].select()
    }
  }

  hasPendingData() {
    const actuals = this.state.pendingActuals || {}
    return Object.values(actuals).some(v => v !== "" && v !== null && v !== undefined)
  }

  hasAnyNewRequestEdit() {
    return Object.values(this.state.editedNewReq || {}).some(Boolean)
  }

  // ── Save Actuals to docData ─────────────────────────────────────────────────

  _commitActuals() {
    const panel = this.state.panel
    if (!panel) return

    const actuals = this.state.pendingActuals
    if (!this.state.docData[panel.id]) {
      this.state.docData[panel.id] = { actualVersions: [], selectedVersion: null }
    }
    if (!this.state.docData[panel.id].actualVersions) {
      this.state.docData[panel.id].actualVersions = []
    }
    const existing = this.state.docData[panel.id].actualVersions
    const nextVersion = existing.length ? Math.max(...existing.map(v => v.version)) + 1 : 1

    const measurements = {}
    for (const m of panel.measurements) {
      const raw = actuals[m.point]
      measurements[m.point] = (raw !== "" && raw !== null && raw !== undefined) ? parseFloat(raw) : null
    }

    this.state.docData[panel.id].actualVersions.push({
      version: nextVersion,
      measurements,
      submitted_at: new Date().toISOString().slice(0, 10),
    })
    this.state.docData[panel.id].selectedVersion = nextVersion

    // Reset pending actuals
    for (const m of panel.measurements) {
      this.state.pendingActuals[m.point] = ""
    }
  }


  deleteActualVersion(version) {
    const panel = this.state.panel
    if (!panel) return
    this.dialogService.add(ConfirmationDialog, {
      title: `Delete Actual v${version}`,
      body: `Delete Actual version ${version}? This cannot be undone.`,
      confirm: () => {
        const d = this.state.docData[panel.id]
        if (!d) return
        d.actualVersions = d.actualVersions.filter(v => v.version !== version)
        if (d.selectedVersion === version) {
          d.selectedVersion = d.actualVersions.length ? d.actualVersions[d.actualVersions.length - 1].version : null
        }
        this.state.isDirty = true
        this._save()
      },
    })
  }

  // ── Persistence ─────────────────────────────────────────────────────────────

  async _save() {
    try {
      // Embed pending new request overrides into docData so the wizard Python can
      // write them back into Panel CAD on action_remanufacture / action_approve_for_shipment
      const panel = this.state.panel
      const saveData = { ...this.state.docData }

      // Always snapshot current new request overrides so Python can apply them
      if (panel) {
        saveData.__pendingNewRequests = {
          panelId: panel.id,
          overrides: { ...this.state.newRequestOverrides },
          editedPoints: Object.keys(this.state.editedNewReq).filter(k => this.state.editedNewReq[k]),
        }
      } else {
        delete saveData.__pendingNewRequests
      }

      // Snapshot raw pending actuals so Python can commit them as a version entry
      if (panel && Object.values(this.state.pendingActuals || {}).some(v => v !== "" && v !== null && v !== undefined)) {
        saveData.__pendingActuals = {
          panelId: panel.id,
          measurements: { ...this.state.pendingActuals },
          submitted_at: new Date().toISOString().slice(0, 10),
        }
      } else {
        delete saveData.__pendingActuals
      }
      await this.props.record.update({ [this.props.name]: saveData })
      this.state.isDirty = false
    } catch (e) {
      console.error("Error saving toile doc data:", e)
      this.notification.add("Error saving documentation", { type: "danger" })
    }
  }

  _setupSaveHook() {
    try {
      if (this.props.record?.save) {
        const original = this.props.record.save.bind(this.props.record)
        this.props.record.save = async (...args) => {
          if (this.state.isDirty) await this._save()
          const result = await original(...args)
          this.state.isDirty = false
          return result
        }
      }
    } catch (e) {
      console.error("Error setting up save hook:", e)
    }
  }
}

registry.category("fields").add("toile_doc_widget", {
  component: ToileDocWidget,
  supportedTypes: ["json", "text", "char"],
})

export default ToileDocWidget
