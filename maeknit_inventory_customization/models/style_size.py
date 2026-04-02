from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

class StyleSize(models.Model):
    """
    Style-specific size management table.
    This allows each style (product template) to have its own set of sizes
    that are unique to that style, while still maintaining the global size library.
    """
    _name = 'style.size'
    _description = 'Style-Specific Size'
    _rec_name = 'size_name'
    _order = 'product_tmpl_id, sequence, size_name'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Style',
        required=True,
        ondelete='cascade',
        help="The style/product template this size belongs to"
    )

    size_id = fields.Many2one(
        'product.attribute.value',
        string='Global Size',
        domain="[('attribute_id.name', '=', 'Size')]",
        required=True,
        help="Reference to the global size from product.attribute.value"
    )

    size_name = fields.Char(
        string='Size Name',
        related='size_id.name',
        help="Name of the size for easy searching and display"
    )

    style_name = fields.Char(
        string='Style Name',
        related='product_tmpl_id.name',
        help="Name of the style for easy reference"
    )

    active = fields.Boolean(default=True, help="Set to false to archive this size for the style")
    sequence = fields.Integer(default=10, help="Sequence for ordering sizes within a style")

    created_by_bom = fields.Boolean(
        string='Created by BOM',
        default=False,
        help="True if this size was automatically created when a BOM was made"
    )

    @api.constrains('product_tmpl_id', 'size_id')
    def _check_unique_size_per_style(self):
        """Ensure each size is unique per style"""
        for record in self:
            if record.product_tmpl_id and record.size_id:
                duplicate = self.search([
                    ('id', '!=', record.id),
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('size_id', '=', record.size_id.id)
                ], limit=1)

                if duplicate:
                    raise ValidationError(
                        f"Size '{record.size_name}' already exists for style '{record.style_name}'. "
                        "Each size can only be added once per style."
                    )

    @api.model
    def get_or_create_style_size(self, product_tmpl_id, size_id):
        """
        Get existing or create new style-specific size.
        This is used when BOMs are created to automatically add sizes to styles.
        """
        existing = self.search([
            ('product_tmpl_id', '=', product_tmpl_id),
            ('size_id', '=', size_id)
        ], limit=1)

        if existing:
            return existing

        return self.create({
            'product_tmpl_id': product_tmpl_id,
            'size_id': size_id,
            'created_by_bom': True
        })

    @api.model
    def get_sizes_for_style(self, product_tmpl_id):
        """Get all sizes available for a specific style."""
        style_sizes = self.search([
            ('product_tmpl_id', '=', product_tmpl_id),
            ('active', '=', True)
        ])
        return style_sizes.mapped('size_id')

    def name_get(self):
        """Custom name display: Style - Size"""
        result = []
        for record in self:
            name = f"{record.style_name} - {record.size_name}"
            result.append((record.id, name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Enhanced search to find by style name or size name"""
        if args is None:
            args = []

        if name:
            domain = ['|',
                     ('size_name', operator, name),
                     ('style_name', operator, name)]
            records = self.search(domain + args, limit=limit)
            return records.name_get()

        return super().name_search(name, args, operator, limit)
