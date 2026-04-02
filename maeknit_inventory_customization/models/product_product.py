from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.depends('product_template_attribute_value_ids', 'product_tmpl_id.name')
    def _compute_display_name(self):
        """Override to always show variant attributes in brackets, even for single variants"""
        for product in self:
            # Start with template name
            name = product.product_tmpl_id.name or ''

            # Get variant attributes
            variant_attrs = []
            if product.product_template_attribute_value_ids:
                for ptav in product.product_template_attribute_value_ids.sorted(
                    lambda x: x.attribute_id.sequence
                ):
                    attr_name = ptav.attribute_id.name
                    value_name = ptav.product_attribute_value_id.name
                    variant_attrs.append(f"{attr_name}: {value_name}")

            # Always show attributes in brackets if they exist
            if variant_attrs:
                name = f"{name} ({', '.join(variant_attrs)})"

            product.display_name = name
