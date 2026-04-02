from odoo import models,fields,api

class ShipstationShippingCharge(models.Model):
    _name="shipstation.shipping.charge"
    _description = 'Shipstation Shipping Charge'
    _rec_name="shipstation_service_code"

    shipstation_provider=fields.Char(string="Provider",help="Shipping Provider")
    shipstation_service_code = fields.Char(string="Service Code", help="Shipping service Code.")
    shipstation_service_name=fields.Char(string="Service Name",help="Shipping service name.")
    shipping_cost=fields.Float(string="Shipping Cost",help="Rate given by shippo")
    other_cost = fields.Float(string='Other Cost')
    sale_order_id=fields.Many2one("sale.order",string="Sales Order")
    picking_id = fields.Many2one('stock.picking')
    v2_rate_id = fields.Char(string='V2 Rate ID',
                             help='ShipStation V2 rate ID. Used to create labels directly from a rate.')
    
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    
    @api.depends('shipping_cost', 'other_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.shipping_cost + record.other_cost

    def set_service(self):
        self.ensure_one()
        carrier = self.sale_order_id.carrier_id
        self.sale_order_id._remove_delivery_line()
        self.sale_order_id.shipstation_shipping_charge_id = self.id
        total_cost = self.shipping_cost + self.other_cost
        self.sale_order_id.set_delivery_line(carrier, total_cost)
        self.sale_order_id.carrier_id = carrier.id


    def set_picking_service(self):
        """Set this service as the selected service for the picking"""
        self.ensure_one()
        self.picking_id.shipstation_shipping_charge_id = self.id
        
        if self.shipstation_provider:
            shipstation_carrier = self.env['shipstation.delivery.carrier'].search([
                ('code', '=', self.shipstation_provider)
            ], limit=1)
            
            if shipstation_carrier:
                self.picking_id.shipstation_carrier_id = shipstation_carrier.id
                
                # Try to find a default package for this carrier
                default_package = self.env['shipstation.delivery.package'].search([
                    ('delivery_carrier_id', '=', shipstation_carrier.id)
                ], limit=1)

                if default_package:
                    # Preserve user-entered dimensions before switching package
                    saved_height = self.picking_id.height
                    saved_width = self.picking_id.width
                    saved_length = self.picking_id.length
                    self.picking_id.delivery_package_id = default_package.id
                    # Restore dimensions onto the new package
                    if saved_height or saved_width or saved_length:
                        self.picking_id.height = saved_height
                        self.picking_id.width = saved_width
                        self.picking_id.length = saved_length
