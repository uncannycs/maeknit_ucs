from odoo import models, fields, api
from odoo.exceptions import ValidationError

class StyleYarnVariant(models.Model):
    _name = 'style.yarn.variant'
    _description = 'Style-Specific Yarn Variant'
    _rec_name = 'yarn_variant_name'

    product_tmpl_id = fields.Many2one('product.template', string='Style', required=True, ondelete='cascade')
    yarn_variant_id = fields.Many2one('product.attribute.value', string='Yarn Variant', 
                                      domain="[('attribute_id.name', '=', 'Yarn Variant')]", required=True)
    
    yarn_variant_name = fields.Char(related='yarn_variant_id.name', string='Yarn Variant Name')
    style_name = fields.Char(related='product_tmpl_id.name', string='Style Name')
    
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('unique_style_yarn', 'unique(product_tmpl_id, yarn_variant_id)', 'Yarn variant must be unique per style.')
    ]

    @api.model
    def get_or_create(self, product_tmpl_id, yarn_variant_id):
        record = self.search([('product_tmpl_id', '=', product_tmpl_id), ('yarn_variant_id', '=', yarn_variant_id)], limit=1)
        if not record:
            record = self.create({'product_tmpl_id': product_tmpl_id, 'yarn_variant_id': yarn_variant_id})
        return record
