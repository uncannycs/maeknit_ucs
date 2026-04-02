from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ProductFiber(models.Model):
    _name = 'product.fiber'
    _description = 'Product Fiber Composition'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', ondelete='cascade')
    percentage = fields.Integer(string='Percentage', default=100)

    # Replace Selection field with Many2one relationship
    fiber_type_id = fields.Many2one('fiber.type', string='Fiber Type', required=True)

    @api.constrains('percentage')
    def _check_percentage(self):
        for record in self:
            if record.percentage <= 0 or record.percentage > 100:
                raise ValidationError("Percentage must be between 1 and 100.")
