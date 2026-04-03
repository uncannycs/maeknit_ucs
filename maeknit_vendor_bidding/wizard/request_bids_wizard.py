from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class RequestBidsWizard(models.TransientModel):
    _name = 'sale.order.rfq.wizard'
    _description = 'Request Bids Wizard'

    sale_order_id = fields.Many2one('sale.order', string='Sales Order', required=True)
    search_partner_id = fields.Many2one('res.partner', string='Search Factory', domain="[('contact_type', '=', 'factory')]")
    factory_ids = fields.Many2many('res.partner', 'sale_order_rfq_wizard_factory_rel', 'wizard_id', 'partner_id', string='Selected Factories', domain="[('contact_type', '=', 'factory')]")


    @api.onchange('search_partner_id')
    def _onchange_search_partner_id(self):
        """Add selected partner to factory_ids list and clear the search box."""
        if self.search_partner_id:
            if self.search_partner_id not in self.factory_ids:
                self.factory_ids = [(4, self.search_partner_id.id)]
            self.search_partner_id = False

    def action_generate_rfqs(self):
        self.ensure_one()
        if not self.factory_ids:
            raise UserError(_('Please select at least one factory.'))

        return self.sale_order_id._generate_rfqs_for_factories(self.factory_ids)
