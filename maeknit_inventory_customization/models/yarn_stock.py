from odoo import models, fields, api

class YarnStock(models.Model):
    _name = 'yarn.stock'
    _description = 'Yarn Stock'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', ondelete='cascade')
    
    # Color information
    technical_color = fields.Char(string='Technical Color')
    generic_color = fields.Char(string='Generic Color')
    lot_number = fields.Char(string='Lot #')

    # Cost information
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id,
                                  required=True)
    cost = fields.Monetary(string='Cost', currency_field='currency_id',
                          help='Cost per unit for this yarn variant')

    # Stock locations
    mk_us_stock = fields.Char(string='MK-US')
    mk_uk_stock = fields.Char(string='MK-UK')
    lf_stock = fields.Char(string='L&F')
    kadri_stock = fields.Char(string='Kadri')
    
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-populate cost from parent product if not provided"""
        for vals in vals_list:
            # If cost is not provided and product_tmpl_id exists, get cost from product
            if 'cost' not in vals or not vals.get('cost'):
                if vals.get('product_tmpl_id'):
                    product = self.env['product.template'].browse(vals['product_tmpl_id'])
                    if product:
                        # Use standard_price (Cost field on product)
                        vals['cost'] = product.standard_price or 0.0

        records = super().create(vals_list)

        # Sync cost to related product variants
        for record in records:
            record._sync_cost_to_variants()

        return records

    def write(self, vals):
        """Sync cost to related product variants when cost is updated"""
        result = super().write(vals)

        # If cost was updated, sync to variants
        if 'cost' in vals:
            for record in self:
                record._sync_cost_to_variants()

        return result

    def _sync_cost_to_variants(self):
        """Find and update product variants that match this yarn stock's colors"""
        import logging
        self.ensure_one()

        if not self.product_tmpl_id:
            return

        # Determine which cost to use: yarn.stock cost or template cost as fallback
        # If yarn.stock cost is 0, use template's cost
        cost_to_use = self.cost if self.cost else (self.product_tmpl_id.cost_price or self.product_tmpl_id.standard_price)

        if not cost_to_use:
            logging.info(f"Yarn Stock Sync: No cost available for variant (yarn.stock cost={self.cost}, template cost={self.product_tmpl_id.standard_price})")
            return

        # Build list of possible color name formats to try
        possible_colors = []
        if self.technical_color and self.generic_color:
            # Try multiple common formats
            possible_colors.append(f"{self.technical_color} {self.generic_color}")  # Space-separated
            possible_colors.append(f"{self.technical_color} ({self.generic_color})")  # With parentheses
            possible_colors.append(f"{self.technical_color}{self.generic_color}")  # No separator
        if self.technical_color:
            possible_colors.append(self.technical_color)
        if self.generic_color:
            possible_colors.append(self.generic_color)

        if not possible_colors:
            return

        logging.info(f"Yarn Stock Sync: Looking for variants matching colors: {possible_colors}")

        # Find variants with matching color attribute values
        ProductProduct = self.env['product.product']
        variants = ProductProduct.search([
            ('product_tmpl_id', '=', self.product_tmpl_id.id)
        ])

        logging.info(f"Yarn Stock Sync: Found {len(variants)} total variants for product")

        matched_count = 0
        for variant in variants:
            # Check if this variant matches the yarn stock colors
            color_match = False
            variant_color = None
            for ptav in variant.product_template_attribute_value_ids:
                if ptav.attribute_id.name == 'Color':
                    variant_color = ptav.product_attribute_value_id.name
                    if variant_color in possible_colors:
                        color_match = True
                        break

            if variant_color:
                logging.info(f"Yarn Stock Sync: Variant {variant.id} has color '{variant_color}' - Match: {color_match}")

            if color_match:
                # Update variant's standard_price
                variant.write({'standard_price': cost_to_use})
                matched_count += 1
                logging.info(f"Yarn Stock Sync: Updated variant {variant.id} cost to {cost_to_use}")

        logging.info(f"Yarn Stock Sync: Updated {matched_count} variants with cost {cost_to_use}")

    # Display name for the record
    @api.depends('technical_color', 'generic_color', 'lot_number')
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.technical_color or ''}"
            if record.generic_color:
                name += f" ({record.generic_color})"
            if record.lot_number:
                name += f" - Lot: {record.lot_number}"
            result.append((record.id, name))
        return result
