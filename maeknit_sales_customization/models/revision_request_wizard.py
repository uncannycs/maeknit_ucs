import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re

class RevisionRequestWizard(models.TransientModel):
    _name = 'revision.request.wizard'
    _description = 'Revision Request Wizard'

    sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line', required=False)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', help='Select a sale order to create a line in')
    show_sale_order_selection = fields.Boolean(string='Show SO Selection', default=False, compute='_compute_show_sale_order_selection')
    available_sale_orders = fields.Many2many('sale.order', string='Available Sale Orders', compute='_compute_available_sale_orders')
    product_id = fields.Many2one('product.product', string='Product', readonly=True)

    change_type = fields.Many2one('mrp.eco.type', string='What type of change?', required=True)

    description = fields.Text(string='Description', required=True)
    responsible = fields.Many2one('res.users', string='Responsible', required=True, default=lambda self: self.env.user)

    @api.depends('sale_order_line_id')
    def _compute_show_sale_order_selection(self):
        """Show sale order selection if no line is linked"""
        for wiz in self:
            wiz.show_sale_order_selection = not wiz.sale_order_line_id

    @api.depends('product_id')
    def _compute_available_sale_orders(self):
        """Get available sale orders for this product or partner"""
        for wiz in self:
            if wiz.product_id:
                # Find sale orders that either have this product or are from the same brand
                partner_id = wiz.product_id.product_tmpl_id.brand_id
                domain = ['|',
                    ('order_line.product_id', '=', wiz.product_id.id),
                    ('partner_id', '=', partner_id.id if partner_id else False)
                ]
                domain.append(('state', 'in', ['draft', 'sent', 'sale']))
                wiz.available_sale_orders = self.env['sale.order'].search(domain, limit=20)
            else:
                wiz.available_sale_orders = False

    @api.model
    def default_get(self, fields_list):
        """Set default product from context"""
        res = super().default_get(fields_list)

        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')

        if active_model == 'maeknit.bom.request' and active_id:
            bom_request = self.env['maeknit.bom.request'].browse(active_id)
            if bom_request.product_id:
                res['product_id'] = bom_request.product_id.id
            if bom_request.sale_order_line_id:
                res['sale_order_line_id'] = bom_request.sale_order_line_id.id
            if bom_request.sale_order_id:
                res['sale_order_id'] = bom_request.sale_order_id.id

        return res
    
    def _get_latest_bom(self, product):
        """Prefer variant BOM; fallback to template BOM. Return the newest active one."""
        Bom = self.env['mrp.bom']
        domain_variant = [('product_id', '=', product.id), ('active', '=', True)]
        domain_template = [('product_tmpl_id', '=', product.product_tmpl_id.id), ('active', '=', True)]

        bom = Bom.search(domain_variant, order='version desc, id desc', limit=1)
        if not bom:
            bom = Bom.search(domain_template, order='version desc, id desc', limit=1)
        return bom

    def _find_draft_stage(self, eco_type):
        Stage = self.env['mrp.eco.stage']
        company = self.env.company

        # Build the "In Progress" + company domain
        base_domain = [
            ('name', 'ilike', 'Draft'),
        ]
        logging.info(f" Custom Code: Finding stage for ECO type {eco_type.name if eco_type else 'None'} with base domain {base_domain}")

        # If stage has a proper M2M field, use it; else read from rel table
        if 'type_ids' in Stage._fields:
            type_domain = ['|', ('type_ids', '=', False), ('type_ids', 'in', eco_type.ids)]
            domain = base_domain + type_domain
            logging.info(f" Custom Code: Using M2M field for stage search with domain {domain}")
        else:
            # Get stage_ids from the raw M2M rel table
            stage_ids = []
            if eco_type and eco_type.ids:
                self.env.cr.execute("""
                    SELECT DISTINCT stage_id
                    FROM mrp_eco_stage_type_rel
                    WHERE type_id = ANY(%s)
                """, (eco_type.ids,))
                stage_ids = [r[0] for r in self.env.cr.fetchall()]
                logging.info(f" Custom Code: Found stage_ids {stage_ids} from rel table for type_ids {eco_type.ids}")

            # If we found mappings, restrict to them; otherwise allow generic stages (no mapping)
            if stage_ids:
                domain = base_domain + [('id', 'in', stage_ids)]
                logging.info(f" Custom Code: Using stage_ids {stage_ids} for stage search with domain {domain}")
            else:
                domain = base_domain  # accept generic "In Progress" (no type mapping)
                logging.info(f" Custom Code: No specific stage_ids found; using base domain {domain}")

        stage = Stage.search(domain, order='sequence,id', limit=1)
        logging.info(f" Custom Code: Stage search result: {stage.name if stage else 'None'}")

        if not stage:
            fallback_domain = []
            if 'company_id' in Stage._fields:
                fallback_domain += ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
            if 'type_ids' in Stage._fields:
                fallback_domain += ['|', ('type_ids', '=', False), ('type_ids', 'in', eco_type.ids)]
            elif stage_ids:
                fallback_domain += [('id', 'in', stage_ids)]
            stage = Stage.search(fallback_domain, order='sequence,id', limit=1, offset=1)


        return stage  # stage.id is your stage_id

    def _safe_vals(self, model, vals):
        """Keep only valid keys and normalize relational (Many2one) fields."""
        clean = {}
        for key, val in vals.items():
            if key in model._fields:
                field = model._fields[key]
                # Handle Many2one: convert (id, name) or recordset to ID
                if field.type == 'many2one':
                    if isinstance(val, tuple):
                        clean[key] = val[0]
                    elif hasattr(val, 'id'):
                        clean[key] = val.id
                    else:
                        clean[key] = val
                else:
                    clean[key] = val
        return clean

    # ---------- actions ----------
    def action_submit_request(self):
        for wiz in self:
            # Check if we need to create a sale order line first
            if not wiz.sale_order_line_id:
                if not wiz.sale_order_id:
                    raise ValidationError(_(
                        "Please select a Sale Order to connect this revision request.\n\n"
                        "If no sale orders are available, please create one first and then retry."
                    ))

                if not wiz.product_id:
                    raise ValidationError(_("No product found. Please set the product first."))

                # Create a sale order line in the selected sale order
                sale_order = wiz.sale_order_id
                product = wiz.product_id

                # Find a base line to copy settings from
                base_line = sale_order.order_line.filtered(lambda l: l.product_id).sorted(lambda l: l.create_date)[-1:]

                rel_service_product = False
                if base_line and base_line.rel_service:
                    rel_service_product = base_line.rel_service
                else:
                    rel_service_product = (
                        sale_order.order_line.filtered(lambda l: l.rel_service).mapped('rel_service')[:1]
                    )
                    rel_service_product = rel_service_product[0] if rel_service_product else False

                # Create the new line
                new_line = self.env['sale.order.line'].create({
                    'order_id': sale_order.id,
                    'product_id': product.id,
                    'product_uom_qty': 1.0,
                    'rel_service': rel_service_product.product_variant_id.id if rel_service_product else False,
                    'style_family': base_line.style_family if base_line else False,
                    'route_id': base_line.route_id.id if base_line and base_line.route_id else False,
                    'crm_child_lead_id': base_line.crm_child_lead_id.id if base_line and base_line.crm_child_lead_id else False,
                })

                wiz.sale_order_line_id = new_line
                logging.info(f"Created new sale order line {new_line.id} for product {product.name} in SO {sale_order.name}")

            # Now proceed with normal flow
            sale_order_line = wiz.sale_order_line_id
            line = wiz.sale_order_line_id
            product = line.product_id

            if not product:
                raise ValidationError(_("Sale order line has no product."))

            # 1) Latest BOM (original)
            bom = wiz._get_latest_bom(product)
            if not bom:
                raise ValueError(_("No BOM found for product %s") % product.display_name)
            logging.info(f" Custom Code: Found BOM {bom.id} (version {bom.version}) for product {product.display_name}")
            # 2) Copy BOM (next revision, inactive)
            existing_boms = self.env['mrp.bom'].search([
                '|',
                ('product_id', '=', product.id),
                ('product_tmpl_id', '=', product.product_tmpl_id.id)
            ])
            logging.info(f" Custom Code: Existing BOMs for product {product.display_name}: {[b.id for b in existing_boms]}")
            
            max_bom_version = 0
            for existing_bom in existing_boms:
                if existing_bom.version:
                    max_bom_version = max(max_bom_version, existing_bom.version)
            
            # Create next BOM version
            new_version = max_bom_version + 1
            logging.info(f" Custom Code: Creating new BOM version {new_version} for product {product.display_name} (max existing: {max_bom_version})")
            for line in bom.bom_line_ids:
                for field in line._fields:
                    try:
                        logging.info('BOM Line Field %s: %s', field, getattr(line, field))
                        getattr(line, field)
                    except Exception as e:
                        logging.error("Broken field %s on BOM line %s: %s", field, line.id, e)
            
            bom_copy = bom.copy(default={
                        'version': new_version,
                        'active': True,
                        'previous_bom_id': bom.id,
                        'bom_line_ids': [
                            (0, 0, {
                                'product_id': line.product_id.id,
                                'product_qty': line.product_qty,
                                'product_uom_id': line.product_uom_id.id,
                                'sequence': line.sequence,
                                'operation_id': line.operation_id.id if line.operation_id else False,
                                'tracking': line.tracking,
                                'manual_consumption': line.manual_consumption,
                                'x_ply': line.x_ply,
                                'left_carrier': line.left_carrier,
                                'right_carrier': line.right_carrier,
                                'structure_id': line.structure_id.id if line.structure_id else False,
                                'cost_share': line.cost_share,
                            })
                            for line in bom.bom_line_ids
                        ]
                    })

            bom.active = False



            logging.info(f" Custom Code: Copied BOM {bom.id} to new BOM {bom_copy.id} with version {new_version}")

            # 3) Create ECO with original + new revision
            Eco = self.env['mrp.eco']
            eco_vals = {
                'name': wiz.description or _("Revision for %s") % product.display_name,
                'type_id': wiz.change_type.id,
                'bom_id': bom.id,                 # ORIGINAL
                'new_bom_id': bom_copy.id,        # COPY (V2)
                'product_tmpl_id': product.product_tmpl_id.id,
                'user_id': wiz.responsible.id,
                'effectivity': 'asap',
                'state': 'draft',
                'will_update_version': True,
            }

            stage = self._find_draft_stage(wiz.change_type)
            if stage:
                eco_vals['stage_id'] = stage.id

            eco = Eco.create(wiz._safe_vals(Eco, eco_vals))
            logging.info(f" Custom Code: Created ECO {eco.id} for product {product.display_name}")

            # Find any previous BOM Request tied to the old BOM
            old_bom_request = self.env['maeknit.bom.request'].search(
                [('bom_id', '=', bom.id)],
                order='create_date desc',
                limit=1
            )

            # Prepare base dict from old record if available
            if old_bom_request:
                old_vals = old_bom_request.read()[0]  # safe dict copy
                old_vals.pop('id', None)
            else:
                old_vals = {}

            # Define new / override fields
            new_vals = {
                'eco_id': eco.id,
                'bom_id': eco.new_bom_id.id,
                'product_id': eco.new_bom_id.product_id.id
                    if eco.new_bom_id.product_id
                    else eco.new_bom_id.product_tmpl_id.product_variant_ids[0].id,
                'product_tmpl_id': (
                    eco.new_bom_id.product_tmpl_id.id
                    if eco.new_bom_id.product_tmpl_id
                    else product.product_tmpl_id.id
                ),
                'product_qty': eco.new_bom_id.product_qty,
                'notes': f'BOM Request created from ECO revision {eco.name}',
                'state': 'draft',
                'rel_service': old_bom_request.rel_service.id if old_bom_request else False,
            }

            bom_request_vals = {**old_vals, **new_vals}
            
            for field in ['company_id', 'partner_id', 'sale_order_id', 'sale_order_line_id', 'user_id']:
                val = bom_request_vals.get(field)
                if isinstance(val, tuple):  # (1, 'MAEKNIT - New York')
                    bom_request_vals[field] = val[0]
                elif hasattr(val, 'id'):  # recordset (res.company(1,))
                    bom_request_vals[field] = val.id

            # Merge and sanitize
            merged_vals = {**old_vals, **new_vals}

            # Remove all mail/thread or transient metadata fields
            for key in [
                'message_follower_ids', 'message_partner_ids', 'message_ids',
                'website_message_ids', 'activity_ids', 'activity_user_id',
                'activity_state', 'activity_date_deadline', 'activity_type_id',
                'activity_summary', 'activity_exception_decoration', 'activity_exception_icon',
                'has_message', 'message_needaction', 'message_needaction_counter',
                'message_has_error', 'message_has_error_counter',
                'message_attachment_count', 'message_main_attachment_id', 'mo_id',
            ]:
                merged_vals.pop(key, None)

            bom_request_vals = wiz._safe_vals(self.env['maeknit.bom.request'], merged_vals)
            # Final debug log
            logging.info(f" Custom Code: FINAL CLEANED BOM REQUEST VALS => {bom_request_vals}")
            
            sale_order = self.env['sale.order'].search([
                    ('state', 'in', ['draft', 'sent', 'sale']),
                    ('order_line.product_id', '=', product.id),
                ], limit=1)
            
            
            original_product = product
            
            if sale_order:
                bom_request_vals['sale_order_id'] = sale_order.id
                # Find the specific order line
                order_line = sale_order.order_line.filtered(
                    lambda l: l.product_id.id == bom_request_vals['product_id']
                )
                
                if order_line and order_line.rel_service:
                    service_name = order_line.rel_service.name
                    # sample is auto-computed from BOM version, no need to set it
                    if 'Swatch Service' == service_name or 'Grading Service' == service_name:
                        bom_request_vals['revision'] = "Revision {}".format(new_version)

                logging.info(f" Custom Code: Order line found: {order_line}")
                logging.info(f" Custom Code: Found sale order {sale_order.name} for product {product.display_name}")

                # Sample # is derived from BOM version (auto-computed)
                sample = f"Sample {new_version}"
                # Remove sample from BOM request vals (auto-computed from BOM version)
                bom_request_vals.pop('sample', None)

                if order_line:
                    base_line = order_line.sorted(lambda l: l.create_date)[-1:]  # last one only
                else:
                    # If no specific line found, try to find any line in the sale order
                    base_line = sale_order.order_line.filtered(lambda l: l.product_id).sorted(lambda l: l.create_date)[-1:]
                
                rel_service_product = False
                if base_line and base_line.rel_service:
                    rel_service_product = base_line.rel_service  # product.product
                else:
                    rel_service_product = (
                        sale_order.order_line.filtered(lambda l: l.rel_service).mapped('rel_service')[:1]
                    )
                    rel_service_product = rel_service_product[0] if rel_service_product else False

                if not base_line:
                    raise ValidationError(_("No base sale order line found for product %s") % original_product.display_name)

                product_line = self.env['sale.order.line'].create({
                    'order_id': sale_order.id,
                    'crm_child_lead_id': base_line.crm_child_lead_id.id,
                    'product_id': original_product.id,
                    'product_uom_qty': 1.0,  # Sample quantity
                    'sample': sample,
                    'rel_service': rel_service_product.product_variant_id.id,
                    'style_family': base_line.style_family,
                    'is_development_reverse_service': True,
                    'route_id': base_line.route_id.id if base_line.route_id else False,
                })
                order_line = product_line
                
                if order_line:
                    bom_request_vals['sale_order_line_id'] = order_line[0].id
            

            bom_request = self.env['maeknit.bom.request'].create(bom_request_vals)
            logging.info(f" Custom Code: Created BOM Request {bom_request.id} with eco_id={bom_request.eco_id.id if bom_request.eco_id else None}")
            mo_action = False
            if not self.env.context.get('revision_skip_generate_mo'):
                logging.info(f" Custom Code: Calling _generate_mo_from_request for BOM Request {bom_request.id}")
                mo_action = self._generate_mo_from_request(bom_request)
                logging.info(f" Custom Code: After MO generation, BOM Request {bom_request.id} has mo_id={bom_request.mo_id.id if bom_request.mo_id else None}")
            if mo_action:
                return mo_action
            # (Optional) If you prefer, let Odoo create the copy for you:
            # eco.action_new_revision()

            sale_order_line.revision_status = 'requested'
            origin_model = self.env.context.get('active_model')
            origin_id = self.env.context.get('active_id')
            logging.info(f" Custom Code: [REVISION] Triggered from {origin_model} (ID: {origin_id})")
                
            if origin_model == 'sale.order.line':
                # quiet close
                return {'type': 'ir.actions.act_window_close'}
            elif origin_model == 'maeknit.bom.request':
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('BOM Request'),
                    'res_model': 'maeknit.bom.request',
                    'res_id': bom_request.id,
                    'view_mode': 'form',
                    'target': 'current',
                }

    def _generate_mo_from_request(self, bom_request):
        """Optionally create an MO after the revision-generated BOM request."""
        try:
            bom_request.with_context(skip_component_validation=True).action_generate_mo()
        except ValidationError as err:
            logging.warning("Custom Code: Unable to auto-create MO for revision (%s): %s", bom_request.name, err)
        except Exception as err:
            logging.info("Custom Code: MO creation failed for revision %s: %s", bom_request.name, err)
        if bom_request.mo_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Manufacturing Order'),
                'res_model': 'mrp.production',
                'res_id': bom_request.mo_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False

    def action_cancel(self):
        """Cancel the revision request"""
        return {'type': 'ir.actions.act_window_close'}
