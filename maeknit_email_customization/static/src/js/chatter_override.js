/** @odoo-module **/

import { onMounted, onPatched } from "@odoo/owl"
import { patch } from "@web/core/utils/patch"
import { registry } from "@web/core/registry"

// Function to find button by text content
function findButtonByText(container, texts) {
  const buttons = container.querySelectorAll("button")
  for (const button of buttons) {
    const buttonText = button.textContent?.trim() || ""
    if (texts.some((text) => buttonText.includes(text))) {
      return button
    }
  }
  return null
}

// Function to show attachments by default when they exist
function showAttachmentsIfPresent(element) {
  const attachmentButtons = element.querySelectorAll(".o-mail-Chatter-attachFiles")
  const attachmentLists = element.querySelectorAll(
    ".o-mail-AttachmentBox, .o-mail-Chatter-attachmentBox, .o-mail-AttachmentList, .o_attachment_list",
  )
  const chatters = element.querySelectorAll(".o-mail-Chatter")

  chatters.forEach((chatter, index) => {
    const expandedSelectors = [
      ".o-mail-AttachmentImage",
      ".o-mail-AttachmentCard",
      ".o_attachment",
      ".o-mail-Attachment",
      ".o-mail-AttachmentVideo",
      ".o-mail-AttachmentAudio",
      ".o-mail-AttachmentDocument",
      ".attachment-item",
      "[data-attachment-id]",
    ].join(", ")

    const hasAttachments = chatter.querySelector(expandedSelectors)
    const attachmentCount = chatter.querySelectorAll(expandedSelectors).length

    const attachmentButton = chatter.querySelector(".o-mail-Chatter-attachFiles")
    let countFromIndicator = 0
    if (attachmentButton) {
      const countElement = attachmentButton.querySelector("sup")
      if (countElement && countElement.textContent.trim()) {
        countFromIndicator = Number.parseInt(countElement.textContent.trim()) || 0
      }
    }

    const hasAnyAttachments = hasAttachments || countFromIndicator > 0
    const totalAttachmentCount = Math.max(attachmentCount, countFromIndicator)

    if (hasAnyAttachments && totalAttachmentCount > 0) {
      if (attachmentButton && !attachmentButton.dataset.maeknitProcessed) {
        attachmentButton.dataset.maeknitProcessed = "true"
        const originalClick = attachmentButton.onclick

        attachmentButton.onclick = function (event) {
          if (this.dataset.programmaticClick === "true") {
            this.dataset.programmaticClick = "false"
            return
          }

          if (originalClick) {
            originalClick.call(this, event)
          }

          setTimeout(() => {
            const attachmentBox = chatter.querySelector(".o-mail-AttachmentBox, .o-mail-Chatter-attachmentBox")
            if (attachmentBox) {
              setTimeout(() => {
                const attachmentItems = attachmentBox.querySelectorAll(expandedSelectors)

                if (attachmentItems.length > 0) {
                } else {
                }

                attachmentBox.style.display = "block"
                attachmentBox.style.visibility = "visible"
                attachmentBox.classList.remove("d-none", "hidden")
                attachmentBox.classList.add("maeknit-attachments-visible")
              }, 200)
            }
          }, 100)
        }
      }

      if (countFromIndicator > 0 && attachmentCount === 0) {
        if (attachmentButton) {
          attachmentButton.dataset.programmaticClick = "true"
          attachmentButton.click()

          setTimeout(() => {
            const attachmentBox = chatter.querySelector(".o-mail-AttachmentBox, .o-mail-Chatter-attachmentBox")
            if (attachmentBox) {
              setTimeout(() => {
                const attachmentItems = attachmentBox.querySelectorAll(expandedSelectors)

                if (attachmentItems.length > 0) {
                } else {
                }

                attachmentBox.style.display = "block"
                attachmentBox.style.visibility = "visible"
                attachmentBox.classList.remove("d-none", "hidden")
                attachmentBox.classList.add("maeknit-attachments-visible")
              }, 200)
            }
          }, 100)
        }
      }

      if (attachmentButton) {
        attachmentButton.style.fontWeight = "bold"
        attachmentButton.style.opacity = "1"
      } else {
      }

      const attachmentBox = chatter.querySelector(".o-mail-AttachmentBox, .o-mail-Chatter-attachmentBox")
      if (attachmentBox) {
        attachmentBox.style.display = "block"
        attachmentBox.style.visibility = "visible"
        attachmentBox.classList.remove("d-none", "hidden")
        attachmentBox.classList.add("maeknit-attachments-visible")
      } else {
      }
    } else {
    }
  })

  attachmentLists.forEach((list, index) => {
    const attachmentItems = list.querySelectorAll(
      ".o-mail-AttachmentImage, .o-mail-AttachmentCard, .o_attachment, .o-mail-Attachment, .o-mail-AttachmentVideo, .o-mail-AttachmentAudio, .o-mail-AttachmentDocument, .attachment-item, [data-attachment-id]",
    )
    const attachmentCount = attachmentItems.length

    if (attachmentCount > 0) {
      list.style.display = "block"
      list.style.visibility = "visible"
      list.classList.remove("d-none", "hidden")
      list.classList.add("maeknit-attachments-visible")
    }
  })
}
// Function to customize chatter buttons in any element
function customizeChatterInElement(element) {
  // Find all chatter topbars in the element
  const topbars = element.querySelectorAll(".o-mail-Chatter-topbar, .o_ChatterTopbar, .o_chatter_topbar")
  topbars.forEach((topbar, index) => {
    // Skip if already customized
    if (topbar.classList.contains("maeknit-chatter-customized")) {
      return
    }

    // Find the main action buttons using valid selectors
    let logNoteBtn = topbar.querySelector(
      '.o-mail-Chatter-logNote, .o_chatter_button_log_note, button[data-hotkey="shift+m"]',
    )
    if (!logNoteBtn) {
      logNoteBtn = findButtonByText(topbar, ["Log note", "Log"])
    }

    let activityBtn = topbar.querySelector(
      '.o-mail-Chatter-activity, .o_chatter_button_schedule_activity, button[data-hotkey="shift+a"]',
    )
    if (!activityBtn) {
      activityBtn = findButtonByText(topbar, ["Activities", "Activity"])
    }

    let sendMessageBtn = topbar.querySelector(
      '.o-mail-Chatter-sendMessage, .o_chatter_button_send_message, button[data-hotkey="m"]',
    )
    if (!sendMessageBtn) {
      sendMessageBtn = findButtonByText(topbar, ["Send message", "Send"])
    }

    // Find utility buttons that should stay on the right
    const searchBtn = topbar.querySelector('button[aria-label*="Search"], .o_chatter_button_search')
    const attachBtn = topbar.querySelector(
      ".o-mail-Chatter-fileUploader, .o-mail-Chatter-attachFiles, .o_chatter_button_attach",
    )
    const followingBtn = topbar.querySelector(".o-mail-Followers, .o-mail-Chatter-follow, .o_followers")
    const closeBtn = topbar.querySelector(".o-mail-Chatter-close")

    // Change "Send message" text to "Email followers"
    if (sendMessageBtn) {
      // Try different ways to find and change the text
      const textElements = [
        sendMessageBtn,
        sendMessageBtn.querySelector("span"),
        sendMessageBtn.querySelector(".o_button_text"),
        ...Array.from(sendMessageBtn.querySelectorAll("*")),
      ].filter(Boolean)

      let textChanged = false
      textElements.forEach((el) => {
        if (el.textContent && el.textContent.trim() === "Send message") {
          el.textContent = "Email followers"
          textChanged = true
        }
        // Also check for partial matches
        if (el.textContent && el.textContent.includes("Send message")) {
          el.textContent = el.textContent.replace("Send message", "Email followers")
          textChanged = true
        }
      })

      // If no text elements found, try to change the button directly
      if (!textChanged && sendMessageBtn.textContent && sendMessageBtn.textContent.trim() === "Send message") {
        sendMessageBtn.textContent = "Email followers"
      }
    }

    // Ensure the topbar uses flexbox
    topbar.style.display = "flex"
    topbar.style.alignItems = "center"
    topbar.style.flexWrap = "wrap"

    // Set order for main action buttons (left side)
    if (logNoteBtn) {
      logNoteBtn.style.order = "1"
      logNoteBtn.style.marginRight = "0.5rem"
    }
    if (activityBtn) {
      activityBtn.style.order = "2"
      activityBtn.style.marginRight = "0.5rem"
    }
    if (sendMessageBtn) {
      sendMessageBtn.style.order = "3"
      sendMessageBtn.style.marginRight = "0.5rem"
    }

    // Add a spacer to push utility buttons to the right
    let spacer = topbar.querySelector(".chatter-spacer")
    if (!spacer) {
      spacer = document.createElement("div")
      spacer.className = "chatter-spacer"
      spacer.style.flexGrow = "1"
      spacer.style.order = "10"
      topbar.appendChild(spacer)
    }

    // Set order for utility buttons (right side) - higher order numbers
    if (searchBtn) {
      searchBtn.style.order = "20"
      searchBtn.style.marginLeft = "0.25rem"
    }
    if (attachBtn) {
      attachBtn.style.order = "21"
      attachBtn.style.marginLeft = "0.25rem"
    }
    if (followingBtn) {
      followingBtn.style.order = "22"
      followingBtn.style.marginLeft = "0.25rem"
    }
    if (closeBtn) {
      closeBtn.style.order = "23"
      closeBtn.style.marginLeft = "0.25rem"
    }

    showAttachmentsIfPresent(topbar.closest(".o-mail-Chatter, .o_chatter") || element)

    let sideToggle = topbar.querySelector(".maeknit-chatter-side-toggle")
    if (!sideToggle) {
      sideToggle = document.createElement("button")
      sideToggle.className = "btn btn-light btn-sm maeknit-chatter-side-toggle"
      sideToggle.innerHTML = '<i class="fa fa-chevron-right"></i>'
      sideToggle.title = "Hide chatter"
      sideToggle.style.order = "0" // Place it first
      topbar.prepend(sideToggle)

      sideToggle.addEventListener("click", (e) => {
        e.preventDefault()

        const chatterContainer = topbar.closest(".o_ChatterContainer, .o-mail-Chatter, .o_chatter")
        if (!chatterContainer) return

        chatterContainer.classList.toggle("maeknit-chatter-hidden")
        const hidden = chatterContainer.classList.contains("maeknit-chatter-hidden")
        const icon = sideToggle.querySelector("i")

        if (hidden) {
          icon.className = "fa fa-chevron-left"
          sideToggle.title = "Show chatter"
          chatterContainer.style.display = "none"
          document.body.classList.add("maeknit-no-chatter")

          // Find and mark the main content area to expand
          const contentContainer = document.querySelector(".o_content, .o_action_manager")
          if (contentContainer) {
            contentContainer.classList.add("maeknit-content-expanded")
          }

          // Also mark form views to expand
          const formView = document.querySelector(".o_form_view")
          if (formView) {
            formView.classList.add("maeknit-form-expanded")
          }

          // Create floating expand button
          createFloatingToggle(chatterContainer)
        } else {
          icon.className = "fa fa-chevron-right"
          sideToggle.title = "Hide chatter"
          chatterContainer.style.display = ""
          document.body.classList.remove("maeknit-no-chatter")

          const contentContainer = document.querySelector(".o_content, .o_action_manager")
          if (contentContainer) {
            contentContainer.classList.remove("maeknit-content-expanded")
          }

          const formView = document.querySelector(".o_form_view")
          if (formView) {
            formView.classList.remove("maeknit-form-expanded")
          }

          // Remove floating expand button
          removeFloatingToggle()
        }
      })
    }

    // Add a class to mark this topbar as customized
    topbar.classList.add("maeknit-chatter-customized")

    console.log("Chatter buttons customized:", {
      logNoteBtn: !!logNoteBtn,
      activityBtn: !!activityBtn,
      sendMessageBtn: !!sendMessageBtn,
      searchBtn: !!searchBtn,
      attachBtn: !!attachBtn,
      followingBtn: !!followingBtn,
    })
  })

  showAttachmentsIfPresent(element)
}

// Function to create floating toggle button to expand chatter when hidden
function createFloatingToggle(chatterContainer) {
  // Remove any existing floating toggle first
  removeFloatingToggle()

  const floatingToggle = document.createElement("button")
  floatingToggle.className = "btn btn-primary maeknit-floating-chatter-toggle"
  floatingToggle.innerHTML = '<i class="fa fa-chevron-left"></i>'
  floatingToggle.title = "Show chatter"
  floatingToggle.setAttribute("data-maeknit-floating", "true")

  floatingToggle.addEventListener("click", (e) => {
    e.preventDefault()

    // Find the original toggle button and click it
    const originalToggle = chatterContainer.querySelector(".maeknit-chatter-side-toggle")
    if (originalToggle) {
      originalToggle.click()
    }
  })

  document.body.appendChild(floatingToggle)
}

// Function to remove floating toggle button
function removeFloatingToggle() {
  const existingFloatingToggle = document.querySelector(".maeknit-floating-chatter-toggle")
  if (existingFloatingToggle) {
    existingFloatingToggle.remove()
  }
}

// Try to patch the Chatter component - use dynamic import
function patchChatterComponent() {
  // Try different possible import paths for the Chatter component
  const possiblePaths = [
    "@mail/core/web/chatter",
    "@mail/components/chatter/chatter",
    "@mail/core/common/chatter",
    "@mail/js/chatter",
    "@mail/static/src/components/chatter/chatter",
  ]

  possiblePaths.forEach(async (path) => {
    try {
      const module = await import(path)
      const Chatter = module.Chatter || module.default

      if (Chatter && Chatter.prototype) {
        // Patch the Chatter component
        patch(Chatter.prototype, "maeknit_chatter_customization", {
          setup() {
            this._super(...arguments)

            onMounted(() => {
              setTimeout(() => this.customizeChatterButtons(), 100)
            })

            onPatched(() => {
              setTimeout(() => this.customizeChatterButtons(), 100)
            })
          },

          customizeChatterButtons() {
            // Find the chatter container
            const chatterEl = this.el || this.__owl__?.bdom?.el
            if (!chatterEl) return

            customizeChatterInElement(chatterEl)
          },
        })

        console.log(`Chatter component patched successfully from ${path}`)
        return true // Success
      }
    } catch (error) {
      // Silently continue to next path
      console.debug(`Could not import Chatter from ${path}:`, error)
    }
  })
}

// MutationObserver approach as fallback
const observer = new MutationObserver((mutations) => {
  mutations.forEach((mutation, mutationIndex) => {
    if (mutation.type === "childList") {
      mutation.addedNodes.forEach((node, nodeIndex) => {
        if (node.nodeType === Node.ELEMENT_NODE) {
          // Check if this node contains chatter topbars
          const hasChatterTopbar =
            node.querySelector &&
            (node.querySelector(".o-mail-Chatter-topbar") ||
              node.querySelector(".o_ChatterTopbar") ||
              node.querySelector(".o_chatter_topbar") ||
              node.classList?.contains("o-mail-Chatter-topbar") ||
              node.classList?.contains("o_ChatterTopbar") ||
              node.classList?.contains("o_chatter_topbar"))

          const hasAttachments =
            node.querySelector &&
            (node.querySelector(".o-mail-AttachmentList") ||
              node.querySelector(".o_attachment_list") ||
              node.querySelector(".o-mail-AttachmentCard") ||
              node.querySelector(".o_attachment") ||
              node.classList?.contains("o-mail-AttachmentList") ||
              node.classList?.contains("o_attachment_list"))
          if (hasChatterTopbar || hasAttachments) {
            setTimeout(() => {
              customizeChatterInElement(node)
            }, 100)
          }
        }
      })
    }
  })
})

// Service to handle chatter customization
const chatterCustomizationService = {
  start() {
    console.log("Chatter customization service started")

    // Try to patch the component
    patchChatterComponent()

    // Start observing DOM changes
    observer.observe(document.body, {
      childList: true,
      subtree: true,
    })

    // Customize existing elements after a short delay
    setTimeout(() => customizeChatterInElement(document.body), 1000)

    // Periodic check for new chatter elements (fallback)
    const interval = setInterval(() => {
      const unCustomizedTopbars = document.querySelectorAll(
        ".o-mail-Chatter-topbar:not(.maeknit-chatter-customized), .o_ChatterTopbar:not(.maeknit-chatter-customized), .o_chatter_topbar:not(.maeknit-chatter-customized)",
      )
      if (unCustomizedTopbars.length > 0) {
        customizeChatterInElement(document.body)
      }
    }, 3000)

    // Stop periodic check after 60 seconds
    setTimeout(() => {
      clearInterval(interval)
    }, 60000)

    return {
      // Expose method to manually trigger customization
      customizeChatter: () => customizeChatterInElement(document.body),
    }
  },
}

// Register the service
registry.category("services").add("chatter_customization", chatterCustomizationService)

// Also try immediate execution when the module loads
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    setTimeout(() => customizeChatterInElement(document.body), 2000)
  })
} else {
  setTimeout(() => customizeChatterInElement(document.body), 2000)
}

// Export for potential manual use
export { customizeChatterInElement }
