from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    bids_requested = fields.Boolean(
        string='Bids Requested',
        default=False,
        copy=False,
        help="Indicates whether RFQs have been generated for this SO."
    )
    has_garment_product = fields.Boolean(
        compute='_compute_has_garment_product',
        string='Has Garment Product'
    )

    @api.depends('order_line.product_id.categ_id')
    def _compute_has_garment_product(self):
        for order in self:
            # Check if any product category name is exactly 'Garment'
            order.has_garment_product = any(
                line.product_id.categ_id.name == 'Garment' for line in order.order_line
            )
    winning_factory_id = fields.Many2one(
        'res.partner',
        string='Winning Factory',
        domain="[('contact_type', '=', 'factory')]",
        tracking=True,
        copy=False
    )
    garment_rfq_ids = fields.One2many(
        'purchase.order',
        'linked_so_id',
        string='Garment RFQs',
        domain=[('bid_rfq_type', '=', 'garment')]
    )
    component_rfq_ids = fields.One2many(
        'purchase.order',
        'linked_so_id',
        string='Component RFQs',
        domain=[('bid_rfq_type', '=', 'component')]
    )
    marketplace_bids_count = fields.Integer(
        compute='_compute_marketplace_bids_count',
        string='Marketplace Bids Count'
    )

    @api.depends('garment_rfq_ids', 'component_rfq_ids')
    def _compute_marketplace_bids_count(self):
        for order in self:
            # Count both Garment and Component RFQs for the smart button
            order.marketplace_bids_count = len(order.garment_rfq_ids)

    def action_request_bids(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('maeknit_vendor_bidding.action_request_bids_wizard')
        action['context'] = {'default_sale_order_id': self.id}
        return action

    def action_view_marketplace_bids(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('purchase.purchase_rfq')
        
        # Domain to show ALL bids (Garment and Component) related to this SO
        action['domain'] = [('linked_so_id', '=', self.id), ('bid_rfq_type', 'in', ['garment'])]
        action['context'] = {'default_linked_so_id': self.id}
        
        # Force the views list to ensure Kanban is first and uses our custom view
        kanban_view = self.env.ref('maeknit_vendor_bidding.view_purchase_order_kanban_bidding', raise_if_not_found=False)
        if kanban_view:
            action['views'] = [(kanban_view.id, 'kanban'), (False, 'list'), (False, 'form')]
            
        return action

    def _generate_rfqs_for_factories(self, factories):
        self.ensure_one()
        so = self
        
        # Determine the destination for the Garment RFQs based on SO
        dest_address_id = False
        picking_type_id = so.fg_shipping_destinations.id if so.fg_shipping_destinations else False

        # 1. Gather ALL components needed for the SO lines and group by Vendor AND Product
        vendor_components_map = {}

        for line in so.order_line:
            product = line.product_id
            if not product or product.type == 'service':
                continue

            all_possible_boms = self.env['mrp.bom'].sudo().with_context(active_test=False).search([
                '|', ('product_id', '=', product.id),
                ('product_tmpl_id', '=', product.product_tmpl_id.id)
            ])

            bom = all_possible_boms.filtered(lambda b: b.active and b.company_id.id in [so.company_id.id, False])[:1]

            if not bom:
                if not all_possible_boms:
                    raise UserError(_("No Bill of Materials (BoM) found for product '%s'.") % product.display_name)

                reasons = []
                for b in all_possible_boms:
                    reason = f"- BoM ID {b.id}"
                    if not b.active: reason += " (ARCHIVED)"
                    if b.company_id and b.company_id.id != so.company_id.id:
                        reason += f" (Different Company: {b.company_id.name})"
                    reasons.append(reason)
                raise UserError(
                    _("Found BoMs for '%s', but none can be used:\n%s") % (product.display_name, "\n".join(reasons)))

            for bom_line in bom.bom_line_ids:
                comp_product = bom_line.product_id
                if comp_product.seller_ids:
                    vendor = comp_product.seller_ids[0].partner_id
                    v_id = vendor.id
                    p_id = comp_product.id

                    if v_id not in vendor_components_map:
                        vendor_components_map[v_id] = {}

                    qty_needed = bom_line.product_qty * line.product_uom_qty

                    if p_id not in vendor_components_map[v_id]:
                        vendor_components_map[v_id][p_id] = {
                            'product_id': p_id,
                            'name': comp_product.name,
                            'product_qty': qty_needed,
                            'product_uom': comp_product.uom_po_id.id or comp_product.uom_id.id,
                            'price_unit': comp_product.seller_ids[0].price,
                        }
                    else:
                        vendor_components_map[v_id][p_id]['product_qty'] += qty_needed
                else:
                    raise UserError(
                        _("The component '%s' has no Vendor assigned in its Purchase tab.") % comp_product.display_name)

        # 2. Iterate through each Factory to create its own set of RFQs
        for factory in factories:
            # Create Garment RFQ for this factory
            garment_po_vals = {
                'partner_id': factory.id,
                'bid_rfq_type': 'garment',
                'linked_so_id': so.id,
                'company_id': so.company_id.id,
                'origin': so.name,
                'picking_type_id': picking_type_id,
                'dest_address_id': factory.id if so.fg_shipping_destination_label == 'client' else False,
                'order_line': [(0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.name,
                    'product_qty': line.product_uom_qty,
                    'product_uom': line.product_uom.id,
                    'price_unit': line.price_unit,
                }) for line in so.order_line if line.product_id]
            }
            if dest_address_id:
                garment_po_vals['dest_address_id'] = dest_address_id
            self.env['purchase.order'].create(garment_po_vals)

            # Create Separate Component RFQs for this factory-vendor combination
            for v_id, products_dict in vendor_components_map.items():
                comp_po_vals = {
                    'partner_id': v_id,
                    'bid_rfq_type': 'component',
                    'linked_so_id': so.id,
                    'company_id': so.company_id.id,
                    'bid_partner_id': factory.id,
                    'dest_address_id': factory.id,
                    'origin': f"{so.name} ({factory.name} Material Bidding)",
                    'order_line': [(0, 0, p_data) for p_data in products_dict.values()]
                }
                comp_po = self.env['purchase.order'].create(comp_po_vals)

                # Create the Routing Breakdown for this specific factory route
                breakdown = self.env['purchase.order.factory.breakdown'].create({
                    'purchase_id': comp_po.id,
                    'factory_id': factory.id,
                })

                # Calculate DHL and Duty for this PO
                try:
                    comp_po._onchange_dhl_trigger()
                    comp_po.action_get_dhl_quote()
                    comp_po.action_get_duty_rate()

                    # Store results in breakdown for showcase
                    breakdown.write({
                        'shipping_cost': comp_po.dhl_shipping_estimate,
                        'duty_cost': comp_po.duty_tax_estimate
                    })
                except Exception as e:
                    _logger.warning("Failed to calculate costs for PO %s (Factory: %s): %s", comp_po.name, factory.name, str(e))

        so.write({'bids_requested': True})
        return {'type': 'ir.actions.act_window_close'}
