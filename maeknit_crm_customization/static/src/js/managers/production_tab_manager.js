/** @odoo-module **/

export class ProductionTabManager {
  constructor(state, orm) {
    this.state = state
    this.orm = orm
  }

  async loadProductionGrid(leadId) {
    /**
     * Load production grid data from backend
     */
    try {
      const result = await this.orm.call("crm.lead", "get_production_grid_data", [[leadId]])

      // Store in state
      this.state.formData.productionGrid = {
        products: result.products || [],
        has_products: result.has_products || false,
        all_colorways: result.all_colorways || [],
        all_sizes: result.all_sizes || [],
        grid_data: result.grid_data || {},
        currency_symbol: result.currency_symbol || '$',
        is_dirty: false,
      }

      return result
    } catch (error) {
      console.error("Error loading production grid:", error)
      this.state.formData.productionGrid = {
        products: [],
        has_products: false,
        all_colorways: [],
        all_sizes: [],
        grid_data: {},
        currency_symbol: '$',
        is_dirty: false,
      }
      return null
    }
  }

  getGridCellValue(productId, sizeId, colorwayId, field) {
    /**
     * Get quantity or price for a specific cell
     */
    if (!this.state.formData.productionGrid) {
      return field === "quantity" ? 0 : 0.0
    }

    const key = `${productId}_${sizeId || 0}_${colorwayId || 0}`
    const cellData = this.state.formData.productionGrid.grid_data[key]

    if (!cellData) {
      return field === "quantity" ? 0 : 0.0
    }

    return cellData[field] || (field === "quantity" ? 0 : 0.0)
  }

  onGridCellChange(productId, sizeId, colorwayId, field, value) {
    /**
     * Update a cell value in the grid
     */
    if (!this.state.formData.productionGrid) {
      this.state.formData.productionGrid = {
        products: [],
        has_products: false,
        all_colorways: [],
        all_sizes: [],
        grid_data: {},
        currency_symbol: '$',
        is_dirty: false,
      }
    }

    const key = `${productId}_${sizeId || 0}_${colorwayId || 0}`

    if (!this.state.formData.productionGrid.grid_data[key]) {
      this.state.formData.productionGrid.grid_data[key] = {
        quantity: 0,
        price: 0.0,
      }
    }

    // Parse value
    let parsedValue = 0
    if (field === "quantity") {
      parsedValue = parseInt(value) || 0
    } else {
      parsedValue = parseFloat(value) || 0.0
    }

    this.state.formData.productionGrid.grid_data[key][field] = parsedValue
    this.state.formData.productionGrid.is_dirty = true
    this.state.isDirty = true
  }

  async saveProductionGrid(leadId) {
    /**
     * Save production grid data to backend
     */
    if (!this.state.formData.productionGrid || !this.state.formData.productionGrid.is_dirty) {
      return true
    }

    try {
      await this.orm.call("crm.lead", "save_production_grid", [[leadId], this.state.formData.productionGrid.grid_data])
      this.state.formData.productionGrid.is_dirty = false
      return true
    } catch (error) {
      console.error("Error saving production grid:", error)
      return false
    }
  }

  async createProductsForProduction(leadId) {
    /**
     * Pull products from the Products Tab and link them to the production grid.
     */
    try {
      await this.orm.call("crm.lead", "create_products_for_production", [[leadId]])
      // Reload the grid
      await this.loadProductionGrid(leadId)
      return true
    } catch (error) {
      console.error("Error creating products:", error)
      return false
    }
  }

  async addProductToProduction(leadId, productTmplId) {
    /**
     * Manually add a specific product template to the production grid.
     * Returns the fresh grid data so the caller can update state.
     */
    const result = await this.orm.call("crm.lead", "add_product_to_production", [[leadId], productTmplId])
    return result
  }

  async removeProductFromProduction(leadId, productTmplId) {
    /**
     * Remove a product template from the production grid.
     * Returns the fresh grid data so the caller can update state.
     */
    const result = await this.orm.call("crm.lead", "remove_product_from_production", [[leadId], productTmplId])
    return result
  }

  async searchProductsForProduction(leadId, searchTerm) {
    /**
     * Search all product templates with no domain restrictions.
     */
    try {
      const results = await this.orm.call("crm.lead", "search_products_for_production", [leadId, searchTerm])
      return results || []
    } catch (error) {
      console.error("Error searching products:", error)
      return []
    }
  }

  async generateQuoteFromGrid(leadId) {
    /**
     * Generate sale order from production grid
     */
    try {
      // First save any changes
      await this.saveProductionGrid(leadId)

      // Generate quote
      const result = await this.orm.call("crm.lead", "generate_quote_from_production_grid", [[leadId]])
      return result
    } catch (error) {
      console.error("Error generating quote from grid:", error)
      throw error
    }
  }

  async generatePricesFromCost(leadId) {
    /**
     * Populate unit prices in the production grid from each product's cost price
     */
    try {
      const result = await this.orm.call("crm.lead", "generate_production_prices_from_cost", [[leadId]])
      return result
    } catch (error) {
      console.error("Error generating prices from cost:", error)
      throw error
    }
  }

  getProductRowspan(product) {
    /**
     * Calculate rowspan for product name cell (merged cells)
     */
    if (!product || !product.has_variants || !product.sizes || product.sizes.length === 0) {
      return 1
    }
    return product.sizes.length
  }

  hasAnyQuantity() {
    /**
     * Check if any cell has quantity > 0
     */
    if (!this.state.formData.productionGrid || !this.state.formData.productionGrid.grid_data) {
      return false
    }

    return Object.values(this.state.formData.productionGrid.grid_data).some((cell) => cell.quantity > 0)
  }
}
