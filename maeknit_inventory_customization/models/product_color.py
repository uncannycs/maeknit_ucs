from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ProductColor(models.Model):
    _name = 'product.color'
    _description = 'Product Color'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', ondelete='cascade')
    technical = fields.Char(string='Technical Color')
    generic = fields.Char(string='Generic Color')

    # Cost information
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id,
                                  required=True)
    cost = fields.Monetary(string='Cost', currency_field='currency_id',
                          help='Cost per unit for this color variant')

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

        return super().create(vals_list)

    def write(self, vals):
        """Sync cost changes to related yarn.stock records"""
        result = super().write(vals)

        # If cost was updated, sync to yarn.stock
        if 'cost' in vals:
            for record in self:
                # Find matching yarn.stock records
                YarnStock = self.env['yarn.stock']
                yarn_stocks = YarnStock.search([
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('technical_color', '=', record.technical or ''),
                    ('generic_color', '=', record.generic or '')
                ])

                # Update cost on matching yarn.stock records
                if yarn_stocks:
                    yarn_stocks.write({'cost': record.cost})

        return result

    @api.constrains('technical', 'generic')
    def _check_color_values(self):
        for record in self:
            if not record.technical and not record.generic:
                raise ValidationError("At least one of Technical or Generic color must be filled.")
