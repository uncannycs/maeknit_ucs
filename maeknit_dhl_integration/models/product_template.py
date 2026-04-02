# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hs_code = fields.Char(string="HS Code", help="Standardized code for international trade.")
    country_of_origin = fields.Many2one('res.country', string="Country of Origin")
    is_dhl = fields.Boolean(string="Is DHL", help="Mark this product as a DHL service product for shipping/duty charges.")
    is_generated = fields.Boolean(string="Is Generated", default=False)
    lookup_id = fields.Char(string="Dutify ID", copy=False)
    product_classification_name = fields.Char(string="Hs Code Description", readonly=True, copy=False)
    yarn_product_name = fields.Char(string="Auto yarn product name", copy=False)

