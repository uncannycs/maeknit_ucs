/** @odoo-module **/
import { registry } from "@web/core/registry"
import { Component } from "@odoo/owl"
import { standardFieldProps } from "@web/views/fields/standard_field_props"

class TimerWidget extends Component {
  static template = "timer_widget.TimerWidget"
  static props = { ...standardFieldProps }

  setup() {
    console.log("[TimerWidget] setup")
    this.isRunning = false
    this.isPaused = false
    this.elapsed = 0
    this._interval = null

    // Load initial state when component mounts
    this._loadState()
  }

  willUnmount() {
    this._clear()
  }

  _clear() {
    if (this._interval) {
      clearInterval(this._interval)
      this._interval = null
    }
  }

  _tick() {
    this._clear()
    this._interval = setInterval(() => {
      if (this.isRunning && !this.isPaused) {
        this.elapsed += 1
        this.render()
      }
    }, 1000)
  }

  get _resId() {
    return this.props.record?.resId
  }

  get displayTime() {
    const sec = Math.max(0, this.elapsed || 0)
    const h = String(Math.floor(sec / 3600)).padStart(2, "0")
    const m = String(Math.floor((sec % 3600) / 60)).padStart(2, "0")
    const s = String(sec % 60).padStart(2, "0")
    return `${h}:${m}:${s}`
  }

  async _loadState() {
    const id = this._resId
    console.log("[TimerWidget] _loadState resId =", id)
    if (!id) {
      this._clear()
      return
    }

    try {
      const res = await this.env.services.orm.call("project.task", "get_timer_state", [id])
      this.isRunning = !!res.is_running
      this.isPaused = !!res.is_paused
      this.elapsed = res.elapsed_seconds || 0
      this.isRunning ? this._tick() : this._clear()
      this.render()
    } catch (error) {
      console.error("[TimerWidget] Error loading state:", error)
    }
  }

  async startTimer() {
    const id = this._resId
    console.log("[TimerWidget] startTimer resId =", id)
    if (!id) return

    try {
      const res = await this.env.services.orm.call("project.task", "start_timer", [id])
      this.isRunning = !!res.is_running
      this.isPaused = !!res.is_paused
      this.elapsed = res.elapsed_seconds || 0
      this._tick()
      this.render()
    } catch (error) {
      console.error("[TimerWidget] Error starting timer:", error)
    }
  }

  async pauseTimer() {
    const id = this._resId
    console.log("[TimerWidget] pauseTimer resId =", id)
    if (!id) return

    try {
      const res = await this.env.services.orm.call("project.task", "pause_timer", [id])
      this.isRunning = !!res.is_running
      this.isPaused = !!res.is_paused
      this.elapsed = res.elapsed_seconds || 0
      this._clear()
      this.render()
    } catch (error) {
      console.error("[TimerWidget] Error pausing timer:", error)
    }
  }

  async resumeTimer() {
    const id = this._resId
    console.log("[TimerWidget] resumeTimer resId =", id)
    if (!id) return

    try {
      const res = await this.env.services.orm.call("project.task", "resume_timer", [id])
      this.isRunning = !!res.is_running
      this.isPaused = !!res.is_paused
      this.elapsed = res.elapsed_seconds || 0
      this._tick()
      this.render()
    } catch (error) {
      console.error("[TimerWidget] Error resuming timer:", error)
    }
  }

  async stopTimer() {
    const id = this._resId
    console.log("[TimerWidget] stopTimer resId =", id)
    if (!id) return

    try {
      const res = await this.env.services.orm.call("project.task", "stop_timer", [id])
      this.isRunning = !!res.is_running
      this.isPaused = !!res.is_paused
      this.elapsed = res.elapsed_seconds || 0
      this._clear()
      this.render()
      if (this.props.record?.load) await this.props.record.load()
    } catch (error) {
      console.error("[TimerWidget] Error stopping timer:", error)
    }
  }

  async saveTimesheet() {
    const id = this._resId
    console.log("[TimerWidget] saveTimesheet resId =", id)
    if (!id) return

    try {
      await this.env.services.orm.call("project.task", "save_timesheet", [id])
      this.isRunning = false
      this.isPaused = false
      this.elapsed = 0
      this._clear()
      this.render()
      if (this.props.record?.load) await this.props.record.load()
    } catch (error) {
      console.error("[TimerWidget] Error saving timesheet:", error)
    }
  }
}

registry.category("fields").add("timer_widget", {
  component: TimerWidget,
  supportedTypes: ["char"],
})

export { TimerWidget }
