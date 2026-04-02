from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _default_picking_type(self):
        return self._get_picking_type(self.env.context.get('company_id') or self.env.company.id)

    @api.model
    def _default_dropship_picking_type(self):
        return self._get_picking_dropship_type(self.env.context.get('company_id') or self.env.company.id)

    factory_id = fields.Many2one('res.partner', string="Factory", domain=['|', ('contact_type', '=', 'factory'), ('contact_type', '=', 'company')])
    is_component_procurement_done = fields.Boolean(string="Component Procurement Done", default=False, copy=False)
    is_parent_procurement_done = fields.Boolean(string="Parent Procurement Done", default=False, copy=False)
    shipping_destinations = fields.Many2one('stock.picking.type', 'Component Shipping Destination', required=True, default=_default_dropship_picking_type, domain="['|', ('warehouse_id', '=', False), ('warehouse_id.company_id', '=', company_id)]")
    fg_shipping_destinations = fields.Many2one('stock.picking.type', 'FG Shipping Destination', required=True, default=_default_picking_type, domain="['|', ('warehouse_id', '=', False), ('warehouse_id.company_id', '=', company_id)]")
    
    fg_shipping_destination_label = fields.Selection([
        ('ny', 'MAEKNIT New York'),
        ('london', 'MAEKNIT London'),
        ('client', 'Client')
    ], string="FG Shipping Destination", compute="_compute_fg_shipping_destination_label", inverse="_inverse_fg_shipping_destination_label", store=True)

    @api.model
    def _get_picking_type(self, company_id):
        picking_type = self.env['stock.picking.type'].search(
            [('code', '=', 'incoming'), ('warehouse_id.company_id', '=', company_id)])
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search(
                [('code', '=', 'incoming'), ('warehouse_id', '=', False)])
        if not picking_type:
            picking_type = self.env['stock.picking.type'].with_context(active_test=False).search(
                [('code', '=', 'incoming'), ('warehouse_id', '=', False)])
        return picking_type[:1]

    @api.model
    def _get_picking_dropship_type(self, company_id):
        # 1. Prefer Dropship picking type
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'dropship'),
            ('company_id', '=', company_id)
        ], limit=1)
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search([
                ('name', 'ilike', 'dropship'),
                ('company_id', '=', company_id)
            ], limit=1)

        # 2. Fallback to Incoming picking type
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search(
                [('code', '=', 'incoming'), ('warehouse_id.company_id', '=', company_id)])
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search(
                [('code', '=', 'incoming'), ('warehouse_id', '=', False)])
        if not picking_type:
            picking_type = self.env['stock.picking.type'].with_context(active_test=False).search(
                [('code', '=', 'incoming'), ('warehouse_id', '=', False)])
        return picking_type[:1]

    @api.depends('fg_shipping_destinations')
    def _compute_fg_shipping_destination_label(self):
        for order in self:
            if not order.fg_shipping_destinations:
                order.fg_shipping_destination_label = False
                continue

            name = (order.fg_shipping_destinations.display_name or '').lower()
            if 'ny' in name or 'new york' in name:
                order.fg_shipping_destination_label = 'ny'
            elif 'uk' in name or 'london' in name:
                order.fg_shipping_destination_label = 'london'
            elif 'dropship' in name or order.fg_shipping_destinations.code == 'dropship':
                order.fg_shipping_destination_label = 'client'
            else:
                order.fg_shipping_destination_label = False

    def _inverse_fg_shipping_destination_label(self):
        for order in self:
            if not order.fg_shipping_destination_label:
                continue

            if order.fg_shipping_destination_label == 'ny':
                # Search for NY Receipts
                ptype = self.env['stock.picking.type'].search([
                    ('code', '=', 'incoming'),
                    '|', ('name', 'ilike', 'NY'), ('warehouse_id.name', 'ilike', 'NY')
                ], limit=1)
                if ptype:
                    order.fg_shipping_destinations = ptype
            elif order.fg_shipping_destination_label == 'london':
                # Search for UK/London Receipts
                ptype = self.env['stock.picking.type'].search([
                    ('code', '=', 'incoming'),
                    '|', ('name', 'ilike', 'UK'), ('warehouse_id.name', 'ilike', 'UK'),
                    '|', ('name', 'ilike', 'London'), ('warehouse_id.name', 'ilike', 'London')
                ], limit=1)
                if ptype:
                    order.fg_shipping_destinations = ptype
            elif order.fg_shipping_destination_label == 'client':
                ptype = self._get_picking_dropship_type(order.company_id.id)
                if ptype:
                    order.fg_shipping_destinations = ptype


    def action_view_replenishment_plan(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'maeknit_sale_replenishment.replenishment_overview_client_action',
            'context': {
                'active_id': self.id,
            },
        }

    def action_generate_procurement(self):
        return {
            'name': 'Procurement',
            'type': 'ir.actions.act_window',
            'res_model': 'maeknit.replenishment',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'maeknit_sale_replenishment.view_maeknit_replenishment_form_view'
            ).id,
            'target': 'new',
            'context': {}
        }

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order._create_subcontracting_boms()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'order_line' in vals or 'factory_id' in vals:
            for order in self:
                order._create_subcontracting_boms()
        return res

    def _create_subcontracting_boms(self):
        """
        Automatically create a subcontracting BOM based on the existing manufacturing BOM
        for each product in the sale order line, assigned to the selected factory.
        """
        for order in self:
            if not order.factory_id:
                continue
            
            for line in order.order_line:
                if line.display_type or not line.product_id or line.product_id.type == 'service':
                    continue
                
                product = line.product_id
                
                # 1. Check if a subcontracting BOM ALREADY exists for this product
                existing_sub_bom = self.env['mrp.bom'].sudo().search([
                    ('type', '=', 'subcontract'),
                    '|', ('product_id', '=', product.id),
                    '&', ('product_id', '=', False), ('product_tmpl_id', '=', product.product_tmpl_id.id),
                ], limit=1)

                if existing_sub_bom:
                    # Ensure current factory is in subcontractors list
                    if order.factory_id.id not in existing_sub_bom.subcontractor_ids.ids:
                        existing_sub_bom.sudo().write({
                            'subcontractor_ids': [(4, order.factory_id.id)]
                        })
                        # logging.info(" Custom Code: Added factory %s to existing subcontracting BOM %s for product %s",
                        #              order.factory_id.name, existing_sub_bom.name, product.display_name)
                # logging.info(" Custom Code: Created new subcontracting BOM %s for product %s and factory %s",
                #              new_sub_bom.name, product.display_name, order.factory_id.name)