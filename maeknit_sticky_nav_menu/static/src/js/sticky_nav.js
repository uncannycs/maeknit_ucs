import { Component, onMounted, xml } from "@odoo/owl"
import { registry } from "@web/core/registry"
import { session } from "@web/session"

export class StickyNav extends Component {
  static template = xml`<div class="sticky-left-nav-container"></div>`

  setup() {
    onMounted(() => this._setupNavMenu())
  }

  _setupNavMenu() {
    const isJag = session.partner_display_name === "Jag Sodhi" || session.username === "jag@maeknit.io"

    // Use relative URLs instead of absolute URLs to make it work in any environment
    const menuItems = [
      ...(!isJag ? [{ name: "Contacts", url: "/odoo/contacts", icon: "fa-mobile-phone" }] : []),
      ...(!isJag ? [{ name: "Purchase", url: "/odoo/purchase", icon: "fa-shopping-bag" }] : []),
      { name: "Inventory", url: "/odoo/action-1096?view_type=list", base: "/odoo/action-1096", icon: "fa-shopping-basket" },
      { name: "CRM", url: "/odoo/crm?view_type=list",   base: "/odoo/crm", icon: "fa-users" },
      { name: "Sales", url: "/odoo/sales", icon: "fa-shopping-cart" },
      {
        name: "BOM QUEUE",
        url: "/odoo/bom-request/development",
        icon: "fa-handshake-o",
        // Add alternative URLs that should also be considered active
        alternativeUrls: ["/odoo/action-1295", "/web#action=maeknit_sales_customization.action_bom_request", "/odoo/action-1191",
        "/web#action=maeknit_sales_customization.action_bom_request",
        "/web#action=maeknit_sales_customization.action_bom_request_garment",
        "/web#action=maeknit_sales_customization.action_bom_request_swatch",
        "/web#action=maeknit_sales_customization.action_bom_request_reverse",
        "/web#action=maeknit_sales_customization.action_bom_request_production",
        "/web#action=maeknit_sales_customization.action_bom_request_grading",
        "/odoo/action-1291", 
        "/odoo/action-1292",
        "/odoo/action-1193",
        "/odoo/action-1318", 
        ],
      },
      ...(!isJag ? [{ name: "Replenishment", url: "/odoo/replenishment", icon: "fa-plus" }] : []),
      { name: "Manufacturing", url: "/odoo/manufacturing", icon: "fa-industry" },
      { name: "Fitting Notes", url: "/odoo/fittings", base: "/odoo/fittings", icon: "fa-clipboard" },
      { name: "My Workorders", url: "/web#action=mrp.mrp_workorder_todo", icon: "fa-wrench", alternativeUrls: ["/odoo/action-673"] },
      { name: "Calendar", url: "/odoo/calendar", icon: "fa-calendar" },
      { name: "Shop Floor", url: "/odoo/shop-floor", icon: "fa-hourglass-start" },
      ...(!isJag ? [{ name: "Accounting", url: "/odoo/accounting", icon: "fa-book" }] : []),
      { name: "To-do", url: "/odoo/to-do?view_type=list",  base: "/odoo/to-do", icon: "fa-check-square-o" },
      { name: "Inbox", url: "/odoo/discuss", icon: "fa-envelope" },
      { name: "Apps", url: "/odoo/apps", icon: "fa-th" },
      { name: "Settings", url: "/odoo/settings", icon: "fa-cog" },
      { name: "Home", url: "/odoo", icon: "fa-home" },
    ]

    const nav = document.createElement("div")
    nav.className = "sticky-left-nav"

    // Add title to the nav
    const title = document.createElement("div")
    title.className = "sticky-nav-title"
    title.textContent = "Quick Navigation"
    nav.appendChild(title)

    const ul = document.createElement("ul")

    menuItems.forEach((item) => {
      const li = document.createElement("li")

      // Create icon element
      const icon = document.createElement("i")
      icon.className = `fa ${item.icon} menu-icon`
      li.appendChild(icon)

      // Create text span
      const text = document.createElement("span")
      text.textContent = item.name
      li.appendChild(text)

      // Set click handler to use direct URL navigation
      li.onclick = () => {
        window.location.href = item.url
      }
      
      if (item.base) {
        li.setAttribute("data-base", item.base)
      }

      // Store URL and alternative URLs for active detection
      li.setAttribute("data-url", item.url)
      if (item.alternativeUrls) {
        li.setAttribute("data-alternative-urls", JSON.stringify(item.alternativeUrls))
      }

      ul.appendChild(li)
    })

    nav.appendChild(ul)

    // Add elements to the DOM
    document.body.appendChild(nav)

    // Add toggle button
    this._createToggleButton()

    // Set up active menu updater
    this._setupActiveMenuUpdater()

    // Fix layout issues
    this._fixLayout()

    // Add observer for DOM changes
    this._setupLayoutObserver()

    // Restore collapsed state from localStorage
    this._restoreCollapsedState()
  }

  _createToggleButton() {
    const toggleBtn = document.createElement("button")
    toggleBtn.className = "nav-toggle"
    toggleBtn.innerHTML = '<i class="fa fa-chevron-left"></i>'
    toggleBtn.title = "Toggle Navigation"

    toggleBtn.onclick = () => {
      this._toggleNav()
    }

    document.body.appendChild(toggleBtn)
  }

  _toggleNav() {
    const isCollapsed = document.body.classList.toggle("nav-collapsed")
    const toggleBtn = document.querySelector(".nav-toggle")

    if (toggleBtn) {
      toggleBtn.innerHTML = isCollapsed
        ? '<i class="fa fa-chevron-right"></i>'
        : '<i class="fa fa-chevron-left"></i>'
    }

    // Save state to localStorage
    localStorage.setItem("maeknit_nav_collapsed", isCollapsed ? "true" : "false")

    // Re-apply layout fixes
    this._fixLayout()
  }

  _restoreCollapsedState() {
    const isCollapsed = localStorage.getItem("maeknit_nav_collapsed") === "true"

    if (isCollapsed) {
      document.body.classList.add("nav-collapsed")
      const toggleBtn = document.querySelector(".nav-toggle")
      if (toggleBtn) {
        toggleBtn.innerHTML = '<i class="fa fa-chevron-right"></i>'
      }
    }
  }

  _setupActiveMenuUpdater() {
    const updateActive = () => {
      const href = window.location.href
      const current = href.replace(window.location.origin, "")
      const items = document.querySelectorAll(".sticky-left-nav ul li")
  
      items.forEach((i) => i.classList.remove("active"))
  
      let best = null
      let bestLen = 0
  
      items.forEach((item) => {
        const url = item.getAttribute("data-url")
        const base = item.getAttribute("data-base")
        const altStr = item.getAttribute("data-alternative-urls")
  
        if (!url) return
  
        // 1. Base path match (strongest)
        if (base && current.startsWith(base) && base.length > bestLen) {
          best = item
          bestLen = base.length
        }
  
        // 2. Full URL match
        if (current.startsWith(url) && url.length > bestLen) {
          best = item
          bestLen = url.length
        }
  
        // 3. Alternative URLs
        if (altStr) {
          try {
            const alts = JSON.parse(altStr)
            alts.forEach((alt) => {
              // action detection
              if (alt.includes("action-")) {
                const actionPart = alt.split("/").pop()
                if (current.includes(actionPart) && alt.length > bestLen) {
                  best = item
                  bestLen = alt.length
                }
                return
              }
  
              // hash URLs
              if (alt.includes("#action=") && href.includes(alt.split("#")[1]) && alt.length > bestLen) {
                best = item
                bestLen = alt.length
                return
              }
  
              // plain URL
              if (current.startsWith(alt) && alt.length > bestLen) {
                best = item
                bestLen = alt.length
              }
            })
          } catch {}
        }
      })
  
      if (best) best.classList.add("active")
    }
  
    updateActive()
  
    const observer = new MutationObserver(updateActive)
    observer.observe(document.body, { childList: true, subtree: true })
  
    window.addEventListener("popstate", updateActive)
    window.addEventListener("hashchange", updateActive)
  }
  

  _fixLayout() {
    const isCollapsed = document.body.classList.contains("nav-collapsed")

    // When collapsed, remove all inline styles to let CSS handle full-width layout
    if (isCollapsed) {
      // Remove inline styles - let CSS .nav-collapsed rules take over
      const webClient = document.querySelector(".o_web_client")
      if (webClient) {
        webClient.style.marginLeft = ""
        webClient.style.width = ""
      }

      const navbar = document.querySelector(".o_main_navbar")
      if (navbar) {
        navbar.style.left = ""
        navbar.style.width = ""
      }

      const appDrawer = document.querySelector(".o_app_drawer")
      if (appDrawer) {
        appDrawer.style.left = ""
        appDrawer.style.width = ""
      }

      const actionManager = document.querySelector(".o_action_manager")
      if (actionManager) {
        actionManager.style.marginLeft = ""
        actionManager.style.paddingLeft = ""
      }

      return // Exit early, CSS handles the rest
    }

    // When expanded, apply nav width offset
    const navWidth = "240px"
    const contentWidth = "calc(100% - 240px)"

    // Fix main container
    const webClient = document.querySelector(".o_web_client")
    if (webClient) {
      webClient.style.marginLeft = navWidth
      webClient.style.width = contentWidth
    }

    // Fix navbar
    const navbar = document.querySelector(".o_main_navbar")
    if (navbar) {
      navbar.style.left = navWidth
      navbar.style.width = contentWidth
    }

    // Fix app drawer
    const appDrawer = document.querySelector(".o_app_drawer")
    if (appDrawer) {
      appDrawer.style.left = navWidth
      appDrawer.style.width = contentWidth
    }

    // Fix settings page
    const settings = document.querySelector(".settings")
    if (settings) {
      settings.style.padding = "0"
    }

    // Fix settings tabs
    const settingsTabs = document.querySelector(".settings_tab")
    if (settingsTabs) {
      settingsTabs.style.paddingLeft = "0"
    }

    // Fix calendar view
    const calendarView = document.querySelector(".o_calendar_view")
    if (calendarView) {
      calendarView.style.marginLeft = "0"
      calendarView.style.width = "100%"
    }

    // Fix action manager top margin
    const actionManager = document.querySelector(".o_action_manager")
    if (actionManager) {
      actionManager.style.marginTop = "46px" // Adjust based on navbar height
    }
  }

  _setupLayoutObserver() {
    // Observer to detect DOM changes that might affect layout
    const observer = new MutationObserver(() => {
      this._fixLayout()
    })

    // Observe changes to the body element
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style"],
    })
  }
}

registry.category("main_components").add("StickyNav", {
  Component: StickyNav,
})
