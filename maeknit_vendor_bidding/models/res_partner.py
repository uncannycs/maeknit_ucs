from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_generate_rfq_from_selection(self):
        """ Generate RFQs from a partner selection list view.
            Uses context to determine which Sales Order is being processed.
        """
        so_id = self.env.context.get('default_sale_order_id')
        if so_id:
            so = self.env['sale.order'].browse(so_id)
            if so.exists():
                return so._generate_rfqs_for_factories(self)
                
        # Fallback to active_id (the wizard)
        wizard_id = self.env.context.get('active_id')
        if wizard_id:
            wizard = self.env['sale.order.rfq.wizard'].browse(wizard_id)
            if wizard.exists() and wizard.sale_order_id:
                return wizard.sale_order_id._generate_rfqs_for_factories(self)
        
        raise UserError(_("Could not find the related Sales Order context. Please reopen the wizard."))
