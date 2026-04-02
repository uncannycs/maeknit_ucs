/** @odoo-module **/

// This file is now deprecated as its functions have been moved to managers.
// Keeping it here for reference if needed, but it's no longer imported by crm_lead_widget.js
// The functions are now directly in the relevant manager files.

export class UserPartnerManager {
  onUserSearchChange(event, state) {
    const searchTerm = event.target.value
    state.searchState.userSearch = searchTerm.toLowerCase()

    if (searchTerm.trim() === "") {
      state.formData.user_id = false
      state.isDirty = true
    }

    if (searchTerm) {
      state.searchState.filteredUsers = UserPartnerManager.filterUsers(state.availableUsers, searchTerm)
      state.searchState.showUserDropdown = true
      state.searchState.selectedUserIndex = 0
    } else {
      state.searchState.filteredUsers = state.availableUsers.slice(0, 5)
      state.searchState.showUserDropdown = false
    }
  }

  onUserFocus(state) {
    state.searchState.filteredUsers = state.availableUsers.slice(0, 5)
    state.searchState.showUserDropdown = true
    state.searchState.selectedUserIndex = 0
  }

  onUserBlur(state) {
    setTimeout(() => {
      state.searchState.showUserDropdown = false
    }, 200)
  }

  onUserKeyDown(event, state) {
    if (["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) {
      event.preventDefault()
    }

    this.handleKeyDown(event, "user", state)
  }

  onUserItemHover(index, state) {
    state.searchState.selectedUserIndex = index
  }

  onUserSelect(userId, userName, state) {
    state.formData.user_id = [userId, userName]
    state.searchState.userSearch = userName
    state.searchState.showUserDropdown = false
    state.isDirty = true
  }

  onPartnerSearchChange(event, state) {
    const searchTerm = event.target.value
    state.searchState.partnerSearch = searchTerm

    if (searchTerm.trim() === "") {
      state.formData.partner_id = false
      state.formData.email = ""
      state.isDirty = true
    }

    if (searchTerm) {
      state.searchState.filteredPartners = UserPartnerManager.filterPartners(state.availablePartners, searchTerm)
      state.searchState.showPartnerDropdown = true
      state.searchState.selectedPartnerIndex = 0
    } else {
      state.searchState.filteredPartners = state.availablePartners.slice(0, 5)
      state.searchState.showPartnerDropdown = false
    }
  }

  async onPartnerFocus(state) {
    state.searchState.filteredPartners = state.availablePartners.slice(0, 5)
    state.searchState.showPartnerDropdown = true
    state.searchState.selectedPartnerIndex = 0
  }

  onPartnerBlur(state) {
    setTimeout(() => {
      state.searchState.showPartnerDropdown = false
    }, 200)
  }

  onPartnerKeyDown(event, state) {
    if (["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) {
      event.preventDefault()
    }

    this.handleKeyDown(event, "partner", state)
  }

  onPartnerItemHover(index, state) {
    state.searchState.selectedPartnerIndex = index
  }

  onPartnerSelect(partnerId, partnerName, state) {
    const partner = state.availablePartners.find((p) => p[0] === partnerId)
    const email = partner && partner.length > 2 ? partner[2] : ""

    state.formData.partner_id = [partnerId, partnerName]
    state.formData.email = email
    state.searchState.partnerSearch = partnerName
    state.searchState.showPartnerDropdown = false
    state.isDirty = true
  }

  handleKeyDown(event, type, state) {
    const isUserDropdown = type === "user"
    const dropdownVisible = isUserDropdown ? state.searchState.showUserDropdown : state.searchState.showPartnerDropdown

    if (!dropdownVisible) {
      if (event.key === "ArrowDown") {
        if (isUserDropdown) {
          this.onUserFocus(state)
        } else {
          this.onPartnerFocus(state)
        }
      }
      return
    }

    const items = isUserDropdown ? state.searchState.filteredUsers : state.searchState.filteredPartners

    if (items.length === 0) return

    const currentIndex = isUserDropdown ? state.searchState.selectedUserIndex : state.searchState.selectedPartnerIndex

    switch (event.key) {
      case "ArrowDown":
        const nextIndex = (currentIndex + 1) % items.length
        if (isUserDropdown) {
          state.searchState.selectedUserIndex = nextIndex
        } else {
          state.searchState.selectedPartnerIndex = nextIndex
        }
        break

      case "ArrowUp":
        const prevIndex = (currentIndex - 1 + items.length) % items.length
        if (isUserDropdown) {
          state.searchState.selectedUserIndex = prevIndex
        } else {
          state.searchState.selectedPartnerIndex = prevIndex
        }
        break

      case "Enter":
        const selected = items[currentIndex]
        if (selected) {
          if (isUserDropdown) {
            this.onUserSelect(selected[0], selected[1], state)
          } else {
            this.onPartnerSelect(selected[0], selected[1], state)
          }
        }
        break

      case "Escape":
        if (isUserDropdown) {
          state.searchState.showUserDropdown = false
        } else {
          state.searchState.showPartnerDropdown = false
        }
        break
    }
  }

  static filterUsers(users, searchTerm) {
    if (!searchTerm) return users.slice(0, 5)

    return users
      .filter((user) => {
        return (
          user &&
          Array.isArray(user) &&
          user.length > 1 &&
          typeof user[1] === "string" &&
          user[1].toLowerCase().includes(searchTerm.toLowerCase())
        )
      })
      .slice(0, 5)
  }

  static filterPartners(partners, searchTerm) {
    if (!searchTerm) return partners.slice(0, 5)

    return partners
      .filter((partner) => {
        return (
          partner &&
          Array.isArray(partner) &&
          partner.length > 1 &&
          typeof partner[1] === "string" &&
          partner[1].toLowerCase().includes(searchTerm.toLowerCase())
        )
      })
      .slice(0, 5)
  }

  static filterCompanies(companies, searchTerm) {
    if (!searchTerm) return companies.slice(0, 5)

    return companies
      .filter((company) => {
        return (
          company &&
          Array.isArray(company) &&
          company.length > 1 &&
          typeof company[1] === "string" &&
          company[1].toLowerCase().includes(searchTerm.toLowerCase())
        )
      })
      .slice(0, 5)
  }
}
