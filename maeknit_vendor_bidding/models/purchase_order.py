from odoo import models, fields, api, _

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    bid_rfq_type = fields.Selection([
        ('standard', 'Standard'),
        ('garment', 'Garment RFQ'),
        ('component', 'Component RFQ')
    ], string='RFQ Type', default='standard', copy=False)
    
    linked_so_id = fields.Many2one('sale.order', string='Linked Sales Order', copy=False)
    is_winning_bid = fields.Boolean(compute='_compute_is_winning_bid', store=True)
    component_rfq_count = fields.Integer(compute='_compute_component_rfq_count')

    def _compute_component_rfq_count(self):
        for po in self:
            count = 0
            if po.bid_rfq_type == 'garment' and po.linked_so_id:
                count = self.env['purchase.order'].search_count([
                    ('linked_so_id', '=', po.linked_so_id.id),
                    ('bid_rfq_type', '=', 'component'),
                    ('bid_partner_id', '=', po.partner_id.id)
                ])
            po.component_rfq_count = count

    def action_view_component_rfqs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('purchase.purchase_rfq')
        action['domain'] = [
            ('linked_so_id', '=', self.linked_so_id.id),
            ('bid_rfq_type', '=', 'component'),
            ('bid_partner_id', '=', self.partner_id.id)
        ]
        action['context'] = {
            'default_linked_so_id': self.linked_so_id.id, 
            'default_bid_rfq_type': 'component',
            'default_bid_partner_id': self.partner_id.id
        }
        tree_view = self.env.ref('maeknit_vendor_bidding.view_purchase_order_tree_bidding', raise_if_not_found=False)
        if tree_view:
            action['views'] = [(tree_view.id, 'list'), (False, 'form')]
        else:
            action['views'] = [(False, 'list'), (False, 'form')]
        return action

    # Cost Breakdown Fields for Garment RFQ
    total_garment_cost = fields.Monetary(string='Total Garment Cost', compute='_compute_garment_costs', store=True)
    total_material_cost = fields.Monetary(string='Total Material Cost', compute='_compute_component_costs')
    garment_shipping = fields.Monetary(string='Garment Shipping', compute='_compute_native_estimates')
    garment_customs_duties = fields.Monetary(string='Garment Customs/Duties', compute='_compute_native_estimates')
    component_shipping = fields.Monetary(string='Component Shipping', compute='_compute_component_costs')
    component_customs_duties = fields.Monetary(string='Component Customs/Duties', compute='_compute_component_costs')
    landed_cost = fields.Monetary(string='Landed Cost (Total)', compute='_compute_landed_cost', store=True)
    factory_id = fields.Many2one('res.partner', string="Factory")
    bid_partner_id = fields.Many2one('res.partner', string="Bid Partner")

    @api.depends('dhl_shipping_estimate', 'duty_tax_estimate')
    def _compute_native_estimates(self):
        for po in self:
            po.garment_shipping = po.dhl_shipping_estimate
            po.garment_customs_duties = po.duty_tax_estimate

    @api.depends('linked_so_id.component_rfq_ids', 'linked_so_id.component_rfq_ids.factory_breakdown_ids.shipping_cost',
                 'linked_so_id.component_rfq_ids.factory_breakdown_ids.duty_cost',
                 'bid_rfq_type', 'partner_id')
    def _compute_component_costs(self):
        for po in self:
            po.total_material_cost = 0.0
            po.component_shipping = 0.0
            po.component_customs_duties = 0.0
            
            if po.bid_rfq_type == 'garment' and po.linked_so_id:
                factory = po.partner_id
                # Filter by the current factory (bid_partner_id) to avoid doubling costs from other routes
                comp_rfqs = self.env['purchase.order'].search([
                    ('linked_so_id', '=', po.linked_so_id.id),
                    ('bid_rfq_type', '=', 'component'),
                    ('bid_partner_id', '=', factory.id),
                    ('state', '!=', 'cancel')
                ])
                
                total_mat = 0.0
                total_ship = 0.0
                total_duty = 0.0
                
                for crfq in comp_rfqs:
                    # Convert to current PO currency to ensure accurate summation
                    total_mat += crfq.currency_id._convert(
                        crfq.amount_untaxed, po.currency_id, po.company_id, po.date_order or fields.Date.today()
                    )

                    # Also sum specific route costs for this factory with currency conversion
                    breakdown = crfq.factory_breakdown_ids.filtered(lambda b: b.factory_id == factory)[:1]
                    if breakdown:
                        total_ship += crfq.currency_id._convert(
                            breakdown.shipping_cost, po.currency_id, po.company_id, po.date_order or fields.Date.today()
                        )
                        total_duty += crfq.currency_id._convert(
                            breakdown.duty_cost, po.currency_id, po.company_id, po.date_order or fields.Date.today()
                        )
                
                po.total_material_cost = total_mat
                po.component_shipping = total_ship
                po.component_customs_duties = total_duty

    # Global Component RFQ breakdown
    factory_breakdown_ids = fields.One2many(
        'purchase.order.factory.breakdown',
        'purchase_id',
        string='Factory Shipping Breakdown',
        copy=False
    )

    @api.depends('linked_so_id.winning_factory_id', 'partner_id', 'bid_rfq_type')
    def _compute_is_winning_bid(self):
        for po in self:
            po.is_winning_bid = False
            if not po.linked_so_id or not po.linked_so_id.winning_factory_id:
                continue
            
            winner = po.linked_so_id.winning_factory_id
            if po.bid_rfq_type == 'garment' and po.partner_id == winner:
                po.is_winning_bid = True
            elif po.bid_rfq_type == 'component' and po.dest_address_id == winner:
                po.is_winning_bid = True

    @api.depends('order_line.price_subtotal')
    def _compute_garment_costs(self):
        for po in self:
            po.total_garment_cost = sum(po.order_line.mapped('price_subtotal'))

    @api.depends('total_garment_cost', 'total_material_cost', 'garment_shipping', 'garment_customs_duties', 
                 'component_shipping', 'component_customs_duties', 'order_line.product_qty')
    def _compute_landed_cost(self):
        for po in self:
            # Total Landed Cost
            po.landed_cost = (
                po.total_garment_cost +
                po.total_material_cost +
                po.garment_shipping +
                po.garment_customs_duties +
                po.component_shipping +
                po.component_customs_duties
            )

    def action_confirm_winning_factory(self):
        for po in self:
            if po.bid_rfq_type != 'garment' or not po.linked_so_id:
                continue
            
            so = po.linked_so_id
            winning_factory = po.partner_id
            so.write({'winning_factory_id': winning_factory.id, 'factory_id': winning_factory.id})
            
            # 1. Cancel other Garment bids
            losing_garment_rfqs = so.garment_rfq_ids - po
            losing_garment_rfqs.button_cancel()

            # 2. Update Global Component RFQs
            for comp_rfq in so.component_rfq_ids:
                if comp_rfq.state in ['draft', 'sent']:
                    picking_type_id = self.env['stock.picking.type'].search([
                                 ('code', '=', 'dropship'),
                                 ('company_id', '=', so.company_id.id)
                             ], limit=1)

                    # Update dropship destination to the winner
                    comp_po_vals = {'picking_type_id': picking_type_id.id if picking_type_id else False, 'dest_address_id': winning_factory.id}
                    
                    # Also grab the estimated shipping/duty from the breakdown for the winner
                    breakdown = comp_rfq.factory_breakdown_ids.filtered(lambda b: b.factory_id == winning_factory)[:1]
                    if breakdown:
                        comp_po_vals.update({
                            'dhl_shipping_estimate': breakdown.shipping_cost,
                            'duty_tax_estimate': breakdown.duty_cost
                        })
                    
                    comp_rfq.write(comp_po_vals)
                    # Automatically Confirm the Component PO
                    comp_rfq.button_confirm()
            
            # 3. Confirm the winning Garment RFQ
            po.button_confirm()

    def action_open_shipping_duty_wizard(self):
        self.ensure_one()
        if self.bid_rfq_type != 'garment' or not self.linked_so_id:
            return
            
        return {
            'name': _('Shipping and Duty Breakdown'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.shipping.duty.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_purchase_id': self.id,
            }
        }

    def write(self, vals):
        """ Robust sync using bid_partner_id as the anchor for specific route updates """
        res = super(PurchaseOrder, self).write(vals)
        
        # Monitor for changes in shipping/duty estimates
        if 'dhl_shipping_estimate' in vals or 'duty_tax_estimate' in vals:
            for po in self:
                if po.bid_rfq_type == 'component':
                    # Determine which breakdown route to update
                    # Use bid_partner_id (Factory) as the primary key for accuracy
                    breakdown = False
                    if po.bid_partner_id:
                        breakdown = po.factory_breakdown_ids.filtered(lambda b: b.factory_id == po.bid_partner_id)[:1]
                    
                    # Fallback to destination matching if bid_partner_id is empty
                    if not breakdown and po.dest_address_id:
                        dest_comm_id = po.dest_address_id.commercial_partner_id.id
                        breakdown = po.factory_breakdown_ids.filtered(
                            lambda b: b.factory_id.commercial_partner_id.id == dest_comm_id
                        )[:1]
                    
                    if breakdown:
                        update_vals = {}
                        if 'dhl_shipping_estimate' in vals:
                            update_vals['shipping_cost'] = vals.get('dhl_shipping_estimate')
                        if 'duty_tax_estimate' in vals:
                            update_vals['duty_cost'] = vals.get('duty_tax_estimate')
                        
                        if update_vals:
                            breakdown.write(update_vals)
                    
                    # Forcefully signal Garment RFQs to recompute and display updated costs
                    if po.linked_so_id:
                        garment_rfqs = po.linked_so_id.garment_rfq_ids
                        garment_rfqs.modified(['component_shipping', 'component_customs_duties'])
                        garment_rfqs._compute_component_costs()
                        garment_rfqs._compute_landed_cost()
        return res
