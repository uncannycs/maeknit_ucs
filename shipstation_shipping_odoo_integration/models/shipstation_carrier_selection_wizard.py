from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

class ShipstationCarrierSelectionWizard(models.TransientModel):
    _name = 'shipstation.carrier.selection.wizard'
    _description = 'ShipStation Carrier Selection Wizard'

    picking_id = fields.Many2one('stock.picking', string='Picking', required=True)
    package_id = fields.Many2one('stock.quant.package', string='Package')
    
    carrier_ids = fields.Many2many(
        'shipstation.delivery.carrier',
        string='Available Carriers',
        compute='_compute_available_carriers'
    )
    
    selected_carrier_ids = fields.Many2many(
        'shipstation.delivery.carrier',
        'wizard_carrier_rel',
        'wizard_id',
        'carrier_id',
        string='Selected Carriers'
    )
    
    fetch_mode = fields.Selection([
        ('combined', 'Combined (Top 10 Cheapest)'),
        ('specific', 'Specific Carriers'),
    ], string='Fetch Mode', default='combined', required=True)
    
    rate_ids = fields.One2many(
        'shipstation.shipping.charge',
        'picking_id',
        related='picking_id.shipstation_shipping_charge_ids',
        string='Available Rates'
    )
    
    selected_rate_id = fields.Many2one(
        'shipstation.shipping.charge',
        string='Selected Rate'
    )
    
    state = fields.Selection([
        ('select', 'Select Carriers'),
        ('rates', 'View Rates'),
    ], default='select', string='State')
    
    error_messages = fields.Text(string='Error Messages', readonly=True)

    @api.depends('picking_id')
    def _compute_available_carriers(self):
        """Get all available carriers from the system"""
        for wizard in self:
            carriers = self.env['shipstation.delivery.carrier'].search([
                ('code', 'in', ['stamps_com', 'ups_walleted', 'fedex_walleted'])
            ])
            wizard.carrier_ids = carriers

    def action_fetch_rates(self, residential=False):
        """Fetch rates based on selected carriers"""
        self.ensure_one()
        if not self.picking_id.carrier_id:
            raise ValidationError("Please select a delivery carrier on the picking.")

        # Clear existing rates
        self.picking_id.shipstation_shipping_charge_ids.unlink()
        
        errors = []
        success_count = 0
        
        if self.fetch_mode == 'combined':
            carriers_to_check = self.carrier_ids.mapped('code')
        else:
            if not self.selected_carrier_ids:
                raise ValidationError("Please select at least one carrier.")
            carriers_to_check = self.selected_carrier_ids.mapped('code')
        
        logging.info(f" Custom Code: Fetching rates for carriers: {carriers_to_check}")
        
        for carrier_code in carriers_to_check:
            try:
                result = self.picking_id.carrier_id.shipstation_rate_shipment_picking(
                    self.picking_id,
                    carrier_code=carrier_code,
                    residential=residential,
                    package_id=self.package_id,
                )
                if result.get('success'):
                    success_count += 1
                    logging.info(f" Custom Code: Successfully fetched rates for {carrier_code}")
                else:
                    error_msg = result.get('error_message', 'Unknown error')
                    errors.append(f"{carrier_code}: {error_msg}")
                    logging.warning(f"Failed to fetch rates for {carrier_code}: {error_msg}")
            except Exception as e:
                errors.append(f"{carrier_code}: {str(e)}")
                logging.error(f"Exception fetching rates for {carrier_code}: {e}")
                continue
        
        self.env.cr.commit()
        
        if self.fetch_mode == 'combined':
            all_rate_records = self.picking_id.shipstation_shipping_charge_ids
            if len(all_rate_records) > 10:
                sorted_rates = all_rate_records.sorted(key=lambda r: r.shipping_cost + r.other_cost)
                rates_to_keep = sorted_rates[:10]
                rates_to_remove = all_rate_records - rates_to_keep
                rates_to_remove.unlink()
                self.env.cr.commit()
        
        error_text = "\n".join(errors) if errors else ""
        if success_count == 0:
            self.error_messages = f"No rates found.\n\nErrors:\n{error_text}"
        else:
            self.error_messages = f"Found {success_count} carrier(s) with rates.\n\nErrors:\n{error_text}" if errors else f"Successfully fetched rates from {success_count} carrier(s)."
        
        self.state = 'rates'
        
        logging.info(f" Custom Code: Returning success with {len(self.picking_id.shipstation_shipping_charge_ids)} rates")
        return {
            'success': True,
            'rate_count': len(self.picking_id.shipstation_shipping_charge_ids),
            'error_messages': error_text,
        }
    
    def action_select_rate(self):
        """Select a rate and update picking carrier/package"""
        self.ensure_one()
        
        if not self.selected_rate_id:
            raise ValidationError("Please select a rate first.")
        
        self.selected_rate_id.set_picking_service()
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_back_to_selection(self):
        """Go back to carrier selection"""
        self.ensure_one()
        self.state = 'select'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'shipstation.carrier.selection.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
