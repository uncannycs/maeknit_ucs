import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ShipstationGenerateAllLabelsWizard(models.TransientModel):
    _name = 'shipstation.generate.all.labels.wizard'
    _description = 'ShipStation Generate All Labels Wizard'

    picking_id = fields.Many2one('stock.picking', string='Delivery Order', required=True)
    partner_id = fields.Many2one(
        'res.partner', string='Delivery Address',
        related='picking_id.partner_id', readonly=True)
    partner_street = fields.Char(related='partner_id.street', readonly=True)
    partner_street2 = fields.Char(related='partner_id.street2', readonly=True)
    partner_city = fields.Char(related='partner_id.city', readonly=True)
    partner_state = fields.Char(
        related='partner_id.state_id.name', string='State', readonly=True)
    partner_zip = fields.Char(related='partner_id.zip', readonly=True)
    partner_country = fields.Char(
        related='partner_id.country_id.name', string='Country', readonly=True)

    package_ids = fields.Many2many(
        'stock.quant.package', string='Packages',
        compute='_compute_package_ids')
    package_count = fields.Integer(
        string='Package Count', compute='_compute_package_ids')

    carrier_id = fields.Many2one(
        'delivery.carrier', string='Carrier',
        related='picking_id.carrier_id', readonly=True)
    shipping_charge_id = fields.Many2one(
        'shipstation.shipping.charge', string='Selected Service',
        related='picking_id.shipstation_shipping_charge_id', readonly=True)

    @api.depends('picking_id')
    def _compute_package_ids(self):
        for wizard in self:
            packages = wizard.picking_id.move_line_ids.mapped('result_package_id').filtered(
                lambda p: p.is_generate_label_in_shipstation)
            wizard.package_ids = packages
            wizard.package_count = len(packages)

    def action_check_rates(self):
        """Open the carrier selection / rate checking wizard for this picking."""
        self.ensure_one()
        return self.picking_id.button_check_shipstation_rates()

    def action_generate_all_labels(self):
        """Generate labels for all packages on the picking."""
        self.ensure_one()
        if not self.package_ids:
            raise ValidationError(_("No packages found to generate labels for."))
        if not self.picking_id.shipstation_shipping_charge_id:
            raise ValidationError(
                _("Please check rates and select a shipping service first."))
        return self.picking_id.generate_label_from_shipstation()
