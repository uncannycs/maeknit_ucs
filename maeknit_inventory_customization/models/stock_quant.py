from odoo import models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _get_forbidden_fields_write(self):
        fields = super()._get_forbidden_fields_write()
        if 'lot_id' in fields:
            fields.remove('lot_id')
        return fields
