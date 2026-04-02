from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class RequestBidsWizard(models.TransientModel):
    _name = 'sale.order.rfq.wizard'
    _description = 'Request Bids Wizard'

    sale_order_id = fields.Many2one('sale.order', string='Sales Order', required=True)
    factory_ids = fields.Many2many('res.partner', string='Factories', domain="[('contact_type', '=', 'factory')]")

    def action_generate_rfqs(self):
        self.ensure_one()
        if not self.factory_ids:
            raise UserError(_('Please select at least one factory.'))

        return self.sale_order_id._generate_rfqs_for_factories(self.factory_ids)
