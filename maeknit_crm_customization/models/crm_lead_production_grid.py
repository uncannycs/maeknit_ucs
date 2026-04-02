from odoo import models, fields, api
import logging

class CrmLeadProductionGrid(models.Model):
    """
    Model to store production grid data for CRM leads.
    Each record represents a cell in the grid (product variant + quantity + price).
    """
    _name = 'crm.lead.production.grid'
    _description = 'CRM Lead Production Grid'
    _order = 'lead_id, product_id, sequence'

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        required=True,
        ondelete='cascade',
        index=True
    )

    product_id = fields.Many2one(
        'product.template',
        string='Product',
        required=True,
        ondelete='cascade'
    )

    variant_id = fields.Many2one(
        'product.product',
        string='Product Variant',
        help='Specific variant (Size + Colorway combination). NULL if product has no variants.'
    )

    size_id = fields.Many2one(
        'product.attribute.value',
        string='Size',
        domain="[('attribute_id.name', '=', 'Size')]"
    )

    colorway_id = fields.Many2one(
        'product.attribute.value',
        string='Colorway',
        domain="[('attribute_id.name', '=', 'Colorway')]"
    )

    quantity = fields.Float(
        string='Quantity',
        default=0.0,
        digits='Product Unit of Measure'
    )

    unit_price = fields.Float(
        string='Unit Price',
        default=0.0,
        digits='Product Price'
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Used for ordering in the grid'
    )

    # Computed fields for easy display
    product_name = fields.Char(
        related='product_id.name',
        string='Product Name',
        readonly=True
    )

    size_name = fields.Char(
        related='size_id.name',
        string='Size Name',
        readonly=True
    )

    colorway_name = fields.Char(
        related='colorway_id.name',
        string='Colorway Name',
        readonly=True
    )

    @api.model
    def get_or_create_grid_line(self, lead_id, product_id, size_id=None, colorway_id=None):
        """
        Get existing or create new grid line for a specific combination
        """
        domain = [
            ('lead_id', '=', lead_id),
            ('product_id', '=', product_id),
        ]

        if size_id:
            domain.append(('size_id', '=', size_id))
        else:
            domain.append(('size_id', '=', False))

        if colorway_id:
            domain.append(('colorway_id', '=', colorway_id))
        else:
            domain.append(('colorway_id', '=', False))

        existing = self.search(domain, limit=1)

        if existing:
            return existing

        return self.create({
            'lead_id': lead_id,
            'product_id': product_id,
            'size_id': size_id,
            'colorway_id': colorway_id,
            'quantity': 0.0,
            'unit_price': 0.0,
        })

    @api.model
    def clear_lead_grid(self, lead_id):
        """
        Clear all grid lines for a lead
        """
        self.search([('lead_id', '=', lead_id)]).unlink()
        return True

    @api.model
    def get_lines_with_quantity(self, lead_id):
        """
        Get all grid lines with quantity > 0 for quote generation
        """
        return self.search([
            ('lead_id', '=', lead_id),
            ('quantity', '>', 0)
        ])
