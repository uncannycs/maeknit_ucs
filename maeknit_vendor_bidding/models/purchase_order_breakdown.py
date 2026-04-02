from odoo import models, fields, api

class PurchaseOrderFactoryBreakdown(models.Model):
    _name = 'purchase.order.factory.breakdown'
    _description = 'Purchase Order Factory Shipping Breakdown'

    purchase_id = fields.Many2one(
        'purchase.order', 
        string='Purchase Order', 
        ondelete='cascade', 
        required=True
    )
    factory_id = fields.Many2one(
        'res.partner', 
        string='Factory', 
        domain="[('contact_type', '=', 'factory')]",
        required=True
    )
    currency_id = fields.Many2one(related='purchase_id.currency_id', string='Currency')
    
    shipping_cost = fields.Monetary(string='Estimated Shipping', currency_field='currency_id')
    duty_cost = fields.Monetary(string='Estimated Duty', currency_field='currency_id')
    total_route_cost = fields.Monetary(
        string='Total Route Cost', 
        compute='_compute_total_route_cost', 
        store=True,
        currency_field='currency_id'
    )

    @api.depends('shipping_cost', 'duty_cost')
    def _compute_total_route_cost(self):
        for record in self:
            record.total_route_cost = record.shipping_cost + record.duty_cost
