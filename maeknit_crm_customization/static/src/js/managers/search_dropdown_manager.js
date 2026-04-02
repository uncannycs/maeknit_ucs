/** @odoo-module **/

import { safeErrorString } from "../utils/helpers"

export class SearchDropdownManager {
  constructor(orm, state) {
    this.orm = orm
    this.state = state
  }

  // --- User Search ---
  onUserSearchChange(event, availableUsers) {
    const searchTerm = event.target.value
    this.state.searchState.userSearch = searchTerm.toLowerCase()

    if (searchTerm.trim() === "") {
      this.state.formData.user_id = false
      this.state.isDirty = true
    }

    if (searchTerm) {
      this.state.searchState.filteredUsers = this._filterItems(availableUsers, searchTerm)
      this.state.searchState.showUserDropdown = true
      this.state.searchState.selectedUserIndex = 0
    } else {
      this.state.searchState.filteredUsers = availableUsers.slice(0, 5)
      this.state.searchState.showUserDropdown = false
    }
  }

  onUserFocus(availableUsers) {
    this.state.searchState.filteredUsers = availableUsers.slice(0, 5)
    this.state.searchState.showUserDropdown = true
    this.state.searchState.selectedUserIndex = 0
  }

  onUserBlur() {
    setTimeout(() => {
      this.state.searchState.showUserDropdown = false
    }, 200)
  }

  onUserKeyDown(event) {
    if (["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) {
      event.preventDefault()
    }
    this._handleKeyDown(event, "user")
  }

  onUserItemHover(index) {
    this.state.searchState.selectedUserIndex = index
  }

  onUserSelect(userId, userName) {
    this.state.formData.user_id = [userId, userName]
    this.state.searchState.userSearch = userName
    this.state.searchState.showUserDropdown = false
    this.state.isDirty = true
  }

  // --- Partner Search ---
  onPartnerSearchChange(event, availablePartners) {
    const searchTerm = event.target.value
    this.state.searchState.partnerSearch = searchTerm

    if (searchTerm.trim() === "") {
      this.state.formData.partner_id = false
      this.state.formData.email = ""
      this.state.isDirty = true
    }

    if (searchTerm) {
      this.state.searchState.filteredPartners = this._filterItems(availablePartners, searchTerm)
      this.state.searchState.showPartnerDropdown = true
      this.state.searchState.selectedPartnerIndex = 0
    } else {
      this.state.searchState.filteredPartners = availablePartners.slice(0, 5)
      this.state.searchState.showPartnerDropdown = false
    }
  }

  onPartnerFocus(availablePartners) {
    this.state.searchState.filteredPartners = availablePartners.slice(0, 5)
    this.state.searchState.showPartnerDropdown = true
    this.state.searchState.selectedPartnerIndex = 0
  }

  onPartnerBlur() {
    setTimeout(() => {
      this.state.searchState.showPartnerDropdown = false
    }, 200)
  }

  onPartnerKeyDown(event) {
    if (["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) {
      event.preventDefault()
    }
    this._handleKeyDown(event, "partner")
  }

  onPartnerItemHover(index) {
    this.state.searchState.selectedPartnerIndex = index
  }

  async onPartnerSelect(partnerId, partnerName, availablePartners) {
    const partner = availablePartners.find((p) => p[0] === partnerId);
    const email = partner && partner.length > 2 ? partner[2] : "";

    this.state.formData.partner_id = [partnerId, partnerName];
    this.state.formData.email = email;
    this.state.searchState.partnerSearch = partnerName;
    this.state.searchState.showPartnerDropdown = false;
    this.state.isDirty = true;

    try {
        const orm = this.orm || this.env.services.orm; 
        if (!this.props.recordId) {
            console.warn("No recordId found, cannot auto-save partner.");
            return;
        }

        await orm.write("crm.lead", [this.props.recordId], {
            partner_id: partnerId,
            email_from: email || false,
        });
    } catch (error) {
        console.error("Failed to save client:", error);
    }
}


  // --- Parent Lead Search ---
  onParentLeadSearchChange(event, currentRecordId) {
    const searchTerm = event.target.value
    this.state.searchState.parentLeadSearch = searchTerm

    if (searchTerm.trim() === "") {
      this.state.formData.parent_id = false
      this.state.isDirty = true
    }

    if (searchTerm) {
      this._searchLeads(searchTerm, currentRecordId)
    } else {
      this.state.searchState.filteredLeads = []
      this.state.searchState.showParentLeadDropdown = false
    }
  }

  async _searchLeads(searchTerm, currentRecordId) {
    try {
      const leads = await this.orm.call(
        "crm.lead",
        "search_read",
        [
          [
            ["name", "ilike", searchTerm],
            ["id", "!=", currentRecordId || 0],
          ],
        ],
        {
          fields: ["id", "name"],
          limit: 10,
        },
      )

      this.state.searchState.filteredLeads = leads.map((lead) => [lead.id, lead.name])
      this.state.searchState.showParentLeadDropdown = leads.length > 0
      this.state.searchState.selectedParentLeadIndex = 0
    } catch (error) {
      const errorString = safeErrorString(error)
      console.error("Error searching leads:", errorString)
      this.state.debugInfo.errors.push("Error searching leads: " + errorString)
    }
  }

  onParentLeadFocus(currentRecordId) {
    if (this.state.searchState.parentLeadSearch) {
      this._searchLeads(this.state.searchState.parentLeadSearch, currentRecordId)
    }
  }

  onParentLeadBlur() {
    setTimeout(() => {
      this.state.searchState.showParentLeadDropdown = false
    }, 200)
  }

  onParentLeadKeyDown(event) {
    if (["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) {
      event.preventDefault()
    }
    this._handleKeyDown(event, "parentLead")
  }

  onParentLeadItemHover(index) {
    this.state.searchState.selectedParentLeadIndex = index
  }

  onParentLeadSelect(leadId, leadName) {
    this.state.formData.parent_id = [leadId, leadName]
    this.state.searchState.parentLeadSearch = leadName
    this.state.searchState.showParentLeadDropdown = false
    this.state.isDirty = true
  }

  // --- Company Search ---
  onCompanySearchChange(event, availableCompanies) {
    const searchTerm = event.target.value
    this.state.searchState.companySearch = searchTerm

    if (searchTerm.trim() === "") {
      this.state.formData.company_id = false
      this.state.isDirty = true
    }

    if (searchTerm) {
      this.state.searchState.filteredCompanies = this._filterItems(availableCompanies, searchTerm)
      this.state.searchState.showCompanyDropdown = true
      this.state.searchState.selectedCompanyIndex = 0
    } else {
      this.state.searchState.filteredCompanies = availableCompanies.slice(0, 5)
      this.state.searchState.showCompanyDropdown = false
    }
  }

  onCompanyFocus(availableCompanies) {
    this.state.searchState.filteredCompanies = availableCompanies.slice(0, 5)
    this.state.searchState.showCompanyDropdown = true
    this.state.searchState.selectedCompanyIndex = 0
  }

  onCompanyBlur() {
    setTimeout(() => {
      this.state.searchState.showCompanyDropdown = false
    }, 200)
  }

  onCompanyKeyDown(event) {
    if (["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) {
      event.preventDefault()
    }
    this._handleKeyDown(event, "company")
  }

  onCompanyItemHover(index) {
    this.state.searchState.selectedCompanyIndex = index
  }

  onCompanySelect(companyId, companyName) {
    this.state.formData.company_id = [companyId, companyName]
    this.state.searchState.companySearch = companyName
    this.state.searchState.showCompanyDropdown = false
    this.state.isDirty = true
  }

  // --- General Keyboard Navigation for Dropdowns ---
  _handleKeyDown(event, type) {
    const searchState = this.state.searchState
    let dropdownVisible, items, currentIndex, selectedIndexKey

    switch (type) {
      case "user":
        dropdownVisible = searchState.showUserDropdown
        items = searchState.filteredUsers
        currentIndex = searchState.selectedUserIndex
        selectedIndexKey = "selectedUserIndex"
        break
      case "partner":
        dropdownVisible = searchState.showPartnerDropdown
        items = searchState.filteredPartners
        currentIndex = searchState.selectedPartnerIndex
        selectedIndexKey = "selectedPartnerIndex"
        break
      case "parentLead":
        dropdownVisible = searchState.showParentLeadDropdown
        items = searchState.filteredLeads
        currentIndex = searchState.selectedParentLeadIndex
        selectedIndexKey = "selectedParentLeadIndex"
        break
      case "company":
        dropdownVisible = searchState.showCompanyDropdown
        items = searchState.filteredCompanies
        currentIndex = searchState.selectedCompanyIndex
        selectedIndexKey = "selectedCompanyIndex"
        break
      default:
        return
    }

    if (!dropdownVisible) {
      if (event.key === "ArrowDown") {
        if (type === "user") this.onUserFocus(this.state.availableUsers)
        else if (type === "partner") this.onPartnerFocus(this.state.availablePartners)
        else if (type === "parentLead") this.onParentLeadFocus(this.props.record?.resId)
        else if (type === "company") this.onCompanyFocus(this.state.availableCompanies)
      }
      return
    }

    if (items.length === 0) return

    switch (event.key) {
      case "ArrowDown":
        searchState[selectedIndexKey] = (currentIndex + 1) % items.length
        break
      case "ArrowUp":
        searchState[selectedIndexKey] = (currentIndex - 1 + items.length) % items.length
        break
      case "Enter":
        const selected = items[currentIndex]
        if (selected) {
          if (type === "user") this.onUserSelect(selected[0], selected[1])
          else if (type === "partner") this.onPartnerSelect(selected[0], selected[1], this.state.availablePartners)
          else if (type === "parentLead") this.onParentLeadSelect(selected[0], selected[1])
          else if (type === "company") this.onCompanySelect(selected[0], selected[1])
        }
        break
      case "Escape":
        if (type === "user") searchState.showUserDropdown = false
        else if (type === "partner") searchState.showPartnerDropdown = false
        else if (type === "parentLead") searchState.showParentLeadDropdown = false
        else if (type === "company") searchState.showCompanyDropdown = false
        break
    }
  }

  _filterItems(items, searchTerm) {
    if (!searchTerm) return items.slice(0, 5)

    return items
      .filter((item) => {
        return (
          item &&
          Array.isArray(item) &&
          item.length > 1 &&
          typeof item[1] === "string" &&
          item[1].toLowerCase().includes(searchTerm.toLowerCase())
        )
      })
      .slice(0, 5)
  }
}
