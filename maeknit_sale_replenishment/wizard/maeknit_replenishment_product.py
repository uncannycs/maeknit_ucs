from odoo import models, fields, api, _

class MaeknitReplenishmentProduct(models.TransientModel):
    _name = 'maeknit.replenishment'
    _description = 'Maeknit Replenishment Product'

    replenishment_line_ids = fields.One2many('maeknit.replenishment.line', 'replenishment_product_id', string='Replenishment Lines')
    replenishment_component_line_ids = fields.One2many('maeknit.replenishment.component.line', 'replenishment_component_id', string='Replenishment Components Lines')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    is_component_procurement_done = fields.Boolean(default=False)
    is_parent_procurement_done = fields.Boolean(default=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        lines = []
        component_map = {}
        sale_id = self.env['sale.order'].browse(active_ids)
        sale_line_ids = sale_id.mapped('order_line')
        
        mto_route = self.env['stock.route'].search([('name', '=', 'Replenish on Order (MTO)')], limit=1)
        manufacture_route = self.env['stock.route'].search([('name', '=', 'Manufacture')], limit=1)
        manufacture_ny_route = self.env['stock.route'].search([('name', '=', 'Manufacture NY')], limit=1)
        manufacture_uk_route = self.env['stock.route'].search([('name', '=', 'Manufacture UK')], limit=1)
        buy_route = self.env['stock.route'].search([('name', '=', 'Buy')], limit=1)
        dropship_route = self.env['stock.route'].search([('name', '=', 'Dropship Subcontractor on Order')], limit=1)
        
        factory_name = sale_id.factory_id.name or ''
        is_ny = 'New York' in factory_name
        is_uk = 'UK' in factory_name
        is_region = is_ny or is_uk

        for line in sale_line_ids:
            boms_dict = self.env['mrp.bom']._bom_find(line.product_id, company_id=line.company_id.id, bom_type='phantom')
            bom = boms_dict[line.product_id]
            if not bom:
                boms_dict = self.env['mrp.bom']._bom_find(line.product_id, company_id=line.company_id.id)
                bom = boms_dict[line.product_id]
            
            if bom:
                # Parent route selection
                bom_route = manufacture_route if manufacture_route else mto_route
                if is_ny and manufacture_ny_route:
                    bom_route = manufacture_ny_route
                elif is_uk and manufacture_uk_route:
                    bom_route = manufacture_uk_route
                
                # Broaden detection: check BOM type AND product route
                is_subcontracting = bom.type == 'subcontract' or (line.route_id and 'subcontract' in line.route_id.name.lower())
                
                # Fallback for subcontractor: BOM -> Sale Order Factory
                subcontractor = False
                if is_subcontracting:
                    if sale_id.factory_id:
                        subcontractor = sale_id.factory_id
                    elif bom.subcontractor_ids:
                        subcontractor = bom.subcontractor_ids[0]

                lines.append((0, 0, {
                    'sale_line_id': line.id,
                    'product_id': line.product_id.id,
                    'qty': line.product_uom_qty,
                    'replenishment_product_id': self.id,
                    'price_unit': line.price_unit,
                    'cost': line.price_unit * line.product_uom_qty,
                    # 'route_id': bom_route.id if bom_route else (line.route_id.id if line.route_id else (line.product_id.route_ids[0].id if line.product_id.route_ids else False)),
                    'route_id': (buy_route.id if buy_route else False) if is_subcontracting else (bom_route.id if is_region else (buy_route.id if buy_route else False)),
                    'is_bom': True,
                    'is_component': False,
                    'is_create_procurement': False,
                    'vendor_id': sale_id.factory_id.id if sale_id.factory_id else False,
                    'is_subcontracting': is_subcontracting,
                    'subcontractor_id': subcontractor.id if is_subcontracting and subcontractor else False,
                }))
                

                # Add Components (Children)
                boms, components = bom.explode(line.product_id, line.product_uom_qty)
                for component, component_data in components:
                     qty = component_data['qty']
                     # lines.append((0, 0, {
                     #    'sale_line_id': line.id,
                     #    'product_id': component.product_id.id,
                     #    'qty': qty,
                     #    'replenishment_product_id': self.id,
                     #    'price_unit': component.product_id.standard_price,
                     #    'cost': component.product_id.standard_price * qty,
                     #    'route_id': buy_route.id if is_ny_uk else (dropship_route.id if dropship_route else False),
                     #    'is_bom': False,
                     #    'is_component': True,
                     #    'is_create_procurement': True,
                     # }))
                     #
                     # Aggregate for Component Page
                     product_id = component.product_id.id
                     if product_id in component_map:
                         component_map[product_id]['qty'] += qty
                         component_map[product_id]['cost'] += component.product_id.standard_price * qty
                         if is_subcontracting:
                             component_map[product_id]['is_subcontracting'] = True
                             component_map[product_id]['subcontractor_id'] = subcontractor.id if subcontractor else False
                     else:
                         component_map[product_id] = {
                             'sale_line_id': line.id,
                             'product_id': product_id,
                             'qty': qty,
                             'replenishment_component_id': self.id,
                             'price_unit': component.product_id.standard_price,
                             'cost': component.product_id.standard_price * qty,
                             'route_id': buy_route.id if is_ny or is_uk else (dropship_route.id if dropship_route else False),
                             'is_bom': False,
                             'is_component': True,
                             'is_create_procurement': True,
                             'is_subcontracting': is_subcontracting,
                             'subcontractor_id': subcontractor.id if is_subcontracting and subcontractor else (component.product_id.seller_ids[0].partner_id.id if component.product_id.seller_ids else False),
                             'vendor_id': component.product_id.seller_ids[0].partner_id.id if component.product_id.seller_ids else False,
                         }

            else:
                 lines.append((0, 0, {
                    'sale_line_id': line.id,
                    'product_id': line.product_id.id,
                    'qty': line.product_uom_qty,
                    'replenishment_product_id':self.id,
                    'price_unit':line.price_unit,
                    'cost':line.price_unit * line.product_uom_qty,
                    'route_id': line.route_id.id if line.route_id else (line.product_id.route_ids[0].id if line.product_id.route_ids else False),
                    'is_bom': False,
                    'is_component': False,
                    'is_create_procurement': True,
                }))

        res['sale_order_id'] = sale_id.id
        res['replenishment_line_ids'] = lines
        res['replenishment_component_line_ids'] = [
            (0, 0, vals) for pid, vals in component_map.items()
        ]

        return res

    def action_select_all_component_procurement(self):
        self.ensure_one()
        # 1. Select all lines
        for line in self.replenishment_component_line_ids:
            line.is_create_procurement = True
        
        # 2. RUN PROCUREMENT LOGIC (Self-contained)
        procurements = []
        all_lines = self.replenishment_component_line_ids.filtered(
            lambda l: l.is_create_procurement and (l.qty > 0 or l.add_qty > 0)
        )
        
        # Update Parent BOMs for manual additions
        self._update_parent_boms(all_lines)
        
        procurement_list = []
        non_dropship_map = {}

        for line in all_lines:
            # Shortage check (bypass for dropship or subcontracting)
            is_dropship = line.route_id and 'dropship' in line.route_id.name.lower()
            is_subcontracting = getattr(line, 'is_subcontracting', False)
            
            if line.final_qty >= 0 and not (is_dropship or is_subcontracting):
                continue

            procurement_product = line.product_id
            product_qty = abs(line.final_qty)
            procurement_uom = line.product_id.uom_id
            
            sale_order = line.sale_line_id.order_id or self.sale_order_id
            group_id = sale_order.procurement_group_id
            if not group_id:
                group_id = self.env['procurement.group'].create({
                    'name': sale_order.name,
                    'move_type': sale_order.picking_policy,
                    'sale_id': sale_order.id,
                    'partner_id': sale_order.partner_shipping_id.id,
                })
                sale_order.procurement_group_id = group_id

            if line.sale_line_id:
                values = line.sale_line_id._prepare_procurement_values(group_id=group_id)
            else:
                values = {
                    'group_id': group_id,
                    'date_planned': sale_order.commitment_date or sale_order.date_order,
                    'warehouse_id': sale_order.warehouse_id,
                    'partner_id': sale_order.partner_shipping_id.id,
                    'company_id': sale_order.company_id,
                }
            if line.route_id:
                values['route_ids'] = line.route_id

            # Ensure selected vendor is used for RFQ
            if line.vendor_id:
                seller = line.product_id._select_seller(
                    partner_id=line.vendor_id,
                    quantity=product_qty,
                    date=values.get('date_planned', fields.Date.today()),
                    uom_id=procurement_uom
                )
                if not seller:
                    seller = self.env['product.supplierinfo'].sudo().create({
                        'partner_id': line.vendor_id.id,
                        'product_id': line.product_id.id,
                        'product_tmpl_id': line.product_id.product_tmpl_id.id,
                        'min_qty': 0,
                        'price': 0,
                        'currency_id': self.env.company.currency_id.id,
                        'delay': 1,
                    })
                values['supplierinfo_name'] = line.vendor_id
                values['supplierinfo_id'] = seller

            if is_dropship:
                procurement_list.append({
                    'product': procurement_product,
                    'qty': product_qty,
                    'uom': procurement_uom,
                    'values': values,
                    'route_id': line.route_id,
                    'sale_order': sale_order,
                })
            else:
                key = (procurement_product.id, line.route_id.id if line.route_id else False, line.sale_line_id.id if line.sale_line_id else False, line.vendor_id.id if line.vendor_id else False)
                if key not in non_dropship_map:
                    non_dropship_map[key] = {
                        'product': procurement_product,
                        'qty': product_qty,
                        'uom': procurement_uom,
                        'values': values,
                        'route_id': line.route_id,
                        'sale_order': sale_order,
                    }
                else:
                    non_dropship_map[key]['qty'] += product_qty

        for p_data in non_dropship_map.values():
            procurement_list.append(p_data)

        for p_data in procurement_list:
            procurement_product = p_data['product']
            product_qty = p_data['qty']
            procurement_uom = p_data['uom']
            values = p_data['values']
            route_id = p_data['route_id']
            sale_order = p_data['sale_order']

            warehouse = sale_order.warehouse_id
            domain = [
                ('product_id', '=', procurement_product.id),
                ('warehouse_id', '=', warehouse.id),
            ]
            orderpoint = self.env['stock.warehouse.orderpoint'].search(domain, limit=1)
            
            if not orderpoint:
                orderpoint = self.env['stock.warehouse.orderpoint'].create({
                    'product_id': procurement_product.id,
                    'warehouse_id': warehouse.id,
                    'location_id': warehouse.lot_stock_id.id,
                    'product_min_qty': abs(product_qty),
                    'product_max_qty': abs(product_qty),
                    'qty_multiple': 1.0,
                    'route_id': route_id.id if route_id else False,
                    'trigger': 'auto',
                })
            else:
                orderpoint.write({
                    'product_min_qty': abs(product_qty),
                    'product_max_qty': abs(product_qty),
                    'route_id': route_id.id if route_id else orderpoint.route_id.id,
                    'trigger': 'auto',
                })

            try:
                procurements.append(self.env['procurement.group'].Procurement(
                    procurement_product, product_qty, procurement_uom,
                    warehouse.lot_stock_id,
                    procurement_product.name, sale_order.name, sale_order.company_id, values
                ))
            except TypeError:
                 procurements.append((
                    procurement_product, product_qty, procurement_uom,
                    warehouse.lot_stock_id,
                    procurement_product.name, sale_order.name, sale_order.company_id, values
                ))
            orderpoint.write({'trigger': 'manual'})

        if procurements:
            self.env['procurement.group'].run(procurements)

        # 3. RFQ UPDATES FOR DROPSHIP ROUTES
        sale_order = self.sale_order_id
        if sale_order:
            pos = self.env['purchase.order'].search([
                ('origin', '=', sale_order.name),
                ('state', '=', 'draft'),
                ('company_id', '=', sale_order.company_id.id)
            ])
            
            # picking_type_sub = self.env['stock.picking.type'].search([
            #     ('name', 'ilike', 'Dropship Subcontractor'),
            #     ('company_id', '=', sale_order.company_id.id)
            # ], limit=1)
            # if not picking_type_sub:
            #     picking_type_sub = self.env['stock.picking.type'].search([
            #         ('code', '=', 'dropship'),
            #         ('company_id', '=', sale_order.company_id.id)
            #     ], limit=1)
            
            for po in pos:
                po_product_ids = po.order_line.mapped('product_id.id')
                # Targeted Vendor Override: Use the vendor selected in the wizard for this RFQ
                comp_lines = [l for l in all_lines if l.product_id.id in po_product_ids]
                if comp_lines:
                    # Priority: Subcontracting Factory > Selected Vendor
                    sub_comp_lines = [l for l in comp_lines if getattr(l, 'is_subcontracting', False)]
                    if sub_comp_lines and sale_order.factory_id:
                        po.write({'partner_id': sale_order.factory_id.id})
                        # logging.info(" Custom Code: Overrode RFQ %s partner with SO Factory %s for subcontracting lines", po.name, sale_order.factory_id.name)
                    else:
                        selected_vendor = next((l.vendor_id for l in comp_lines if l.vendor_id), False)
                        if selected_vendor:
                            po.write({'partner_id': selected_vendor.id})
                            # logging.info(" Custom Code: Overrode RFQ %s partner with selected Vendor %s", po.name, selected_vendor.name)

                # Only process POs containing products from our lines that used a Dropship route
                target_lines = [
                    l for l in all_lines 
                    if l.product_id.id in po_product_ids and 'dropship' in (l.route_id.name or '').lower()
                ]
                if target_lines:
                    subcontractor = next((l.subcontractor_id for l in target_lines if l.subcontractor_id), False)
                    if not subcontractor and sale_order.factory_id:
                        subcontractor = sale_order.factory_id
                    
                    po.write({
                        'picking_type_id': sale_order.fg_shipping_destinations.id,
                        'dest_address_id': subcontractor.id if subcontractor else po.partner_id.id,
                    })
        
        self.is_component_procurement_done = True
        if self.sale_order_id:
            self.sale_order_id.is_component_procurement_done = True
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'maeknit.replenishment',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def _update_parent_boms(self, all_lines):
        """
        Check if any component lines are manually added (not in the original BOM)
        and add them to the parent product's BOM using the linked Sale Line.
        """
        for line in all_lines:
            if not line.sale_line_id:
                continue
            
            parent_product = line.sale_line_id.product_id
            # Find the BOM for the parent product
            existing_sub_bom = self.env['mrp.bom'].sudo().search([
                ('type', '=', 'subcontract'),
                '|', ('product_id', '=', parent_product.id),
                '&', ('product_id', '=', False), ('product_tmpl_id', '=', parent_product.product_tmpl_id.id),
            ], limit=1)

            if not existing_sub_bom:
                continue
            # Check if product is already in BOM
            existing_bom_line = existing_sub_bom.bom_line_ids.filtered(
                lambda l: l.product_id.id == line.product_id.id
            )

            if not existing_bom_line:
                product_qty = line.qty if line.qty > 0 else line.add_qty

                if line.sale_line_id.product_uom_qty:
                    product_qty = product_qty / line.sale_line_id.product_uom_qty

                self.env['mrp.bom.line'].sudo().create({
                    'bom_id': existing_sub_bom.id,
                    'product_id': line.product_id.id,
                    'product_qty': product_qty,
                    'product_uom_id': line.product_id.uom_id.id,
                })
    # def action_select_all_parent_procurement(self):
    #     self.ensure_one()
    #     # 1. Select all parent BOM products
    #     for line in self.replenishment_line_ids:
    #         if line.is_bom:
    #             line.is_create_procurement = True
    #
    #     # 2. RUN PROCUREMENT LOGIC (Self-contained)
    #     procurements = []
    #     all_lines = self.replenishment_line_ids.filtered(
    #         lambda l: l.is_bom and l.is_create_procurement and (l.qty > 0 or l.add_qty > 0)
    #     )
    #
    #     procurement_list = []
    #     non_dropship_map = {}
    #
    #     # Identify target warehouse based on Factory
    #     sale_order = self.sale_order_id
    #     target_warehouse = sale_order.warehouse_id
    #     if sale_order.factory_id:
    #         factory_name = sale_order.factory_id.name.upper()
    #         if 'NEW YORK' in factory_name or ' NY ' in factory_name or factory_name.endswith(' NY'):
    #             target_warehouse = self.env['stock.warehouse'].search([
    #                 '|', ('name', 'ilike', 'NY'), ('code', 'ilike', 'NY'),
    #                 ('company_id', '=', sale_order.company_id.id)
    #             ], limit=1) or target_warehouse
    #         elif 'UK' in factory_name or 'UK Limited' in factory_name or 'UNITED KINGDOM' in factory_name:
    #             target_warehouse = self.env['stock.warehouse'].search([
    #                 '|', ('name', 'ilike', 'UK'), ('code', 'ilike', 'UK'),
    #                 ('company_id', '=', sale_order.company_id.id)
    #             ], limit=1) or target_warehouse
    #
    #     for line in all_lines:
    #         # Shortage check
    #         if line.final_qty >= 0:
    #             continue
    #
    #         # Skip custom manufacture logic lines from standard procurement to avoid aggregated MOs
    #         route_name = (line.route_id.name or '').lower()
    #         if line.route_id and ('manufacture' in route_name or 'mto' in route_name):
    #              continue
    #
    #         # Parents are usually BUY or Manufacture. Standard logic handles MO creation via 'normal' routes.
    #         procurement_product = line.product_id
    #         product_qty = abs(line.final_qty)
    #         procurement_uom = line.product_id.uom_id
    #
    #         sale_order = line.sale_line_id.order_id or self.sale_order_id
    #         group_id = sale_order.procurement_group_id
    #         if not group_id:
    #             group_id = self.env['procurement.group'].create({
    #                 'name': sale_order.name,
    #                 'move_type': sale_order.picking_policy,
    #                 'sale_id': sale_order.id,
    #                 'partner_id': sale_order.partner_shipping_id.id,
    #             })
    #             sale_order.procurement_group_id = group_id
    #
    #         if line.sale_line_id:
    #             values = line.sale_line_id._prepare_procurement_values(group_id=group_id)
    #         else:
    #             values = {
    #                 'group_id': group_id,
    #                 'date_planned': sale_order.commitment_date or sale_order.date_order,
    #                 'warehouse_id': sale_order.warehouse_id,
    #                 'partner_id': sale_order.partner_shipping_id.id,
    #                 'company_id': sale_order.company_id,
    #             }
    #         if line.route_id:
    #             values['route_ids'] = line.route_id
    #
    #         key = (procurement_product.id, line.route_id.id if line.route_id else False, line.sale_line_id.id if line.sale_line_id else False)
    #         if key not in non_dropship_map:
    #             non_dropship_map[key] = {
    #                 'product': procurement_product,
    #                 'qty': product_qty,
    #                 'uom': procurement_uom,
    #                 'values': values,
    #                 'route_id': line.route_id,
    #                 'sale_order': sale_order,
    #             }
    #         else:
    #             non_dropship_map[key]['qty'] += product_qty
    #
    #     for p_data in non_dropship_map.values():
    #         procurement_list.append(p_data)
    #
    #     for p_data in procurement_list:
    #         procurement_product = p_data['product']
    #         product_qty = p_data['qty']
    #         procurement_uom = p_data['uom']
    #         values = p_data['values']
    #         route_id = p_data['route_id']
    #         sale_order = p_data['sale_order']
    #
    #         domain = [
    #             ('product_id', '=', procurement_product.id),
    #             ('warehouse_id', '=', target_warehouse.id),
    #         ]
    #         orderpoint = self.env['stock.warehouse.orderpoint'].search(domain, limit=1)
    #
    #         if not orderpoint:
    #             orderpoint = self.env['stock.warehouse.orderpoint'].create({
    #                 'product_id': procurement_product.id,
    #                 'warehouse_id': target_warehouse.id,
    #                 'location_id': target_warehouse.lot_stock_id.id,
    #                 'product_min_qty': abs(product_qty),
    #                 'product_max_qty': abs(product_qty),
    #                 'qty_multiple': 1.0,
    #                 'route_id': route_id.id if route_id else False,
    #                 'trigger': 'auto',
    #             })
    #         else:
    #             orderpoint.write({
    #                 'product_min_qty': abs(product_qty),
    #                 'product_max_qty': abs(product_qty),
    #                 'route_id': route_id.id if route_id else orderpoint.route_id.id,
    #                 'trigger': 'auto',
    #             })
    #
    #         try:
    #             procurements.append(self.env['procurement.group'].Procurement(
    #                 procurement_product, product_qty, procurement_uom,
    #                 target_warehouse.lot_stock_id,
    #                 procurement_product.name, sale_order.name, sale_order.company_id, values
    #             ))
    #         except TypeError:
    #              procurements.append((
    #                 procurement_product, product_qty, procurement_uom,
    #                 target_warehouse.lot_stock_id,
    #                 procurement_product.name, sale_order.name, sale_order.company_id, values
    #             ))
    #         orderpoint.write({'trigger': 'manual'})
    #
    #     if procurements:
    #         self.env['procurement.group'].run(procurements)
    #
    #     # Identify the sale lines with manufacture/mto route that were selected
    #     custom_mrp_lines = all_lines.filtered(
    #         lambda l: l.route_id and ('manufacture' in (l.route_id.name or '').lower() or 'mto' in (l.route_id.name or '').lower())
    #     )
    #     sale_line_ids = custom_mrp_lines.mapped('sale_line_id')
    #     qty_map = {l.sale_line_id.id: abs(l.final_qty) for l in custom_mrp_lines if l.sale_line_id}
    #
    #     # Trigger custom MO generation logic for the specific lines if available
    #     if sale_line_ids and self.sale_order_id and hasattr(self.sale_order_id, 'action_generate_all_mos'):
    #         self.sale_order_id.action_generate_all_mos(lines=sale_line_ids, qty_map=qty_map)
    #
    #     # 3. CONVERT RESULTING RFQS TO USE FACTORY AS VENDOR (For parents with BUY route)
    #     if sale_order.factory_id:
    #         pos = self.env['purchase.order'].search([
    #             ('origin', '=', sale_order.name),
    #             ('state', '=', 'draft'),
    #             ('company_id', '=', sale_order.company_id.id)
    #         ])
    #         for po in pos:
    #             po_product_ids = po.order_line.mapped('product_id.id')
    #             # Check if this PO contains products from our BOM lines that used a BUY route
    #             target_lines = all_lines.filtered(
    #                 lambda l: l.product_id.id in po_product_ids and 'buy' in (l.route_id.name or '').lower()
    #             )
    #             if target_lines:
    #                 po.write({'partner_id': sale_order.factory_id.id})
    #
    #     self.is_parent_procurement_done = True
    #     if self.sale_order_id:
    #         self.sale_order_id.is_parent_procurement_done = True
    #
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'maeknit.replenishment',
    #         'view_mode': 'form',
    #         'res_id': self.id,
    #         'target': 'new',
    #     }
    #
    # def generate_procurements(self):
    #     self.ensure_one()
    #     procurements = []
    #
    #     # Combine lines and component lines for processing
    #     all_lines = []
    #     for line in self.replenishment_component_line_ids:
    #         if line.is_create_procurement and (line.qty > 0 or line.add_qty > 0):
    #             all_lines.append(line)
    #
    #     for line in self.replenishment_line_ids:
    #         if line.is_create_procurement and (line.qty > 0 or line.add_qty > 0):
    #             all_lines.append(line)
    #
    #     # Collect unique procurements
    #     procurement_list = [] # List of dicts: {'product':, 'qty':, 'uom':, 'values':, 'route_id':, 'sale_line_id':}
    #     non_dropship_map = {} # key: (product_id, route_id, sale_line_id) - grouped by SO line to avoid mixing warehouses/groups
    #     subcontracting_groups = {}
    #
    #     for line in all_lines:
    #         # ONLY PROCEED IF SHORTAGE EXISTS (unless it's subcontracting)
    #         is_subcontracting = getattr(line, 'is_subcontracting', False)
    #         if line.final_qty >= 0 and not is_subcontracting:
    #             continue
    #
    #         is_dropship = line.route_id and 'dropship' in line.route_id.name.lower()
    #
    #         if is_dropship:
    #             procurement_product = line.sale_line_id.product_id
    #             product_qty = line.sale_line_id.product_uom_qty
    #             procurement_uom = line.sale_line_id.product_uom
    #         else:
    #             procurement_product = line.product_id
    #             product_qty = abs(line.final_qty)
    #             procurement_uom = line.product_id.uom_id
    #
    #         sale_order = line.sale_line_id.order_id or self.sale_order_id
    #         group_id = sale_order.procurement_group_id
    #         if not group_id:
    #             group_id = self.env['procurement.group'].create({
    #                 'name': sale_order.name,
    #                 'move_type': sale_order.picking_policy,
    #                 'sale_id': sale_order.id,
    #                 'partner_id': sale_order.partner_shipping_id.id,
    #             })
    #             sale_order.procurement_group_id = group_id
    #
    #         if line.sale_line_id:
    #             values = line.sale_line_id._prepare_procurement_values(group_id=group_id)
    #         else:
    #             values = {
    #                 'group_id': group_id,
    #                 'date_planned': sale_order.commitment_date or sale_order.date_order,
    #                 'warehouse_id': sale_order.warehouse_id,
    #                 'partner_id': sale_order.partner_shipping_id.id,
    #                 'company_id': sale_order.company_id,
    #             }
    #         if line.route_id:
    #             values['route_ids'] = line.route_id
    #
    #         if is_dropship:
    #             # Add directly to list (no aggregation as per user request)
    #             procurement_list.append({
    #                 'product': procurement_product,
    #                 'qty': product_qty,
    #                 'uom': procurement_uom,
    #                 'values': values,
    #                 'route_id': line.route_id,
    #                 'sale_order': sale_order,
    #             })
    #         else:
    #             # Aggregate for non-dropship (BUY routes)
    #             key = (procurement_product.id, line.route_id.id if line.route_id else False, line.sale_line_id.id if line.sale_line_id else False)
    #             if key not in non_dropship_map:
    #                 non_dropship_map[key] = {
    #                     'product': procurement_product,
    #                     'qty': product_qty,
    #                     'uom': procurement_uom,
    #                     'values': values,
    #                     'route_id': line.route_id,
    #                     'sale_order': sale_order,
    #                 }
    #             else:
    #                 non_dropship_map[key]['qty'] += product_qty
    #
    #     # Combine aggregated maps into procurement_list
    #     for p_data in non_dropship_map.values():
    #         procurement_list.append(p_data)
    #
    #     for p_data in procurement_list:
    #         procurement_product = p_data['product']
    #         product_qty = p_data['qty']
    #         procurement_uom = p_data['uom']
    #         values = p_data['values']
    #         route_id = p_data['route_id']
    #         sale_order = p_data['sale_order']
    #
    #         # Find or Create Reordering Rule
    #         warehouse = sale_order.warehouse_id
    #         domain = [
    #             ('product_id', '=', procurement_product.id),
    #             ('warehouse_id', '=', warehouse.id),
    #         ]
    #         orderpoint = self.env['stock.warehouse.orderpoint'].search(domain, limit=1)
    #
    #         if not orderpoint:
    #             orderpoint = self.env['stock.warehouse.orderpoint'].create({
    #                 'product_id': procurement_product.id,
    #                 'warehouse_id': warehouse.id,
    #                 'location_id': warehouse.lot_stock_id.id,
    #                 'product_min_qty': abs(product_qty),
    #                 'product_max_qty': abs(product_qty),
    #                 'qty_multiple': 1.0,
    #                 'route_id': route_id.id if route_id else False,
    #                 'trigger': 'auto',
    #             })
    #         else:
    #             orderpoint.write({
    #                 'product_min_qty': abs(product_qty),
    #                 'product_max_qty': abs(product_qty),
    #                 'route_id': route_id.id if route_id else orderpoint.route_id.id,
    #                 'trigger': 'auto',
    #             })
    #
    #         try:
    #             procurements.append(self.env['procurement.group'].Procurement(
    #                 procurement_product, product_qty, procurement_uom,
    #                 warehouse.lot_stock_id,
    #                 procurement_product.name, sale_order.name, sale_order.company_id, values
    #             ))
    #         except TypeError:
    #              procurements.append((
    #                 procurement_product, product_qty, procurement_uom,
    #                 warehouse.lot_stock_id,
    #                 procurement_product.name, sale_order.name, sale_order.company_id, values
    #             ))
    #
    #         # Set Reordering Rule to Manual after procurement generation
    #         orderpoint.write({'trigger': 'manual'})
    #
    #     if procurements:
    #         self.env['procurement.group'].run(procurements)
    #
    #     return {'type': 'ir.actions.act_window_close'}

class MaeknitReplenishmentProductLine(models.TransientModel):
    _name = 'maeknit.replenishment.line'

    replenishment_product_id = fields.Many2one('maeknit.replenishment', string='Replenishment Product')
    product_id = fields.Many2one('product.product', string='Product')
    qty = fields.Float(string='Quantity')
    add_qty = fields.Float(string="Additional Qty")
    is_create_procurement = fields.Boolean(default=False, string="Create Procurement?")
    sale_line_id = fields.Many2one('sale.order.line', string='Sale Line')
    route_id = fields.Many2one('stock.route', 'Route', required=True, ondelete='cascade', index=True)
    lead_time = fields.Integer('Lead Time')
    landed_cost = fields.Float('Landed Cost')
    price_unit = fields.Float('Price Unit')
    cost = fields.Float('Cost')
    is_bom = fields.Boolean('Bom')
    vendor_id = fields.Many2one('res.partner', string="Vendor")
    is_component = fields.Boolean('Component')
    onhand_qty = fields.Float(string="Onhand Qty", compute="_compute_onhand_qty")
    final_qty = fields.Float(string="Final Qty", compute='_compute_final_qty')
    is_subcontracting = fields.Boolean('Is Subcontracting?')
    subcontractor_id = fields.Many2one('res.partner', 'Subcontractor', domain="[('supplier_rank', '>', 0)]")

    @api.depends('product_id')
    def _compute_onhand_qty(self):
        for rec in self:
            rec.onhand_qty = rec.product_id.qty_available if rec.product_id else 0.0

    @api.depends('qty', 'onhand_qty', 'add_qty')
    def _compute_final_qty(self):
        for rec in self:
            rec.final_qty = rec.onhand_qty - rec.qty - rec.add_qty


class MaeknitReplenishmentComponentLine(models.TransientModel):
    _name = 'maeknit.replenishment.component.line'

    replenishment_component_id = fields.Many2one('maeknit.replenishment', string='Replenishment Product')
    product_id = fields.Many2one('product.product', string='Product')
    qty = fields.Float(string='Quantity')
    add_qty = fields.Float(string="Additional Qty")
    is_create_procurement = fields.Boolean(default=False, string="Create Procurement?")
    sale_line_id = fields.Many2one('sale.order.line', string='Sale Line')
    route_id = fields.Many2one('stock.route', 'Route', required=False, ondelete='cascade', index=True)
    lead_time = fields.Integer('Lead Time')
    landed_cost = fields.Float('Landed Cost')
    price_unit = fields.Float('Price Unit')
    cost = fields.Float('Cost')
    is_bom = fields.Boolean('Bom')
    is_component = fields.Boolean('Component')
    onhand_qty = fields.Float(string="Onhand Qty", compute="_compute_onhand_qty")
    final_qty = fields.Float(string="Final Qty", compute='_compute_final_qty')
    is_subcontracting = fields.Boolean('Is Subcontracting?')
    subcontractor_id = fields.Many2one('res.partner', 'Subcontractor', domain="[('supplier_rank', '>', 0)]")
    vendor_id = fields.Many2one('res.partner', 'Vendor', domain="[('supplier_rank', '>', 0)]")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        sale_id = self.env.context.get('active_id')
        order_id = self.env['sale.order'].browse(sale_id)
        if order_id:
            sale_order = order_id

            # ✅ subcontracting default
            if sale_order and sale_order.factory_id:
                # res['is_subcontracting'] = True
                res['subcontractor_id'] = sale_order.factory_id.id

        for sale_line in order_id.order_line:
            # ✅ sale line default
            if sale_line:
                res['sale_line_id'] = sale_line

        return res

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            buy_route = self.env['stock.route'].search([('name', '=', 'Buy')], limit=1)
            dropship_route = self.env['stock.route'].search([('name', '=', 'Dropship Subcontractor on Order')], limit=1)
            
            if not self.route_id:
                if self.is_subcontracting:
                    self.route_id = buy_route.id if buy_route else False
                else:
                    self.route_id = dropship_route.id if dropship_route else (buy_route.id if buy_route else False)

            if self.product_id.seller_ids:
                if self.product_id.seller_ids[0].partner_id :
                    self.vendor_id = self.product_id.seller_ids[0].partner_id.id
                else :
                    self.vendor_id = False


            if self.is_subcontracting and not self.subcontractor_id:
                self._onchange_is_subcontracting()

    @api.onchange('is_subcontracting')
    def _onchange_is_subcontracting(self):
        if self.is_subcontracting:
            if self.replenishment_component_id.sale_order_id.factory_id:
                self.subcontractor_id = self.replenishment_component_id.sale_order_id.factory_id
            
            buy_route = self.env['stock.route'].search([('name', '=', 'Buy')], limit=1)
            if buy_route:
                self.route_id = buy_route
        else:
            self.subcontractor_id = False
            dropship_route = self.env['stock.route'].search([('name', '=', 'Dropship Subcontractor on Order')], limit=1)
            if dropship_route:
                self.route_id = dropship_route

    @api.depends('product_id')
    def _compute_onhand_qty(self):
        for rec in self:
            rec.onhand_qty = rec.product_id.qty_available if rec.product_id else 0.0

    @api.depends('qty', 'onhand_qty', 'add_qty')
    def _compute_final_qty(self):
        for rec in self:
            rec.final_qty = rec.onhand_qty - rec.qty - rec.add_qty
