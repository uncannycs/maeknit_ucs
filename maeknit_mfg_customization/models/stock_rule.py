from odoo import models

class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _run_manufacture(self, procurements):
        """
        Create/confirm the MO via super(), then push every
        just-created MO back to *draft*.
        """
        
        if self.env.context.get('skip_mo_creation'):
            return True
        
        max_id_before = self.env['mrp.production'].search([], order='id desc', limit=1).id or 0

        super_result = super()._run_manufacture(procurements)

        new_mos = self.env['mrp.production'].search([('id', '>', max_id_before)])

        if new_mos:
            new_mos.write({'state': 'draft', 'is_locked': False})

        return super_result
