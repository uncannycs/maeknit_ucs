from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    related_service = fields.Char(string="Old Related Service (Deprecated)")
    rel_service = fields.Many2one('product.product', string="Related Service")
    style_family = fields.Char(string="Style Family")
    hidden = fields.Boolean(string="Hidden")
    revision_status = fields.Selection([
        ('none', 'No Revision'),
        ('requested', 'Revision Requested'),
    ], string="Revision", default='none')
    sample = fields.Char(string="Sample")
    revision = fields.Char(string="Revision")
    size = fields.Char(string="Size", compute="_compute_size_colorway", store=True, readonly=False)
    line_currency_id = fields.Many2one(
        'res.currency',
        related='order_id.currency_id',
        store=True,
        readonly=False,
        string='Line Currency'
    )

    is_development_reverse_service = fields.Boolean(
        string="Is Development/ Reverse Service",
        compute="_compute_is_development_reverse_service",
        store=False
    )
    is_grading_service = fields.Boolean(
        string="Is Grading Service",
        compute="_compute_is_grading_service",
        store=True
    )
    is_production_service = fields.Boolean(
        string="Is Production Service",
        compute="_compute_is_production_service",
        store=False
    )
    is_swatch_service = fields.Boolean(
        string="Is Swatch Service",
        compute="_compute_is_swatch_service",
        store=False
    )
    colorway = fields.Char(string="Colorway", compute="_compute_size_colorway", store=True, readonly=False)
    pricing_id = fields.Many2one('sale.order.line.pricing', string='Pricing Data', ondelete='cascade')
    has_pricing_data = fields.Boolean(string='Has Pricing', compute='_compute_has_pricing_data')
    
    @api.depends('pricing_id')
    def _compute_has_pricing_data(self):
        for record in self:
            record.has_pricing_data = bool(record.pricing_id)
    
    crm_child_lead_id = fields.Many2one(
        'crm.lead', string="Child Opportunity"
    )

    @api.depends('rel_service', 'rel_service.name')
    def _compute_is_development_reverse_service(self):
        for record in self:
            record.is_development_reverse_service = (
                record.rel_service and 
                record.rel_service.name == 'Development Service'
            )

    @api.depends('rel_service', 'rel_service.name')
    def _compute_is_grading_service(self):
        for record in self:
            record.is_grading_service = (
                record.rel_service and record.rel_service.name == 'Grading Service'
            )
            logging.info(f"[STEP 2] Compute is_grading_service: "
                          f"{record.rel_service.name if record.rel_service else 'None'} -> "
                          f"{record.is_grading_service}")

    @api.depends('rel_service', 'rel_service.name')
    def _compute_is_production_service(self):
        for record in self:
            record.is_production_service = (
                record.rel_service and record.rel_service.name == 'Production Service'
            )

    @api.depends('rel_service', 'rel_service.name')
    def _compute_is_swatch_service(self):
        for record in self:
            record.is_swatch_service = (
                record.rel_service and record.rel_service.name == 'Swatch Service'
            )

    @api.depends('product_id', 'product_id.product_template_attribute_value_ids')
    def _compute_size_colorway(self):
        """Auto-populate Size and Colorway from product variant attributes"""
        for line in self:
            size_val = False
            colorway_val = False

            if line.product_id and line.product_id.product_template_attribute_value_ids:
                for ptav in line.product_id.product_template_attribute_value_ids:
                    attr_name = ptav.attribute_id.name.lower()
                    value_name = ptav.product_attribute_value_id.name

                    if 'size' in attr_name:
                        size_val = value_name
                    elif 'color' in attr_name or 'colorway' in attr_name:
                        colorway_val = value_name

            # Only update if the field is empty (don't overwrite manual entries)
            if not line.size:
                line.size = size_val
            if not line.colorway:
                line.colorway = colorway_val

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Override to preserve price_unit when it was explicitly set (e.g. from CRM quotation context)."""
        if not self.product_id:
            return

    @api.onchange('product_id')
    def _onchange_product_id_assign_service(self):
        if self.product_id and self.product_id.type == 'consu':
            logging.info(f"[STEP 3] Onchange product {self.product_id.display_name}")
            if self.order_id and self.order_id.x_rel_service_id and not self.rel_service:
                self.rel_service = self.order_id.x_rel_service_id
                logging.info(f"[STEP 4] Assigned related service "
                             f"{self.rel_service.display_name} from order")

    def action_open_price_calculator(self):
        """Open the price calculator widget"""
        self.ensure_one()
        
        if not self.pricing_id:
            # Check if one exists for this line first
            existing_pricing = self.env['sale.order.line.pricing'].search([
                ('sale_order_line_id', '=', self.id)
            ], limit=1)
            
            if existing_pricing:
                self.pricing_id = existing_pricing
            else:
                self.pricing_id = self.env['sale.order.line.pricing'].create({
                    'sale_order_line_id': self.id,
                })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'price_calculator_widget',
            'target': 'new',
            'context': {
                'sale_order_line_id': self.id,
                'pricing_id': self.pricing_id.id,
            }
        }
    
    def action_apply_pricing_to_all(self):
        """Apply pricing from this line to all other lines in the SO with the same service"""
        self.ensure_one()
        
        if not self.pricing_id:
            raise ValidationError(_("No pricing data to apply"))
        
        # Find other lines with the same service type
        other_lines = self.env['sale.order.line'].search([
            ('order_id', '=', self.order_id.id),
            ('id', '!=', self.id),
            ('rel_service', '=', self.rel_service.id),
        ])
        
        if not other_lines:
            return {'type': 'ir.actions.act_window_close'}
        
        for line in other_lines:
            if line.pricing_id:
                # Update existing pricing
                line.pricing_id.write({
                    'material_cost': self.pricing_id.material_cost,
                    'margin_percentage': self.pricing_id.margin_percentage,
                    'shipping_cost': self.pricing_id.shipping_cost,
                })
                # Delete existing operations
                line.pricing_id.operation_ids.unlink()
                new_pricing = line.pricing_id
            else:
                # Create new pricing
                new_pricing = self.env['sale.order.line.pricing'].create({
                    'sale_order_line_id': line.id,
                    'material_cost': self.pricing_id.material_cost,
                    'margin_percentage': self.pricing_id.margin_percentage,
                    'shipping_cost': self.pricing_id.shipping_cost,
                })
                line.pricing_id = new_pricing
            
            # Copy operations
            for op in self.pricing_id.operation_ids:
                self.env['sale.order.line.pricing.operation'].create({
                    'pricing_id': new_pricing.id,
                    'sequence': op.sequence,
                    'operation_id': op.operation_id.id if op.operation_id else False,
                    'workcenter_id': op.workcenter_id.id if op.workcenter_id else False,
                    'employee_id': op.employee_id.id if op.employee_id else False,
                    'expected_minutes': op.expected_minutes,
                    'hourly_rate': op.hourly_rate,
                })
            
            # Update line price
            line.write({
                'price_unit': new_pricing.total_cost,
            })
        
        return {'type': 'ir.actions.act_window_close'}

    def action_request_revision(self):
        logging.info(f"[STEP 5] Opening Revision Wizard for line {self.id}")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Request Revision',
            'res_model': 'revision.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_sale_order_line_id': self.id}
        }

    def action_add_grading_sizes(self):
        self.ensure_one()
        logging.info(f"[STEP 6] Opening Grading Wizard for line {self.id}")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Grading Sizes',
            'res_model': 'grading.size.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.order_id.id,
                'default_product_id': self.product_id.id,
                'default_sale_order_line_id': self.id,
            }
        }

    @api.model_create_multi
    def create(self, vals_list):
        SaleOrder = self.env['sale.order']
        ProductCategory = self.env['product.category']

        # --- Pre-validate all lines to avoid partial creation ----------------------
        missing_lead_orders = set()
        for vals in vals_list:
            order_id = vals.get('order_id')
            if order_id:
                order = SaleOrder.browse(order_id)
                if not order.lead_id:
                    missing_lead_orders.add(order.name or str(order_id))
            else:
                missing_lead_orders.add(f"(no order_id in vals: {vals})")

        if missing_lead_orders:
            raise ValidationError(_("You must set a Collection Name before adding products. "
                                    "Orders missing collection: %s") % ", ".join(sorted(missing_lead_orders)))

        # --- Create all lines in one go -------------------------------------------
        lines = super().create(vals_list)

        # --- Post-create normalization per line -----------------------------------
        for line in lines:
            order = line.order_id

            # 1) Auto-assign related service if missing
            if (not line.rel_service
                and order.x_rel_service_id
                and line.product_id
                and line.product_id.type == 'consu'):
                line.rel_service = order.x_rel_service_id.id
                logging.info("[STEP 9] Auto-assigned rel_service: %s", line.rel_service.display_name)

            # 2) Adjust product category by service type (only when both exist)
            service_name = (line.rel_service.name if line.rel_service else "") or ""
            if line.product_id and service_name:
                tmpl = line.product_id.product_tmpl_id

                def ensure_category(name: str):
                    cat = ProductCategory.search([('name', '=', name)], limit=1)
                    if not cat:
                        cat = ProductCategory.create({'name': name})
                        logging.info("Created product.category '%s'", name)
                    # align both categ_id and custom product_category flag
                    target = name.lower()
                    if tmpl.categ_id != cat or (tmpl.product_category or '').lower() != target:
                        tmpl.write({'categ_id': cat.id, 'product_category': target})
                        logging.info("Updated template '%s' category -> %s", tmpl.display_name, target)

                if line.product_id.type == 'consu':
                    if service_name in ('Development Service', 'Production Service', 'Grading Service'):
                        ensure_category('Garment')
                    elif service_name == 'Swatch Service':
                        ensure_category('Swatch')

            # 3) CRM Child Lead linkage (skipped when called from production grid generation)
            if line.product_id and not line.crm_child_lead_id \
                    and not self.env.context.get('skip_crm_child_lead'):
                logging.info("[STEP 15] Processing CRM child lead linkage for SO line %s", line.id)

                domain = [
                    ('parent_id', '=', order.lead_id.id),
                    ('x_project_type', '=', 'style'),
                ]
                if line.style_family:
                    domain.append(('style_family', '=', line.style_family))
                else:
                    domain.append(('name', 'ilike', line.product_id.display_name))
                logging.info("[STEP 16 A] Child lead search domain: %s", domain)

                existing_child = self.env['crm.lead'].search(domain, limit=1)
                if existing_child:
                    line.crm_child_lead_id = existing_child.id
                else:
                    # Only create child for non-swatch services
                    if service_name != 'Swatch Service':
                        child_vals = {
                            'name': f"{line.product_id.display_name}",
                            'type': 'opportunity',
                            'partner_id': order.partner_id.id,
                            'parent_id': order.lead_id.id,
                            'x_project_type': 'style',
                            'expected_revenue': line.price_subtotal or 0.0,
                            'description': f"Auto-created from Sale Order {order.name}, Line {line.product_id.display_name}",
                        }
                        child = self.env['crm.lead'].create(child_vals)
                        logging.info("[STEP 20] Created new child lead %s (style_family=%s)", child.name, child.style_family)
                        line.crm_child_lead_id = child.id
                        line.style_family = child.style_family

                        if not line.sample:
                            line.sample = 'Sample 1'

                    logging.info("[STEP 21] Updated style_family to %s", line.style_family)

                    # If grading service, append size note to child
                    if getattr(line, 'is_grading_service', False) and line.rel_service:
                        same_product_lines = self.env['sale.order.line'].search([
                            ('order_id', '=', order.id),
                            ('product_id', '=', line.product_id.id),
                            ('rel_service', '=', line.rel_service.id),
                        ])
                        if len(same_product_lines) > 1 and line.crm_child_lead_id:
                            sizes = [l.size for l in same_product_lines if getattr(l, 'size', False)]
                            if sizes:
                                note = ("Grading service: Multiple sizes for %s\nSizes: %s"
                                        % (line.product_id.display_name, ", ".join(sizes)))
                                line.crm_child_lead_id.write({'description': (line.crm_child_lead_id.description or '') + '\n' + note})
                                logging.info("[STEP 21] Updated child lead with grading size notes")

            logging.info("[STEP 22] Sale order line %s created successfully.", line.id)

        return lines

    def action_edit_product_name(self):
        """Open product form to edit product name"""
        self.ensure_one()
        if not self.product_id:
            raise ValidationError(_("No product selected on this line"))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Edit Product: %s') % self.product_id.name,
            'res_model': 'product.template',
            'res_id': self.product_id.product_tmpl_id.id,
            'view_mode': 'form',
            'target': 'new',  # Open in dialog
            'context': {'form_view_initial_mode': 'edit'},  # Open in edit mode
        }


    def _check_line_unlink(self):
        """
        Extend the check for line deletion to allow unlinking if NO delivery or invoice exists.
        """
        # Call super to get the lines Odoo normally blocks in a confirmed SO
        lines_to_block = super()._check_line_unlink()

        # Filter the blocked lines to ONLY return those that have actual delivery or invoice progress
        # If a line has no delivery and no invoice, it will be removed from this 'blocked' set,
        # thereby allowing the deletion in confirms state.
        return lines_to_block.filtered(
            lambda line: line.qty_delivered > 0 or line.qty_invoiced > 0 or line.invoice_lines
        )

    def unlink(self):
        """
        Ensure related stock moves (pickings) are cancelled before the line is deleted
        to prevent orphaned records in the inventory system.
        """
        # Select lines in 'sale' state that are being unlinked
        sale_lines = self.filtered(lambda l: l.state == 'sale')
        if sale_lines:
            # Cancel associated stock moves that are not already done or cancelled
            moves_to_cancel = sale_lines.mapped('move_ids').filtered(
                lambda m: m.state not in ['cancel', 'done']
            )
            if moves_to_cancel:
                moves_to_cancel._action_cancel()

        return super().unlink()