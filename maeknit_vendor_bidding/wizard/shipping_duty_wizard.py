from odoo import models, fields, api, _

class PurchaseShippingDutyWizard(models.TransientModel):
    _name = 'purchase.shipping.duty.wizard'
    _description = 'Shipping and Duty Breakdown Wizard'

    purchase_id = fields.Many2one('purchase.order', string='Garment RFQ', readonly=True)
    line_ids = fields.One2many('purchase.shipping.duty.wizard.line', 'wizard_id', string='Component Breakdown', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super(PurchaseShippingDutyWizard, self).default_get(fields_list)
        purchase_id = self._context.get('default_purchase_id') or self._context.get('active_id')
        if purchase_id:
            purchase = self.env['purchase.order'].browse(purchase_id)
            if purchase.bid_rfq_type == 'garment' and purchase.linked_so_id:
                wizard_lines = []
                # Find all material POs for this specific factory route
                comp_rfqs = self.env['purchase.order'].search([
                    ('linked_so_id', '=', purchase.linked_so_id.id),
                    ('bid_rfq_type', '=', 'component'),
                    ('bid_partner_id', '=', purchase.partner_id.id),
                    ('state', '!=', 'cancel')
                ])
                
                for crfq in comp_rfqs:
                    # Get the specific route costs for this factory
                    breakdown = crfq.factory_breakdown_ids.filtered(lambda b: b.factory_id == purchase.partner_id)[:1]
                    if breakdown:
                        # Iterate through each material line in the PO to show qty/price
                        for line in crfq.order_line:
                            wizard_lines.append((0, 0, {
                                'component_po_id': crfq.id,
                                'product_id': line.product_id.id,
                                'product_qty': line.product_qty,
                                'price_unit': line.price_unit,
                                'price_subtotal': crfq.product_subtotal,
                                'shipping_cost': breakdown.shipping_cost,
                                'duty_cost': breakdown.duty_cost,
                                'total_cost': crfq.total_landed_cost,

                            }))
                res.update({'line_ids': wizard_lines, 'purchase_id': purchase_id})
        return res


class PurchaseShippingDutyWizardLine(models.TransientModel):
    _name = 'purchase.shipping.duty.wizard.line'
    _description = 'Shipping and Duty Breakdown Wizard Line'

    wizard_id = fields.Many2one('purchase.shipping.duty.wizard', string='Wizard', ondelete='cascade', readonly=True)
    component_po_id = fields.Many2one('purchase.order', string='Component PO', readonly=True)
    currency_id = fields.Many2one(related='component_po_id.currency_id', string='Currency', readonly=True)
    
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_qty = fields.Float(string='Quantity', readonly=True)
    price_unit = fields.Monetary(string='Unit Price', currency_field='currency_id', readonly=True)
    
    shipping_cost = fields.Monetary(string='Shipping Cost', currency_field='currency_id', readonly=True)
    duty_cost = fields.Monetary(string='Duty Cost', currency_field='currency_id', readonly=True)
    price_subtotal = fields.Monetary(string='Price Subtotal', currency_field='currency_id', readonly=True)
    total_cost = fields.Monetary(string='Total Cost', currency_field='currency_id', readonly=True)

