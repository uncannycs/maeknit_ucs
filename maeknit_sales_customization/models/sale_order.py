from odoo import models, fields, api, _
import logging
from odoo.exceptions import ValidationError, UserError
import re
import json

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    _MO_BUTTON_FACTORIES = frozenset({
        'MAEKNIT - NEW YORK',
        'MAEKNIT UK LIMITED',
    })
    _ALWAYS_DIRECT_MO_SERVICES = frozenset({
        'development service',
        'swatch service',
        'production service',
    })
    _UK_ONLY_DIRECT_MO_SERVICES = frozenset({
        'grading service',
    })
    _UK_MANUFACTURE_KEYWORDS = ('manufacture', 'uk')

    # Many2one field to link directly to CRM leads
    lead_id = fields.Many2one(
                    'crm.lead',
                    string="Collection Name",
                    domain="[('type', 'in', ['lead', 'opportunity']),"
                           " ('partner_id', '=', partner_id),"
                           " ('x_project_type', '=', 'collection')]",
                    required=True
                )

    # Field to display child CRM leads for quoting (computed, not stored)
    child_crm_leads_to_quote = fields.Many2many('crm.lead',
                                                string="Child Leads",
                                                compute='_compute_child_crm_leads_to_quote',
                                                store=False,
                                                help="Child opportunities linked to the main lead of this Sales Order."
                                               )

    # Field to track selected child leads for quote generation (stored Many2many)
    selected_child_leads = fields.Many2many('crm.lead',
                                            'sale_order_selected_leads_rel',
                                            'sale_order_id',
                                            'lead_id',
                                            string="Selected Child Leads",
                                            help="Child leads selected for quote generation."
                                           )
    manufacturing_due_date = fields.Date(string='Manufacturing Due Date', store=True,
        readonly=False)
    
    quotation_date = fields.Date(string='Quotation Sent Date', store=True,
        readonly=True, help="Date when quotation was first sent by email")
    # New computed field to list unique related service types from order lines
    x_rel_services = fields.Char(
        string="Services",
        compute='_compute_rel_services',
        store=True, # Store for easier filtering/searching
    )

    x_rel_service_id = fields.Many2one(
                            "product.product",
                            string="Service",
                            domain="[('type','=','service'), ('name','in',['Development Service','Swatch Service','Grading Service','Production Service'])]",
                            help="Main related service for this Sales Order",
                        )
    x_service_from_crm = fields.Boolean(
        string="Service from CRM",
        default=False,
        help="Indicates if the service was inherited from CRM lead"
    )
    # New computed field to list unique style families from order lines
    x_quoted_style_families = fields.Text(
        string="Quoted Style Families",
        compute='_compute_quoted_style_families',
        store=True, # Store for easier filtering/searching
        help="Comma-separated list of unique style families included in this sales order."
    )

    x_project_count = fields.Integer(compute="_compute_x_project_count")
    bom_request_ids = fields.One2many('maeknit.bom.request', 'sale_order_id', string='BOM Requests')
    bom_request_count = fields.Integer(compute="_compute_bom_request_count", string="BOM Requests")
    x_grading_data = fields.Char(
            string="Grading Data",
            help="JSON data for grading items and sizes"
        )
    x_swatch_data = fields.Char(string="Swatch Data", help="Auto-generated swatch info from SO")
    region = fields.Char(string="Region")

    is_swatch_service = fields.Boolean(
    string="Is Swatch Service",
    compute="_compute_is_swatch_service",
    store=False
    )

    is_production_service = fields.Boolean(
    string="Is Production Service",
    compute="_compute_is_production_service",
    store=False
    )

    button_generate_bom_queue_visible = fields.Boolean(
        string="Show Generate BOM QUEUE Button",
        store=True,
        default=True,
    )

    direct_mo_mode = fields.Boolean(
        string="Direct MO Mode",
        compute="_compute_direct_mo_mode",
        store=True,
        help="Auto hide the BOM queue button and shortcut directly to the MO. "
             "Always on for Development and Swatch services; "
             "on for Grading service only when a UK manufacture route is chosen."
    )

    x_service_badge = fields.Selection(
    [
        ('success', 'Success'),
        ('info', 'Info'),
        ('primary', 'Primary'),
        ('warning', 'Warning'),
    ],
    compute='_compute_x_service_badge',
    store=False,
    )

    def _compute_x_service_badge(self):
        for order in self:
            name = order.x_rel_service_id.name or ''
            if name == 'Development Service':
                order.x_service_badge = 'success'
            elif name == 'Swatch Service':
                order.x_service_badge = 'info'
            elif name == 'Grading Service':
                order.x_service_badge = 'primary'
            elif name == 'Production Service':
                order.x_service_badge = 'warning'
            else:
                order.x_service_badge = False

    manufacturing_order_count = fields.Integer(
        string="Manufacturing Orders",
        compute="_compute_manufacturing_order_count",
        store=False,
    )

    purchase_order_count = fields.Integer(
        string="Purchase Orders",
        compute="_compute_purchase_order_count",
        store=False,
    )

    generate_mo_button_visible = fields.Boolean(
        string="Show Generate MO Button",
        store=True,
        default=True,
    )
    use_generate_mo_label = fields.Boolean(
        string="Use Generate MO Label",
        compute="_compute_use_generate_mo_label",
        store=False,
    )

    @api.depends('x_rel_service_id', 'order_line.route_id', 'order_line.route_id.name')
    def _compute_direct_mo_mode(self):
        for order in self:
            service_name = (order.x_rel_service_id.name or '').strip().lower()

            # Development + Swatch: always skip BOM Queue, go direct to MO
            if service_name in self._ALWAYS_DIRECT_MO_SERVICES:
                order.direct_mo_mode = True
                continue

            # Grading: only direct MO when UK manufacture route is detected
            if service_name in self._UK_ONLY_DIRECT_MO_SERVICES:
                route_lines = order.order_line.filtered(lambda l: l.route_id)
                order.direct_mo_mode = any(
                    all(kw in (route.name or '').lower() for kw in self._UK_MANUFACTURE_KEYWORDS)
                    for route in route_lines.mapped("route_id")
                )
                continue

            order.direct_mo_mode = False

    @api.depends('factory_id', 'factory_id.name')
    def _compute_use_generate_mo_label(self):
        for order in self:
            order.use_generate_mo_label = order._is_internal_factory()

    @api.depends('bom_request_ids', 'bom_request_ids.mo_id', 'name')
    def _compute_manufacturing_order_count(self):
        for order in self:
            logging.info(" Custom Code: [MO COUNT] Computing for SO %s (ID: %s)", order.name, order.id)
            logging.info(" Custom Code: [MO COUNT] Total bom_request_ids: %d, IDs: %s",
                        len(order.bom_request_ids), order.bom_request_ids.ids)

            # Get MOs linked through BOM Requests
            bom_requests = order.bom_request_ids.filtered(lambda r: r.mo_id)
            logging.info(" Custom Code: [MO COUNT] BOM requests with mo_id: %d, IDs: %s",
                        len(bom_requests), bom_requests.ids)

            for req in bom_requests:
                logging.info(" Custom Code: [MO COUNT]   - BOM Req %s (ID: %s) -> MO: %s (ID: %s), ECO: %s",
                            req.name, req.id, req.mo_id.name if req.mo_id else 'None',
                            req.mo_id.id if req.mo_id else 'None',
                            req.eco_id.id if req.eco_id else 'None')

            mo_from_bom = bom_requests.mapped("mo_id")

            # Also get MOs created directly (for Production Service) - those with origin = SO name
            direct_mos = self.env['mrp.production'].search([
                ('origin', '=', order.name)
            ]) if order.name else self.env['mrp.production']

            # Combine both sets (avoid duplicates)
            all_mos = mo_from_bom | direct_mos

            order.manufacturing_order_count = len(all_mos)
            logging.info(" Custom Code: [MO COUNT] Final count: %d (BOM: %d, Direct: %d), MO IDs: %s",
                         len(all_mos), len(mo_from_bom), len(direct_mos), all_mos.ids)

    def action_view_manufacturing_orders(self):
        self.ensure_one()

        # Get MOs linked through BOM Requests
        bom_requests = self.env["maeknit.bom.request"].search(
            [("sale_order_id", "=", self.id), ("mo_id", "!=", False)]
        )
        mo_from_bom = bom_requests.mapped("mo_id")

        # Get MOs created directly (for Production Service)
        direct_mos = self.env['mrp.production'].search([
            ('origin', '=', self.name)
        ]) if self.name else self.env['mrp.production']

        # Combine both sets
        all_mos = mo_from_bom | direct_mos

        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.production",
            "view_mode": "list,form",
            "domain": [("id", "in", all_mos.ids)] if all_mos else [("id", "=", 0)],
            "context": {"create": False},
            "name": _("Manufacturing Orders"),
        }

    @api.depends('bom_request_ids.purchase_order_id', 'name')
    def _compute_purchase_order_count(self):
        for order in self:
            # POs linked through BOM Requests
            po_from_bom = order.bom_request_ids.mapped('purchase_order_id')

            # POs created with origin = SO name (fallback)
            direct_pos = self.env['purchase.order'].search([
                ('origin', '=', order.name)
            ]) if order.name else self.env['purchase.order']

            all_pos = po_from_bom | direct_pos
            order.purchase_order_count = len(all_pos)

    def action_view_purchase_orders(self):
        self.ensure_one()

        po_from_bom = self.bom_request_ids.mapped('purchase_order_id')
        direct_pos = self.env['purchase.order'].search([
            ('origin', '=', self.name)
        ]) if self.name else self.env['purchase.order']

        all_pos = po_from_bom | direct_pos

        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", all_pos.ids)] if all_pos else [("id", "=", 0)],
            "context": {"create": False},
            "name": _("Purchase Orders"),
        }


    @api.depends('x_rel_service_id')
    def _compute_is_swatch_service(self):
        for order in self:
            order.is_swatch_service = (
                order.x_rel_service_id
                and order.x_rel_service_id.name == "Swatch Service"
            )

    def _compute_is_production_service(self):
        for order in self:
            order.is_production_service = (
                order.x_rel_service_id
                and order.x_rel_service_id.name == "Production Service"
            )

    def action_quotation_send(self):
        """Override to set quotation_date when first sent by email"""
        # Set quotation_date only if not already set (first time sending)
        if not self.quotation_date:
            self.quotation_date = fields.Date.context_today(self)
            logging.info(f" Custom Code: [SO] Set quotation_date to {self.quotation_date} for order {self.name}")
        return super(SaleOrder, self).action_quotation_send()

    def _compute_x_project_count(self):
        for order in self:
            projects = order.order_line.mapped("project_id")
            order.x_project_count = len(projects)
            logging.info(f" Custom Code: [STEP 1] Order {order.name}: Found {order.x_project_count} linked projects.")

    def _compute_bom_request_count(self):
        for order in self:
            bom_requests = self.env['maeknit.bom.request'].search([
                ('sale_order_id', '=', order.id)
            ])
            order.bom_request_count = len(bom_requests)
            logging.info(f" Custom Code: [BOM] Order {order.name}: Found {order.bom_request_count} BOM requests.")

    def _compute_rel_service_id(self):
        for order in self:
            services = order.order_line.mapped('rel_service')
            service_ids = services.ids
            order.x_rel_service_id = service_ids[0] if len(set(service_ids)) == 1 else False

    def _inverse_rel_service_id(self):
        for order in self:
            if order.x_rel_service_id:
                # Optional: update all order lines to use selected service
                for order in self:
                    if order.x_rel_service_id:
                        for line in order.order_line:
                            if line.product_id and line.product_id.type == 'consu':
                                line.rel_service = order.x_rel_service_id.id
    def action_view_projects(self):
        kanban_view_id = self.env.ref('project.view_project_kanban').id
        projects = self.order_line.mapped("project_id")

        result = {
            "type": "ir.actions.act_window",
            "res_model": "project.project",
            "views": [[kanban_view_id, "kanban"], [False, "form"]],
            "domain": [("id", "in", projects.ids)],
            "context": {"create": False},
            "name": _("Projects"),
        }
        if len(self.project_ids) == 1:
            result['views'] = [(False, "form")]
            result['res_id'] = self.project_ids.id
        return result

    def action_view_bom_requests(self):
        """Open BOM Queue filtered by this sales order"""
        self.ensure_one()
        bom_requests = self.env['maeknit.bom.request'].search([
            ('sale_order_id', '=', self.id)
        ])

        result = {
            "type": "ir.actions.act_window",
            "res_model": "maeknit.bom.request",
            "view_mode": "list,form",
            "domain": [("id", "in", bom_requests.ids)],
            "context": {
                "create": False,
                "default_sale_order_id": self.id,
            },
            "name": _("BOM Requests"),
        }

        # If only one BOM request, open it directly
        if len(bom_requests) == 1:
            result['view_mode'] = "form"
            result['res_id'] = bom_requests.id

        return result

    @api.depends('order_line.rel_service')
    def _compute_rel_services(self):
        for order in self:
            service_names = set()
            service_ids = set()
            for line in order.order_line:
                if line.rel_service:
                    service_names.add(line.rel_service.name)
                    service_ids.add(line.rel_service.id)

            if len(service_names) > 1:
                raise ValidationError(
                    _("Only one Related Service is allowed per Sale Order. Found: %s")
                    % ", ".join(service_names)
                )

            order.x_rel_services = ", ".join(service_names) if service_names else ""
            logging.info(f" Custom Code: [STEP 2] Order {order.name}: Found {order.x_rel_services} related services.")
            # keep x_rel_service_id in sync if clear/unique
            if len(service_ids) == 1:
                order.x_rel_service_id = list(service_ids)[0]
                logging.info(f" Custom Code: [STEP 3] Order {order.name}: Set x_rel_service_id to {order.x_rel_service_id}.")
            elif not service_ids and not order.x_rel_service_id:
                order.x_rel_service_id = False
                logging.info(f" Custom Code: [STEP 4] Order {order.name}: Set x_rel_service_id to False.")
            # If multiple services, leave x_rel_service_id as is (user may correct)

    def action_open_opportunity(self):
        self.ensure_one()
        if not self.opportunity_id:
            return
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "view_mode": "form",
            "res_id": self.opportunity_id.id,
            "target": "current",
            "name": _("Opportunity"),
        }

    @api.depends('order_line.style_family')
    def _compute_quoted_style_families(self):
        for order in self:
            unique_style_families = set()
            for line in order.order_line:
                if line.style_family:
                    unique_style_families.add(line.style_family)
            order.x_quoted_style_families = ", ".join(sorted(list(unique_style_families)))

    # Override opportunity_id to sync with lead_id when appropriate
    @api.onchange('lead_id')
    def _onchange_lead_id(self):
        if self.lead_id and self.lead_id.type == 'opportunity':
            self.opportunity_id = self.lead_id
        # Clear selected leads when parent lead changes
        self.selected_child_leads = [(5, 0, 0)] # Clear all
        if self.lead_id and hasattr(self.lead_id, 'x_service_id') and self.lead_id.x_service_id:
            self.x_rel_service_id = self.lead_id.x_service_id
            self.x_service_from_crm = True

    @api.onchange('opportunity_id')
    def _onchange_opportunity_id(self):

        if self.opportunity_id:
            self.lead_id = self.opportunity_id
        # Clear selected leads when opportunity changes
        self.selected_child_leads = [(5, 0, 0)] # Clear all
        if self.opportunity_id and hasattr(self.opportunity_id, 'x_service_id') and self.opportunity_id.x_service_id:
            self.x_rel_service_id = self.opportunity_id.x_service_id
            self.x_service_from_crm = True

    @api.onchange('x_rel_service_id')
    def _onchange_x_rel_service_id(self):
        """Cascade service selection to all order lines and, for Swatch Service, add a service line."""
        ProductTemplate = self.env['product.template']

        if not self.x_rel_service_id:
            return

        # Find the Swatch Service template
        swatch_service_tmpl = ProductTemplate.search([
            ('name', '=', 'Swatch Service'),
            ('type', '=', 'service')
        ], limit=1)
        grading_service_tmpl = ProductTemplate.search([
            ('name', '=', 'Grading Service'),
            ('type', '=', 'service')
        ], limit=1)

        if self.x_rel_service_id and self.x_rel_service_id.product_tmpl_id.id == swatch_service_tmpl.id:
            logging.info(" Custom Code:[SO] Swatch Service selected — initializing swatch flow")

            # Create service line if not already
            existing_service_line = self.order_line.filtered(
                lambda l: l.product_id.product_tmpl_id == swatch_service_tmpl
            )

            # Create first swatch product (if not exists)
            ProductCategory = self.env['product.category']
            swatch_category = ProductCategory.search([('name', '=', 'Swatch')], limit=1)
            if not swatch_category:
                swatch_category = ProductCategory.create({'name': 'Swatch'})

            style_seq = self.env['crm.lead'].get_next_swatch_style_sequence()
            swatch_name = f"Swatch 1"
            existing_swatch = ProductTemplate.search([
                                ('name', '=', swatch_name),
                                ('type', '=', 'consu'),
                                ('categ_id', '=', swatch_category.id)
                            ], limit=1)
            if not existing_swatch:
                swatch_product = ProductTemplate.create({
                    'name': swatch_name,
                    'type': 'consu',
                    'categ_id': swatch_category.id,
                    'style_family': style_seq,
                })
                logging.info(f" Custom Code: [SO] Created first swatch product: {swatch_name} ({style_seq})")

                self.order_line += self.env['sale.order.line'].new({
                    'product_id': swatch_product.product_variant_id.id,
                    'product_uom_qty': 1.0,
                    'price_unit': 0.0,
                    'rel_service': self.x_rel_service_id.id,
                    'style_family': style_seq,
                })

            # Sync x_swatch_data + CRM
            swatch_json = {
                "items": [{"tempId": -1, "name": swatch_name, "styleCode": style_seq}],
                "selectedItems": [-1],
                "nextSwatchNumber": 2,
                "servicePrice": 250
            }
            self.x_swatch_data = json.dumps(swatch_json)

            if self.lead_id:
                self.lead_id.write({
                    "x_swatch_data": json.dumps(swatch_json),
                    "x_include_swatch_in_quote": True
                })
                logging.info(f" Custom Code: [SO] Updated CRM Lead {self.lead_id.id} with swatch_data")

        elif self.x_rel_service_id and self.x_rel_service_id.product_tmpl_id.id == grading_service_tmpl.id:
            logging.info(" Custom Code:[SO] Grading Service selected — initializing grading flow")

            existing_grading_line = self.order_line.filtered(
                lambda l: l.product_id.product_tmpl_id == grading_service_tmpl
            )

            if not existing_grading_line:
                self.order_line += self.env['sale.order.line'].new({
                    'product_id': grading_service_tmpl.product_variant_id.id,
                    'product_uom_qty': 1.0,
                    'price_unit': 300.0,  # Default grading price
                    'rel_service': self.x_rel_service_id.id,
                    'style_family': self.lead_id.style_family or "grading",
                })
                logging.info(" Custom Code:[SO] Added default grading service line")

            # Initialize x_grading_data structure
            grading_json = {
                "items": [],
                "selectedItems": [],
                "nextGradingNumber": 1,
                "pricePerGrade": 300
            }
            self.x_grading_data = json.dumps(grading_json)

            if self.lead_id:
                self.lead_id.write({
                    "x_grading_data": json.dumps(grading_json),
                    "x_include_grading_in_quote": True
                })
                logging.info(f" Custom Code: [SO] Updated CRM Lead {self.lead_id.id} with grading_data")

        # Cascade service to consumables
        for line in self.order_line:
            if line.product_id and line.product_id.type == 'consu':
                line.rel_service = self.x_rel_service_id

    def _is_internal_factory(self):
        """Check whether the SO should use the MO flow."""
        self.ensure_one()
        if not self.factory_id:
            return False
        factory_name = (self.factory_id.name or '').strip().upper()
        return factory_name in self._MO_BUTTON_FACTORIES

    def _get_target_company(self):
        """Map factory to the correct Odoo company for manufacturing/procurement."""
        self.ensure_one()
        return self.company_id

    def action_generate_all_mos(self, lines=None, qty_map=None):
        """Generate MOs or RFQs for this Sale Order based on factory.

        - direct_mo_mode (Development / Swatch / Production / Grading-UK):
          Creates MOs directly from consumable SO lines, mirroring what Odoo
          does on order confirmation.  Works in any SO state (draft/quotation
          or confirmed) and is fully idempotent.
        - Other services: creates MOs from pending BOM Requests (existing flow).
        - If 'lines' is passed (e.g. from Replenishment wizard), we ensure
          BOM Requests exist for these lines before proceeding.
        """
        self.ensure_one()


        is_internal = self._is_internal_factory()

        if hasattr(self, '_create_subcontracting_boms'):
            self._create_subcontracting_boms()

        # Ensure subcontracting BOMs are synced before any generation (especially for RFQs)
        if not is_internal:
            po = self._generate_direct_rfqs(lines=lines, qty_map=qty_map)
            if not po:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Nothing to do'),
                        'message': _('All eligible lines already have an RFQ or no eligible lines found.'),
                        'type': 'warning',
                        'sticky': False,
                    },
                }
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'current',
                'name': _('Sales Order'),
            }

        # ── BOM-request flow (non-direct_mo_mode) ──────────────────────────
        if self.direct_mo_mode:
            return self._generate_direct_mos_from_lines(lines=lines, qty_map=qty_map)

        # 1. ── Pre-process targeted lines (silent "Generate BOM Queue") ──
        if lines is not None:
            for line in lines:
                categ_name = (line.product_id.categ_id.name or '').lower()
                if line.product_id.type == 'consu' and categ_name in ('garment', 'swatch'):
                    if not self._already_processed(line):
                        qty_override = qty_map.get(line.id) if qty_map else None
                        try:
                            if categ_name == 'swatch':
                                self._process_swatch_line(line, qty_override=qty_override)
                            elif self.x_rel_service_id and self.x_rel_service_id.name == "Production Service":
                                self._process_production_line(line, qty_override=qty_override)
                            else:
                                self._process_garment_line(line, qty_override=qty_override)
                        except Exception as e:
                            logging.error("Failed to pre-process line %s during MO gen: %s", line.id, e)

        # 2. ── BOM-request flow (non-direct_mo_mode) ──────────────────────────
        target_lines = lines if lines is not None else self.order_line
        pending = self.bom_request_ids.filtered(lambda r: not r.mo_id and (lines is None or r.sale_order_line_id.id in target_lines.ids))
        if not pending:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Nothing to do'),
                    'message': _('All BOM Requests already have a Manufacturing Order.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        created = 0
        failed = []
        target_company = self._get_target_company()
        for req in pending:
            try:
                if is_internal:
                    # 1) Generate MO
                    req.action_generate_mo()
                else:
                    req.action_generate_rfq()
                created += 1
            except Exception as e:
                logging.error("Generate MO failed for BOM Request %s: %s", req.name, e)
                failed.append("%s: %s" % (req.name, str(e)))
        if failed:
            raise ValidationError(
                _("Generated %d MO(s). The following failed:\n\n%s") % (created, '\n'.join(failed))
            )
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'name': _('Sales Order'),
        }

    def _generate_direct_rfqs(self, lines=None, qty_map=None):
        """Generate RFQs directly from SO lines for external factories."""
        self.ensure_one()
        PurchaseOrder = self.env['purchase.order']
        PurchaseOrderLine = self.env['purchase.order.line']

        if not self.factory_id:
            return False

        target_lines = lines if lines is not None else self.order_line

        # Only process consumable Garment/Swatch lines
        valid_lines = target_lines.filtered(lambda l:
                                            l.product_id and l.product_id.type == 'consu' and
                                            (l.product_id.categ_id.name or '').lower() in ('garment', 'swatch')
                                            )

        if not valid_lines:
            return False

        # Find or Create Purchase Order
        po = PurchaseOrder.search([
            ('origin', '=', self.name),
            ('partner_id', '=', self.factory_id.id),
            ('state', '=', 'draft'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        if not po:
            po_vals = {
                'partner_id': self.factory_id.id,
                'origin': self.name,
                'company_id': self.company_id.id,
                'date_order': fields.Datetime.now(),
            }
            # Handle picking type and dest address if available
            if hasattr(self, 'fg_shipping_destinations'):
                po_vals['picking_type_id'] = self.fg_shipping_destinations.id
            else:
                po_vals['picking_type_id'] = self._get_picking_type(self.company_id.id).id

            po_vals['dest_address_id'] = self.partner_id.id
            po = PurchaseOrder.create(po_vals)

        created_po_lines = 0
        for line in valid_lines:
            # Idempotency: skip if this exact product is already in the PO
            existing_pol = po.order_line.filtered(lambda pol: pol.product_id == line.product_id)
            if existing_pol:
                continue

            qty = qty_map.get(line.id) if qty_map else line.product_uom_qty

            PurchaseOrderLine.create({
                'order_id': po.id,
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_qty': qty,
                'product_uom': line.product_uom.id,
                'price_unit': line.product_id.standard_price or 0.0,
                'date_planned': fields.Datetime.now(),
            })
            created_po_lines += 1

        return po if created_po_lines > 0 or (po and po.order_line) else False

    def _generate_direct_mos_from_lines(self, lines=None, qty_map=None):
        """Process SO lines and immediately generate MOs — identical to action_confirm's MO logic.

        Calls the same _process_*_line helpers that action_confirm uses, so:
        - BOM Requests are created (carrying sample, project, task, etc.)
        - MOs are generated from those BOM Requests right away
        - When the SO is confirmed later, _already_processed() finds existing
          BOM Requests and skips those lines → zero duplicate MOs or BOM Requests.

        Works regardless of SO state (draft / quotation / confirmed).
        """
        self.ensure_one()

        service_name_str = (self.x_rel_service_id.name or '') if self.x_rel_service_id else ''
        service_lower = service_name_str.strip().lower()
        created_bom_requests = self.env['maeknit.bom.request']

        target_lines = lines if lines is not None else self.order_line
        for line in target_lines:
            qty_override = qty_map.get(line.id) if qty_map else None
            try:
                if service_name_str == "Swatch Service":
                    req = self._process_swatch_line(line, qty_override=qty_override)
                elif service_name_str == "Production Service":
                    # Production lines create MOs directly inside _process_production_line;
                    # idempotency is via line.project_id (set inside that method).
                    self._process_production_line(line, qty_override=qty_override)
                    req = None
                else:
                    req = self._process_garment_line(line, qty_override=qty_override)
                if req:
                    created_bom_requests |= req
            except Exception as e:
                logging.error("Custom Code: [GEN-MO] Error processing line %s: %s", line.id, e)
                raise

        if not created_bom_requests:
            # Production Service creates MOs directly — count them by origin.
            direct_mos = self.env['mrp.production'].search([('origin', '=', self.name)])
            if direct_mos:
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'sale.order',
                    'res_id': self.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'name': _('Sales Order'),
                }
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Nothing to do'),
                    'message': _('All lines are already processed. No new BOM Requests or MOs created.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        # Generate MOs from the newly created BOM Requests

        # Ensure subcontracting BOMs are synced for direct mode too
        if hasattr(self, '_create_subcontracting_boms'):
            self._create_subcontracting_boms()

        is_internal = self._is_internal_factory()
        target_company = self._get_target_company()
        # Generate MOs or RFQs from the newly created BOM Requests
        if is_internal:
            created_bom_requests.write({'company_id': target_company.id})
            created_bom_requests.with_context(skip_component_validation=True).action_generate_mo()
        else:
            created_bom_requests.action_generate_rfq()

        # Sync rel_service and sample — mirrors action_confirm post-processing
        for req in created_bom_requests:
            if not req.mo_id:
                continue
            if self.x_rel_service_id:
                req.mo_id.rel_service = self.x_rel_service_id
            if (service_lower == 'development service'
                    and req.sale_order_line_id
                    and req.sale_order_line_id.sample):
                req.mo_id.sample = req.sale_order_line_id.sample

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'name': _('Sales Order'),
        }

    def action_generate_bom_queue(self):
        self.ensure_one()
        self.button_generate_bom_queue_visible = False
        for line in self.order_line:
            try:
                if self.x_rel_service_id and self.x_rel_service_id.name == "Swatch Service":
                    self._process_swatch_line(line)
                elif self.x_rel_service_id and self.x_rel_service_id.name == "Production Service":
                    self._process_production_line(line)
                else:
                    self._process_garment_line(line)
            except Exception as e:
                logging.error("Error processing line %s: %s", line.id, e)
                raise

    def action_generate_production_mos(self):
        """Generate Manufacturing Orders directly for Production Service garment lines."""
        self.ensure_one()

        if not self.x_rel_service_id or self.x_rel_service_id.name != "Production Service":
            raise ValidationError(_("This action is only available for Production Service orders."))

        created_mos = self.env['mrp.production']

        for line in self.order_line:
            # Skip if not a garment product
            if not line.product_id or line.product_id.type != 'consu':
                continue
            if not getattr(line.product_id, 'categ_id', False):
                continue
            if (line.product_id.categ_id.name or '').lower() != 'garment':
                continue

            # Check if MO already exists for this line
            existing_mo = self.env['mrp.production'].search([
                ('origin', '=', self.name),
                ('product_id', '=', line.product_id.id),
            ], limit=1)

            if existing_mo:
                logging.info("MO already exists for line %s: %s", line.id, existing_mo.name)
                continue

            # Search for BOM
            bom_id = self.env['mrp.bom'].search([('product_id', '=', line.product_id.id)], limit=1)

            # Prepare MO values
            mo_vals = {
                'product_id': line.product_id.id,
                'product_qty': line.product_uom_qty,
                'bom_id': bom_id.id if bom_id else False,
                'rel_service': line.rel_service.id if line.rel_service else False,
                'origin': self.name,
                'user_id': self.user_id.id,
                'partner_id': self.partner_id.id,
            }

            # Get picking type
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'mrp_operation'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)

            if not picking_type:
                picking_type = self.env.ref('mrp.picking_type_manufacturing', raise_if_not_found=False)

            if not picking_type:
                raise ValidationError(_("No Manufacturing picking type found for company %s.") % self.company_id.display_name)

            # Set picking type and locations
            mo_vals.update({
                'picking_type_id': picking_type.id,
                'location_src_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
            })

            # Create MO
            mo = self.env['mrp.production'].with_context(skip_bom_request_cad_sync=True).create(mo_vals)
            created_mos |= mo
            logging.info("Created MO %s for line %s (%s)", mo.name, line.id, line.product_id.display_name)

        if created_mos:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Manufacturing Orders Created'),
                    'message': _('%d Manufacturing Order(s) created successfully.') % len(created_mos),
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No MOs Created'),
                    'message': _('No new Manufacturing Orders were created. They may already exist or no garment lines found.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

    def action_add_next_swatch(self):
        """Add next swatch and sync with CRM"""
        self.ensure_one()
        if not self.x_rel_service_id or self.x_rel_service_id.name != "Swatch Service":
            raise ValidationError(_("Swatch Service must be selected first."))

        ProductTemplate = self.env['product.template']
        ProductCategory = self.env['product.category']

        # Ensure Swatch category exists
        swatch_category = ProductCategory.search([('name', '=', 'Swatch')], limit=1)
        if not swatch_category:
            swatch_category = ProductCategory.create({'name': 'Swatch'})

        # Parse current swatch data (fallback to empty)
        data = {}
        try:
            data = json.loads(self.x_swatch_data or '{}')
        except Exception:
            data = {}

        # STEP 1 — Detect existing swatch numbers from SO lines
        existing_swatch_nums = []
        for line in self.order_line:
            if (
                line.product_id
                and line.product_id.product_tmpl_id.categ_id.name == 'Swatch'
                and line.product_id.product_tmpl_id.name.startswith('Swatch ')
            ):
                try:
                    num_part = int(line.product_id.product_tmpl_id.name.split('Swatch ')[1])
                    existing_swatch_nums.append(num_part)
                except Exception:
                    continue

        next_number = max(existing_swatch_nums) + 1 if existing_swatch_nums else 1

        # STEP 2 — Generate new style sequence
        style_seq = self.env['crm.lead'].get_next_swatch_style_sequence()
        swatch_name = f"Swatch {next_number}"

        # STEP 3 — Create product linked to CRM Lead and Client
        swatch_product = ProductTemplate.create({
            'name': swatch_name,
            'type': 'consu',
            'categ_id': swatch_category.id,
            'style_family': style_seq,
            'parent_project_id': self.lead_id.id if self.lead_id else False,  # Link to CRM Lead
            'product_category': 'swatch',  # Mark as swatch
            'brand_id': self.partner_id.id if self.partner_id else False,  # Copy client/brand
        })
        logging.info(f" Custom Code: [SO] Created next swatch: {swatch_name} ({style_seq}), linked to lead {self.lead_id.id if self.lead_id else 'None'}, client {self.partner_id.name if self.partner_id else 'None'}")

        # STEP 4 — Find existing swatch line to copy route from
        existing_swatch_line = self.order_line.filtered(
            lambda l: l.product_id.product_tmpl_id.categ_id.name == 'Swatch'
        )[:1]  # Get first swatch line if exists

        route_id = existing_swatch_line.route_id.id if existing_swatch_line and existing_swatch_line.route_id else False

        # STEP 5 — Add to SO lines (use create to save immediately for BOM processing)
        new_line = self.env['sale.order.line'].create({
            'order_id': self.id,
            'product_id': swatch_product.product_variant_id.id,
            'product_uom_qty': 1.0,
            'price_unit': 0.0,
            'rel_service': self.x_rel_service_id.id,
            'style_family': style_seq,
            'route_id': route_id,  # Copy route from existing swatch
        })

        logging.info(f" Custom Code: [SO] Copied route {route_id} from existing swatch line")

        # STEP 6 — Create BOM Request and MO for the new swatch
        try:
            is_internal = self._is_internal_factory()
            self._process_swatch_line(new_line)
            logging.info(f" Custom Code: [SO] Created BOM Request for {swatch_name}")

            # If in direct MO mode, generate MO immediately
            if self.direct_mo_mode:
                bom_request = self.env['maeknit.bom.request'].search([
                    ('sale_order_line_id', '=', new_line.id)
                ], limit=1)
                if bom_request:
                    if is_internal:
                        bom_request.with_context(skip_component_validation=True).action_generate_mo()
                        logging.info(
                            f" Custom Code: [SO] Generated MO for {swatch_name}: {bom_request.mo_id.name if bom_request.mo_id else 'None'}")
                        # Sync rel_service to the newly created MO
                        if bom_request.mo_id and self.x_rel_service_id:
                            bom_request.mo_id.rel_service = self.x_rel_service_id
                    else:
                        bom_request.action_generate_rfq()
                        logging.info(
                            f" Custom Code: [SO] Generated RFQ for {swatch_name}: {bom_request.purchase_order_id.name if bom_request.purchase_order_id else 'None'}")
        except Exception as e:
            logging.error(f" Custom Code: [SO] Failed to create BOM/MO for {swatch_name}: {e}")

        # STEP 7 — Update JSON + CRM
        new_item = {"tempId": -next_number, "name": swatch_name, "styleCode": style_seq}
        data.setdefault('items', []).append(new_item)
        data.setdefault('selectedItems', []).append(-next_number)
        data['nextSwatchNumber'] = next_number + 1
        self.x_swatch_data = json.dumps(data)

        if self.lead_id:
            self.lead_id.write({"x_swatch_data": json.dumps(data)})

        logging.info(f" Custom Code: [SO] Added {swatch_name} and synced CRM Lead {self.lead_id.id}")


    @api.depends('lead_id')
    def _compute_child_crm_leads_to_quote(self):
        """
        Compute the child CRM leads related to the current sale order's lead.
        Only show child leads that are not yet linked to a sales order.
        """
        for order in self:
            if order.lead_id and order.lead_id.child_ids:
                # Filter out child leads that are already linked to a sale order
                # or are already converted to a sale order
                existing_sale_orders = self.env['sale.order'].search([
                    ('opportunity_id', 'in', order.lead_id.child_ids.ids)
                ]).mapped('opportunity_id')
                available_child_leads = order.lead_id.child_ids - existing_sale_orders
                order.child_crm_leads_to_quote = available_child_leads
            else:
                order.child_crm_leads_to_quote = False

    def action_select_all_leads(self):
        """
        Select all available child leads for quote generation.
        """
        self.ensure_one()
        if self.child_crm_leads_to_quote:
            self.selected_child_leads = [(6, 0, self.child_crm_leads_to_quote.ids)]
        # Removed notification as per user request
        # No return statement to simply refresh the view

    def action_clear_selection(self):
        """
        Clear all selected child leads.
        """
        self.ensure_one()
        if self.selected_child_leads:
            self.selected_child_leads = [(5, 0, 0)]  # Clear all
        # Removed notification as per user request
        # No return statement to simply refresh the view

    def _get_service_product(self, name):
        ProductTemplate = self.env['product.template']
        pt = ProductTemplate.search([
            ('name', '=', name),
            ('type', '=', 'service')
        ], limit=1)
        if not pt:
            logging.info(" Custom Code:Service product '%s' not found.", name)
        return pt


    def _service_name_from_line(self, line):
        """Return a plain service name string from sale.order.line.rel_service (product.product)."""
        service_pp = line.rel_service
        if not service_pp:
            return ''
        # Prefer template name; fall back to display_name
        tmpl = service_pp.product_tmpl_id
        if tmpl and tmpl.name:
            return tmpl.name or ''
        return service_pp.display_name or service_pp.name or ''

    def _already_processed(self, line):
        """Idempotency guard: skip if project or a BOM Request already exists for this SO line."""
        if line.project_id:
            return True
        existing = self.env['maeknit.bom.request'].search([
            ('sale_order_line_id', '=', line.id)
        ], limit=1)
        return bool(existing)

    def _process_production_line(self, line, qty_override=None):
        # Preconditions
        if not line.product_id or line.product_id.type != 'consu':
            return
        if not getattr(line.product_id, 'categ_id', False):
            return
        if (line.product_id.categ_id.name or '').lower() != 'garment':
            return
        # The MO idempotency check is handled inside the manufacture-route block below.
        target_company = self._get_target_company()
        logging.info(" Custom Code:Processing garment line %s (%s)", line.id, line.product_id.display_name)
        service_name = (self._service_name_from_line(line) or '').lower()

        # Gather style_family and sample label
        style_family = line.style_family
        product_line = line.order_id.order_line.filtered(
            lambda l: l.product_id and l.product_id.type != 'service'
            and (not style_family or l.style_family == style_family)
        )[:1]

        ProductTemplate = self.env['product.template']
        linked_product = ProductTemplate.search([('style_family', '=', style_family)], limit=1)
        base_name = str(linked_product.name or line.product_id.display_name or "Unnamed")
        new_name = f"{base_name} - {line.rel_service.product_tmpl_id.name}" if line.rel_service else base_name

        service_name = self._service_name_from_line(line)
        tag_id = self._get_or_create_service_tag(service_name) if service_name else False

        if line.project_id:
            # Project already exists from a previous run — skip creation, just proceed to MO.
            logging.info(" Custom Code:Project already exists for line %s, skipping project/task creation.", line.id)
        else:
            project_vals = {
                'name': new_name,
                'company_id': target_company.id,
                'partner_id': line.order_id.partner_id.id,
                'tag_ids': [(6, 0, [tag_id])] if tag_id else [(6, 0, [])],
            }
            project = self.env['project.project'].with_company(target_company).sudo().create(project_vals)
            logging.info(" Custom Code:Created project %s (%s)", project.name, project.id)

            task_name = (product_line.product_id.name if product_line and product_line.product_id else line.name)
            project_task = self.env['project.task'].with_company(target_company).sudo().create({
                'name': task_name,
                'project_id': project.id,
                'company_id': target_company.id,
                'tag_ids': [(6, 0, [tag_id])] if tag_id else [(6, 0, [])],
            })
            logging.info(" Custom Code:Created project task %s (%s)", project_task.name, project_task.id)
            line.write({'project_id': project.id})
        logging.info('service_name: %s', service_name)
        logging.info(" Custom Code:Line route id %s ", line.route_id)
        route_name = self.env['stock.route'].search([('id', '=', line.route_id.id)]).name
        logging.info(" Custom Code:Line route name %s ", route_name)

        if route_name and 'manufacture' in route_name.lower():
            # Idempotency: skip if MOs already exist for this product on this SO
            existing_mos = self.env['mrp.production'].search([
                ('origin', '=', line.order_id.name),
                ('product_id', '=', line.product_id.id),
            ], limit=1)
            if existing_mos:
                logging.info(
                    " Custom Code: MOs already exist for product %s on SO %s — skipping.",
                    line.product_id.display_name, line.order_id.name,
                )
                return

            bom_id = self.env['mrp.bom'].search([('product_id', '=', line.product_id.id)], limit=1)
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'mrp_operation'),
                ('company_id', '=', target_company.id)
            ], limit=1)

            if not picking_type:
                picking_type = self.env.ref('mrp.picking_type_manufacturing', raise_if_not_found=False)

            if not picking_type:
                raise ValidationError(_("No Manufacturing picking type found for company %s.") % target_company.display_name)

            qty = int(line.product_uom_qty) or 1
            for _ in range(qty):
                mo_vals = {
                    'product_id': line.product_id.id,
                    'product_qty': 1.0,
                    'bom_id': bom_id.id,
                    'rel_service': line.rel_service.id if line.rel_service else False,
                    'origin': line.order_id.name,
                    'user_id': self.user_id.id,
                    'partner_id': self.partner_id.id,
                    'picking_type_id': picking_type.id,
                    'location_src_id': picking_type.default_location_src_id.id,
                    'location_dest_id': picking_type.default_location_dest_id.id,
                }
                self.env['mrp.production'].with_context(skip_bom_request_cad_sync=True).create(mo_vals)

    def _parse_size_colorway(self, name):
        name = (name or '').strip()

        size = ''
        colorway = ''

        # 1) $$...$$ tokens (can be multiple)
        tokens = re.findall(r'\$\$(.*?)\$\$', name)
        tokens = [t.strip() for t in tokens if t.strip()]

        # Heuristic: first token = size, second = colorway
        if tokens:
            size = tokens[0]
            if len(tokens) > 1:
                colorway = tokens[1]

        # 2) Fallback: (...) tokens if missing
        if not size or not colorway:
            parens = re.findall(r'$$(.*?)$$', name)
            parens = [p.strip() for p in parens if p.strip()]

            for p in parens:
                # Skip if already assigned
                if not size:
                    size = p
                    continue
                if not colorway:
                    colorway = p
                    break

        return size, colorway


    def _process_garment_line(self, line, qty_override=None):
        """
        Create Project (+first task), BOM, and BOM Request for a garment SO line.
        """
        # Preconditions
        if not line.product_id or line.product_id.type != 'consu':
            return
        if not getattr(line.product_id, 'categ_id', False):
            return
        if (line.product_id.categ_id.name or '').lower() != 'garment':
            return
        if self._already_processed(line):
            logging.info(" Custom Code:Skip line %s: already processed.", line.id)
            return
        target_company = self._get_target_company()
        logging.info(" Custom Code:Processing garment line %s (%s)", line.id, line.product_id.display_name)
        logging.info('line.name: %s', line.name)

        service_name = (self._service_name_from_line(line) or '').lower()

        # Gather style_family and sample label
        style_family = line.style_family
        product_line = line.order_id.order_line.filtered(
            lambda l: l.product_id and l.product_id.type != 'service'
            and (not style_family or l.style_family == style_family)
        )[:1]
        sample_label = (product_line.sample or line.sample or "Sample")

        ProductTemplate = self.env['product.template']
        linked_product = ProductTemplate.search([('style_family', '=', style_family)], limit=1)
        base_name = str(linked_product.name or line.product_id.display_name or "Unnamed")
        new_name = f"{base_name} - {line.rel_service.product_tmpl_id.name}" if line.rel_service else base_name

        service_name = self._service_name_from_line(line)
        tag_id = self._get_or_create_service_tag(service_name) if service_name else False

        vals = {
            'name': new_name,
            'company_id': target_company.id,
            'partner_id': line.order_id.partner_id.id,
            'tag_ids': [(6, 0, [tag_id])] if tag_id else [(6, 0, [])],
        }
        project = self.env['project.project'].with_company(target_company).sudo().create(vals)
        logging.info(" Custom Code:Created project %s (%s)", project.name, project.id)

        task_name = (product_line.product_id.name if product_line and product_line.product_id else line.name) + " - " + sample_label
        project_task = self.env['project.task'].with_company(target_company).sudo().create({
            'name': task_name,
            'project_id': project.id,
            'company_id': target_company.id,
            'tag_ids': [(6, 0, [tag_id])] if tag_id else [(6, 0, [])],
        })
        logging.info(" Custom Code:Created project task %s (%s)", project_task.name, project_task.id)
        line.write({'project_id': project.id})
        logging.info('service_name: %s', service_name)
        bom_request = self.env['maeknit.bom.request']
        # 2) Create BOM/BOM Request branches
        try:
            if 'grading' not in service_name.lower():
                logging.info(" Custom Code:Non-grading service detected: %s", service_name)
                # Non-grading: Development/Reverse/etc.

                # Find attribute value "Sample 1"
                sample_1_attr = self.env['product.attribute.value'].search([('name', '=', 'Sample 1')], limit=1)

                bom_vals = {
                    'product_tmpl_id': line.product_id.product_tmpl_id.id,
                    'product_id': line.product_id.id,
                    'product_qty': 1.0,
                    'type': 'normal',
                    'is_garment_bom': True,
                    'order_date': fields.Date.today(),
                    'company_id': target_company.id,
                    'partner_id': self.partner_id.id,
                    'rel_service': line.rel_service.id if line.rel_service else False,
                }

                bom = self.env['mrp.bom'].with_company(target_company).sudo().create(bom_vals)
                logging.info(" Custom Code:Created BOM %s", bom.id)

                bom_req_base_vals = {
                    'product_tmpl_id': line.product_id.product_tmpl_id.id,
                    'product_id': line.product_id.id,
                    'rel_service': line.rel_service.id if line.rel_service else False,
                    'sale_order_id': self.id,
                    'sale_order_line_id': line.id,
                    'bom_id': bom.id,
                    'project_task_id': project_task.id,
                    'product_qty': 1.0,
                    'company_id': target_company.id,
                    'partner_id': self.partner_id.id,
                    'notes': f'BOM Request for {line.product_id.name} from Sales Order {self.name}',
                }
                bom_req_base_vals.pop('sample', None)

                qty = int(qty_override if qty_override is not None else line.product_uom_qty) or 1
                bom_request = self.env['maeknit.bom.request']
                for _ in range(qty):
                    req = self.env['maeknit.bom.request'].with_company(target_company).sudo().create(bom_req_base_vals)
                    bom_request |= req
                    logging.info(" Custom Code:Created BOM Request %s", req.name)

            else:
                # Grading branch
                logging.info(" Custom Code:Grading service detected: %s", service_name)
                original_pt = line.product_id.product_tmpl_id
                price_unit_str = line.price_unit
                name = str(line.name or '')
                size, colorway = self._parse_size_colorway(name)
                logging.info('Parsed size: %s, colorway: %s from line name: %s', size, colorway, name)
                if not size:
                    size = str(line.size or '')
                if not colorway:
                    colorway = ('N/A')
                # Now pass both
                bom, graded_pp = self._create_or_get_grading_bom_and_variant(
                    original_pt,
                    size,
                    price_unit_str,
                    colorway,
                )

                if not graded_pp or not bom:
                    error_msg = f"Failed to create graded product variant for {original_pt.name}"
                    if size:
                        error_msg += f" (Size: {size})"
                    if colorway:
                        error_msg += f" (Colorway: {colorway})"
                    logging.error(error_msg)
                    raise ValidationError(_(error_msg + ". Please check the product configuration and try again."))
                logging.info(" Custom Code:Using graded product %s (%s) and BOM %s", graded_pp.name, graded_pp.id, bom.id)
                try:
                    line.product_id = graded_pp.id
                    if colorway != 'N/A':
                        line.name = graded_pp.name + "(" + size + ") - Colorway: " + colorway
                    else:
                        line.name = graded_pp.name + "(" + size + ")"
                except Exception as e:
                    logging.error("Failed to update line %s with graded product: %s", line.id, e)
                size_value = False
                if size:
                    ProductAttribute = self.env['product.attribute']
                    ProductAttributeValue = self.env['product.attribute.value']

                    size_attr = ProductAttribute.search([('name', '=', 'Size')], limit=1)
                    if not size_attr:
                        size_attr = ProductAttribute.create({'name': 'Size', 'display_type': 'select'})

                    size_value = ProductAttributeValue.search([
                        ('attribute_id', '=', size_attr.id),
                        ('name', '=', size)
                    ], limit=1)
                    if not size_value:
                        size_value = ProductAttributeValue.create({
                            'attribute_id': size_attr.id,
                            'name': size
                        })
                logging.info('size_value: %s', size_value)

                bom_req_vals = {
                    'product_tmpl_id': graded_pp.product_tmpl_id.id,
                    'product_id': graded_pp.id,
                    'size_id': size_value.id if size_value else False,
                    'rel_service': line.rel_service.id if line.rel_service else False,
                    'sale_order_id': self.id,
                    'sale_order_line_id': line.id,
                    'bom_id': bom.id,
                    'product_qty': 1.0,
                    'company_id': self.company_id.id,
                    'partner_id': self.partner_id.id,
                    'notes': f'BOM Request for {graded_pp.name} from Sales Order {self.name}',
                }
                # sample is auto-computed from BOM version (related field)
                bom_req_vals.pop('sample', None)
                logging.info(" Custom Code:Creating Grading BOM Request with vals: %s", bom_req_vals)
                grading_qty = int(line.product_uom_qty) or 1
                bom_request = self.env['maeknit.bom.request']
                for _ in range(grading_qty):
                    req = self.env['maeknit.bom.request'].create(bom_req_vals)
                    bom_request |= req
                    logging.info(" Custom Code:Created Grading BOM Request %s", req.name)

        except Exception as e:
            logging.error("Error creating BOM/BOM Request for line %s: %s", line.id, e)
            raise
        return bom_request
    def _get_or_create_garment_product_for_lead(self, lead, garment_category=None, default_style_family='unnamed-project'):
        """Return a product.template for this lead in the Garment category."""
        ProductTemplate = self.env['product.template']
        categ_id = garment_category.id if garment_category else False

        name = lead.name or "Unnamed Project"
        style_family = lead.style_family or default_style_family

        domain = [('name', '=', name)]
        if categ_id:
            domain.append(('categ_id', '=', categ_id))

        existing = ProductTemplate.search(domain, limit=1)
        if existing:
            return existing

        # Create a minimal Garment product.template if not found
        vals = {
            'name': name,
            'type': 'consu',
            'style_family': style_family,
        }
        if categ_id:
            vals['categ_id'] = categ_id
        pt = ProductTemplate.create(vals)
        logging.info(" Custom Code:Created garment product.template %s for lead %s", pt.id, lead.id)
        return pt

    def action_generate_quote_lines(self):
        """
        New version: generate SO lines for selected child leads as Garment items,
        attach rel_service to Development Service variant, compute style_family,
        and set price using development_prices or expected revenue.
        """
        self.ensure_one()

        selected_child_leads = self.selected_child_leads
        if not selected_child_leads:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Warning'),
                    'message': _('Please select at least one child lead to generate quote lines.'),
                    'type': 'warning',
                }
            }

        development_prices = self.env.context.get('development_prices', {}) or {}
        garment_category = self.env['product.category'].search([('name', '=', 'Garment')], limit=1)


        def _get_service(name):
            pt = self.env['product.template'].search([('name', '=', name), ('type', '=', 'service')], limit=1)
            return pt

        dev_service_product = _get_service('Development Service')
        swatch_service_product = _get_service('Swatch Service')
        grading_service_product = _get_service('Grading Service')

        existing_ids = set(self.order_line.ids)
        new_lines = []
        seq_base = (len(self.order_line) + 1) * 10

        for idx, child_lead in enumerate(selected_child_leads, start=0):
            # Create or get garment template for the lead
            garment_product = self._get_or_create_garment_product_for_lead(
                child_lead,
                garment_category=garment_category,
                default_style_family='unnamed-project'
            )

            style_family = garment_product.style_family or 'unnamed-project'

            parent_project_id = getattr(garment_product, 'parent_project_id', False)
            parent_key = str(parent_project_id.id) if getattr(parent_project_id, 'id', False) else None
            garment_price = float(development_prices.get(parent_key, 0.0)) if parent_key else 0.0

            dev_revenue = child_lead.expected_revenue or 0.0
            final_price_unit = garment_price if garment_price > 0.0 else (dev_revenue or 2000.0)

            rel_service_id = dev_service_product.product_variant_id.id if dev_service_product else False

            line_vals = {
                'order_id': self.id,
                'product_id': garment_product.product_variant_id.id,
                'product_uom_qty': 1.0,
                'price_unit': final_price_unit,
                'name': garment_product.name,
                'sample': 'Sample 1',
                'rel_service': rel_service_id,
                'style_family': style_family,
                'sequence': seq_base + idx * 10,
            }
            new_lines.append((0, 0, line_vals))
            logging.info(" Custom Code:Prepared SO line from lead %s -> %s", child_lead.id, line_vals)

        if not new_lines:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Info'),
                    'message': _('No lines were generated.'),
                    'type': 'info',
                }
            }

        # Write and capture created lines
        self.write({'order_line': new_lines})
        self.selected_child_leads = [(5, 0, 0)]

        created_lines = self.order_line.filtered(lambda l: l.id not in existing_ids)

        # Process created garment lines immediately (idempotent with confirmation step)
        for line in created_lines:
            try:
                self._process_garment_line(line)
            except Exception as e:
                logging.exception("Failed to post-process created line %s: %s", line.id, e)
                raise UserError(_("Failed post-processing for a created line: %s") % e)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'name': _('Sales Order'),
        }

    def _process_swatch_line(self, line, qty_override=None):
        """
        Create Swatch BOM Request for each Swatch product line.
        Light version — no grading or complex variants.
        """
        if not line.product_id or line.product_id.type != 'consu':
            return
        if not getattr(line.product_id, 'categ_id', False):
            return
        if (line.product_id.categ_id.name or '').lower() != 'swatch':
            return

        if self._already_processed(line) and qty_override is None:
            logging.info(" Custom Code:Skip swatch line %s: BOM Request already exists.", line.id)
            return

        service_name = self._service_name_from_line(line)
        tag_id = self._get_or_create_service_tag(service_name) if service_name else False
        target_company = self._get_target_company()
        logging.info(" Custom Code:[SWATCH] Processing swatch line %s (%s)", line.id, line.product_id.display_name)
        project = self.env['project.project'].with_company(target_company).sudo().create({
            'name': f"{line.product_id.name} - Swatch",
            'company_id': target_company.id,
            'partner_id': self.partner_id.id,
            'tag_ids': [(6, 0, [tag_id])] if tag_id else [(6, 0, [])],
        })

        logging.info(" Custom Code:[SWATCH] Created project %s for swatch %s", project.id, line.product_id.name)

        # Create corresponding project task
        task = self.env['project.task'].with_company(target_company).sudo().create({
            'name': f"Swatch Task - {line.product_id.name}",
            'project_id': project.id,
            'tag_ids': [(6, 0, [tag_id])] if tag_id else [(6, 0, [])],
        })

        # Create Swatch BOM (optional, keeps structure aligned)
        MrpBom = self.env['mrp.bom']
        bom_vals = {
            'product_tmpl_id': line.product_id.product_tmpl_id.id,
            'product_id': line.product_id.id,
            'product_qty': 1.0,
            'type': 'normal',
            'is_swatch_bom': True,
            'order_date': fields.Date.today(),
            'company_id': target_company.id,
            'partner_id': self.partner_id.id,
            'rel_service': line.rel_service.id if line.rel_service else False,
        }
        bom = MrpBom.with_company(target_company).sudo().create(bom_vals)
        logging.info(" Custom Code:[SWATCH] Created Swatch BOM %s", bom.id)

        # Create BOM Request(s) — one per unit of quantity
        bom_request_vals = {
            'product_tmpl_id': line.product_id.product_tmpl_id.id,
            'product_id': line.product_id.id,
            'sale_order_id': self.id,
            'sale_order_line_id': line.id,
            'bom_id': bom.id,
            'rel_service': line.rel_service.id if line.rel_service else False,
            'project_task_id': task.id,
            'product_qty': 1.0,
            'company_id': target_company.id,
            'partner_id': self.partner_id.id,
            'notes': f'Swatch BOM Request for {line.product_id.name} from SO {self.name}',
        }
        # sample is auto-computed from BOM version (related field)
        bom_request_vals.pop('sample', None)
        swatch_qty = int(qty_override if qty_override is not None else line.product_uom_qty) or 1
        bom_request = self.env['maeknit.bom.request']
        for _ in range(swatch_qty):
            req = self.env['maeknit.bom.request'].with_company(target_company).sudo().create(bom_request_vals)
            bom_request |= req
            logging.info(" Custom Code:[SWATCH] Created Swatch BOM Request %s", req.name)

        # Link project to SO line
        line.write({'project_id': project.id})

        return bom_request



    def action_confirm(self):
        """Override to create BOMs and BOM Requests for garment products and projects for related services."""
        logging.info(" Custom Code:Confirming Sale Order %s with %s lines", self.name, len(self.order_line))
        if self.env.context.get("skip_project_creation"):
            return super(SaleOrder, self).action_confirm()

        created_bom_requests = self.env['maeknit.bom.request']
        for line in self.order_line:
            try:
                if self.x_rel_service_id and self.x_rel_service_id.name == "Swatch Service":
                    req = self._process_swatch_line(line)
                elif self.x_rel_service_id and self.x_rel_service_id.name == "Production Service":
                    req = self._process_production_line(line)
                else:
                    req = self._process_garment_line(line)
                if req:
                    created_bom_requests |= req
            except Exception as e:
                logging.error("Error processing line %s during confirm: %s", line.id, e)
                raise

        if self.direct_mo_mode and created_bom_requests:
            is_internal = self._is_internal_factory()
            if is_internal:
                created_bom_requests.with_context(skip_component_validation=True).action_generate_mo()
            else:
                created_bom_requests.action_generate_rfq()
            service_name = (self.x_rel_service_id.name or '').strip().lower()
            for req in created_bom_requests:
                if not req.mo_id:
                    continue
                if self.x_rel_service_id:
                    req.mo_id.rel_service = self.x_rel_service_id
                # For development service, sync sample number from SO line as source of truth
                if service_name == 'development service' and req.sale_order_line_id and req.sale_order_line_id.sample:
                    req.mo_id.sample = req.sale_order_line_id.sample

        res = super(SaleOrder, self.with_context(skip_mo_creation=True)).action_confirm()
        return res


    def action_open_order(self):
        """Open the task form view in a new window."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.id,
            'view_mode': 'form',
            'name': self.name,
        }

    def _create_or_get_grading_bom_and_variant(self, product_template, size_string, price_per_grade, colorway_string = ''):
        """
        Helper method to create or get a specific graded product variant and its BOM.
        :param product_template: The original product.template record (e.g., "Sweater A").
        :param size_string: The size for grading (e.g., "S", "M", "L").
        :param price_per_grade: The price to set for this graded item.
        :return: The product.product record for the graded variant, or False if creation fails.
        """
        ProductAttribute = self.env['product.attribute']
        ProductAttributeValue = self.env['product.attribute.value']
        MrpBom = self.env['mrp.bom']
        logging.info('Creating or getting graded BOM and variant for %s, size %s, price %s, colorway %s', product_template.name, size_string, price_per_grade, colorway_string)
        # --------------------------------------------------------
        # SIZE ATTRIBUTE + VALUE
        # --------------------------------------------------------
        size_attribute = ProductAttribute.search([('name', '=', 'Size')], limit=1)
        if not size_attribute:
            size_attribute = ProductAttribute.create({
                'name': 'Size',
                'display_type': 'select'
            })

        size_value = ProductAttributeValue.search([
            ('attribute_id', '=', size_attribute.id),
            ('name', '=', size_string)
        ], limit=1)

        if not size_value:
            size_value = ProductAttributeValue.create({
                'attribute_id': size_attribute.id,
                'name': size_string
            })

        # --------------------------------------------------------
        # COLORWAY ATTRIBUTE + VALUE
        # --------------------------------------------------------
        colorway_value = False
        if colorway_string:
            colorway_attribute = ProductAttribute.search([('name', '=', 'Colorway')], limit=1)
            if not colorway_attribute:
                colorway_attribute = ProductAttribute.create({
                    'name': 'Colorway',
                    'display_type': 'select'
                })

            colorway_value = ProductAttributeValue.search([
                ('attribute_id', '=', colorway_attribute.id),
                ('name', '=', colorway_string)
            ], limit=1)

            if not colorway_value:
                colorway_value = ProductAttributeValue.create({
                    'attribute_id': colorway_attribute.id,
                    'name': colorway_string
                })

        # --------------------------------------------------------
        # CREATE OR GET VARIANT (size + colorway)
        # --------------------------------------------------------
        if colorway_value:
            logging.info(" Custom Code:Creating or getting specific garment variant for size %s and colorway %s", size_string, colorway_string)
            graded_variant = MrpBom._find_or_create_specific_garment_variant(
                product_template,
                colorway_value,
                size_value
            )
        else:
            logging.info(" Custom Code:Creating or getting generic garment variant for size %s", size_string)
            graded_variant = MrpBom._find_or_create_specific_garment_variant(
                    product_template,
                    colorway_value=colorway_value if colorway_value else None,
                    size_value=size_value
                )

        if not graded_variant:
            logging.error("Failed to create or find graded variant for size %s and colorway %s", size_string, colorway_string)
            return False, False

        # --------------------------------------------------------
        # BUILD THE DOMAIN FOR BOM SEARCH
        # --------------------------------------------------------
        bom_domain = [
            ('product_tmpl_id', '=', product_template.id),
            ('product_id', '=', graded_variant.id),
            ('is_grading_bom', '=', True),
            ('size_id', '=', size_value.id),
        ]

        # Only add this domain if colorway_value exists
        if colorway_value:
            bom_domain.append(('colorway_id', '=', colorway_value.id))

        bom = MrpBom.search(bom_domain, limit=1)

        # --------------------------------------------------------
        # CREATE OR UPDATE BOM
        # --------------------------------------------------------
        if not bom:
            bom_vals = {
                'product_tmpl_id': product_template.id,
                'product_id': graded_variant.id,
                'type': 'normal',
                'sample': 'Sample 1',
                'rel_service': self.x_rel_service_id.id,
                'is_grading_bom': True,
                'partner_id': self.partner_id.id,
                'grading_price_unit': price_per_grade,
                'size_id': size_value.id,
            }

            if colorway_value:
                bom_vals['colorway_id'] = colorway_value.id

            bom = MrpBom.create(bom_vals)

        else:
            if bom.grading_price_unit != price_per_grade:
                bom.write({'grading_price_unit': price_per_grade})

        bom._compute_total_cost()

        return bom, graded_variant

    def _get_or_create_service_tag(self, service_name):
        """Return a valid project.tag ID for the given service name."""
        ProjectTag = self.env['project.tags']
        tag_name = service_name.strip()

        tag = ProjectTag.search([('name', 'ilike', tag_name)], limit=1)
        if not tag or not tag.exists():
            tag = ProjectTag.create({'name': {'en_US': tag_name}})
            logging.info(f" Custom Code: [TAGS] Created new tag '{tag_name}' (ID {tag.id})")
        else:
            logging.info(f" Custom Code: [TAGS] Using existing tag '{tag_name}' (ID {tag.id})")
        return tag.id

    def _has_bom_request(self, line):
        return bool(self.env['maeknit.bom.request'].search([
            ('sale_order_line_id', '=', line.id)
        ], limit=1))

    def _auto_process_line_post_confirm(self, line):
        """Process garment/swatch lines added AFTER confirmation."""

        # Skip non-consumables
        if not line.product_id or line.product_id.type != 'consu':
            return

        # Skip if product has no category
        categ = line.product_id.categ_id
        if not categ:
            return

        cname = (categ.name or "").lower()

        # Skip if BOM request already exists
        if self.env['maeknit.bom.request'].search([('sale_order_line_id', '=', line.id)], limit=1):
            logging.info(" Custom Code:Line %s already has BOM Req – skipping", line.id)
            return

        # Garment
        if cname == "garment":
            logging.info(" Custom Code:Auto-processing GARMENT line %s after confirm", line.id)
            # self._process_garment_line(line)
            return

        # Swatch
        if cname == "swatch" and hasattr(self, "_process_swatch_line"):
            logging.info(" Custom Code:Auto-processing SWATCH line %s after confirm", line.id)
            # self._process_swatch_line(line)
            return

    def write(self, vals):
        """Override write to sync grading data back to CRM lead"""
        is_confirmed = self.state in ['sale', 'done']

        # Capture existing line IDs before write
        existing_line_ids = set(self.order_line.ids)

        res = super(SaleOrder, self).write(vals)


        if 'x_grading_data' in vals and self.lead_id:
            self.lead_id.write({'x_grading_data': vals['x_grading_data']})

        if not is_confirmed:
            return res

        # Detect newly added lines
        new_lines = self.order_line.filtered(lambda l: l.id not in existing_line_ids)

        for line in new_lines:
            try:
                self._auto_process_line_post_confirm(line)
            except Exception as e:
                logging.error("Error auto-processing new line %s: %s", line.id, e)
                raise UserError(f"Failed processing newly added line {line.id}: {e}")

        return res

    def action_add_grading_sizes(self):
        """Open wizard to add grading sizes for selected products"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Grading Sizes',
            'res_model': 'grading.size.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            }
        }

    def _create_grading_variants_from_data(self):
        """Create product variants and SO lines from grading data"""
        if not self.x_grading_data or not self.x_rel_service_id:
            return

        try:
            grading_data = json.loads(self.x_grading_data)
        except json.JSONDecodeError:
            logging.error("Failed to parse x_grading_data: %s", self.x_grading_data)
            return

        grading_items = grading_data.get('items', [])
        selected_items = grading_data.get('selectedItems', [])
        price_per_grade = grading_data.get('pricePerGrade', 300)

        # Get or create Size attribute
        ProductAttribute = self.env['product.attribute']
        ProductAttributeValue = self.env['product.attribute.value']

        size_attribute = ProductAttribute.search([('name', '=', 'Size')], limit=1)
        if not size_attribute:
            size_attribute = ProductAttribute.create({
                'name': 'Size',
                'display_type': 'select'
            })

        new_lines = []

        for item in grading_items:
            item_id = item.get('id') or item.get('tempId')
            if item_id not in selected_items:
                continue

            # Find the product template
            product_name = item.get('name')
            style_code = item.get('styleCode')
            sizes = item.get('sizes', [])

            # Search for existing product template
            ProductTemplate = self.env['product.template']
            product_template = ProductTemplate.search([
                ('name', '=', product_name)
            ], limit=1)

            if not product_template:
                # Create new product template
                garment_category = self.env['product.category'].search([
                    ('name', '=', 'Garment')
                ], limit=1)
                if not garment_category:
                    garment_category = self.env['product.category'].create({'name': 'Garment'})

                product_template = ProductTemplate.create({
                    'name': product_name,
                    'type': 'consu',
                    'categ_id': garment_category.id,
                    'style_family': style_code,
                })

            # Calculate total service price
            total_service_price = price_per_grade * len(sizes)

            # Add grading service line
            new_lines.append((0, 0, {
                'product_id': self.x_rel_service_id.id,
                'product_uom_qty': 1.0,
                'price_unit': total_service_price,
                'rel_service': self.x_rel_service_id.id,
                'style_family': style_code,
            }))

            # Create variant for each size
            for size_str in sizes:
                if not size_str.strip():
                    continue

                # Get or create size attribute value
                size_value = ProductAttributeValue.search([
                    ('attribute_id', '=', size_attribute.id),
                    ('name', '=', size_str.strip().upper())
                ], limit=1)

                if not size_value:
                    size_value = ProductAttributeValue.create({
                        'attribute_id': size_attribute.id,
                        'name': size_str.strip().upper()
                    })

                # Create or get variant
                logging.info('Size: %s', size_str.strip().upper())
                bom, graded_variant = self._create_or_get_grading_bom_and_variant(
                    product_template,
                    size_str.strip().upper(),
                    price_per_grade
                )

                # Add SO line for this size variant
                new_lines.append((0, 0, {
                    'product_id': graded_variant.id,
                    'product_uom_qty': 1.0,
                    'price_unit': 0,
                    'revision': 'Revision 1',
                    'rel_service': self.x_rel_service_id.id,
                    'style_family': style_code,
                    'size': size_str.strip().upper(),
                    'name': f'({size_str.strip().upper()})',
                }))

        if new_lines:
            self.write({'order_line': new_lines})

        if self.lead_id and self.x_grading_data:
            try:
                self.lead_id.write({'x_grading_data': self.x_grading_data})
                logging.info(f" Custom Code: [GRADING] Synced x_grading_data to CRM Lead {self.lead_id.id}")
            except Exception as e:
                logging.error(f"[GRADING] Failed syncing x_grading_data to CRM: {e}")

    @api.model_create_multi
    def create(self, vals_list):
        IrSequence = self.env['ir.sequence']

        for vals in vals_list:
            # Need a sequence-generated name if missing/placeholder
            need_seq = not vals.get('name') or vals['name'] in ('New', _('New'))

            if need_seq:
                # Compute sequence date in user tz if date_order provided
                seq_date = None
                if vals.get('date_order'):
                    dt = fields.Datetime.to_datetime(vals['date_order'])
                    # context_timestamp expects a recordset; self is fine
                    seq_date = fields.Datetime.context_timestamp(self, dt)

                # Ensure we pick the correct company sequence
                company_id = vals.get('company_id') or self.env.company.id

                vals['name'] = (
                    IrSequence.with_company(company_id)
                    .next_by_code('sale.order', sequence_date=seq_date)
                    or 'New'  # final fallback if sequence misconfigured
                )

        return super(SaleOrder, self).create(vals_list)

    def action_sync_so_variants(self):
        """Fix existing SO lines: parse size/colorway from name, link proper variant + BOM."""
        import re
        self.ensure_one()

        MrpBom = self.env['mrp.bom']
        Attribute = self.env['product.attribute']
        AttributeValue = self.env['product.attribute.value']
        StyleSize = self.env['style.size']
        StyleColorway = self.env['style.colorway']

        size_attr = Attribute.search([('name', '=', 'Size')], limit=1)
        colorway_attr = Attribute.search([('name', '=', 'Colorway')], limit=1)

        production_service = self.env['product.product'].search([
            ('name', '=', 'Production Service')
        ], limit=1)

        fixed = 0
        for line in self.order_line:
            tmpl = line.product_id.product_tmpl_id
            if not tmpl or tmpl.product_category != 'garment':
                continue

            # Already has a specific variant (has PTAVs) — just fill size/colorway fields
            ptavs = line.product_id.product_template_attribute_value_ids
            size_name = line.size
            colorway_name = line.colorway

            # If the SO line fields are blank, try to parse from the description
            if (not size_name or not colorway_name) and line.name:
                size_match = re.search(r'Size:\s*([^\-\n]+)', line.name)
                colorway_match = re.search(r'Colorway:\s*([^\-\n]+)', line.name)
                if size_match and not size_name:
                    size_name = size_match.group(1).strip()
                if colorway_match and not colorway_name:
                    colorway_name = colorway_match.group(1).strip()

            if not size_name or not colorway_name:
                continue  # not enough info to resolve

            # Get or create attribute values
            size_val = size_attr and AttributeValue.search([
                ('attribute_id', '=', size_attr.id), ('name', '=', size_name)
            ], limit=1)
            colorway_val = colorway_attr and AttributeValue.search([
                ('attribute_id', '=', colorway_attr.id), ('name', '=', colorway_name)
            ], limit=1)

            if not size_val or not colorway_val:
                continue  # attribute values don't exist yet — skip

            # Find or create the specific variant
            variant = MrpBom._find_or_create_specific_garment_variant(
                tmpl, colorway_val, size_val
            )
            if not variant:
                continue

            # Ensure BOM exists
            existing_bom = MrpBom.search([
                ('product_tmpl_id', '=', tmpl.id),
                ('colorway_id', '=', colorway_val.id),
                ('size_id', '=', size_val.id),
            ], limit=1)
            if not existing_bom:
                MrpBom.create({
                    'product_tmpl_id': tmpl.id,
                    'colorway_id': colorway_val.id,
                    'size_id': size_val.id,
                    'partner_id': self.partner_id.id if self.partner_id else False,
                    'rel_service': production_service.id if production_service else False,
                })
            else:
                update_vals = {}
                if not existing_bom.partner_id and self.partner_id:
                    update_vals['partner_id'] = self.partner_id.id
                if not existing_bom.rel_service and production_service:
                    update_vals['rel_service'] = production_service.id
                if update_vals:
                    existing_bom.write(update_vals)

            # Ensure style.size / style.colorway records exist
            if not StyleSize.search([('product_tmpl_id', '=', tmpl.id), ('size_id', '=', size_val.id)], limit=1):
                StyleSize.create({'product_tmpl_id': tmpl.id, 'size_id': size_val.id, 'active': True})
            if not StyleColorway.search([('product_tmpl_id', '=', tmpl.id), ('colorway_id', '=', colorway_val.id)], limit=1):
                StyleColorway.create({'product_tmpl_id': tmpl.id, 'colorway_id': colorway_val.id, 'active': True})

            # Fill blank size/colorway fields (safe on confirmed orders)
            # product_id is intentionally not changed — confirmed SO lines block it
            update_vals = {}
            if not line.size:
                update_vals['size'] = size_name
            if not line.colorway:
                update_vals['colorway'] = colorway_name
            if update_vals:
                line.write(update_vals)

            fixed += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Variants Synced',
                'message': f'{fixed} order line(s) updated with specific variants.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_open_variant_wizard(self):
        """Open the Add Variants wizard, pre-filtered to garment products on this SO."""
        self.ensure_one()

        # Collect unique garment product templates from order lines
        garment_templates = self.order_line.mapped('product_id.product_tmpl_id').filtered(
            lambda t: t.product_category == 'garment'
        )

        if not garment_templates:
            raise UserError("No garment products found on this Sales Order.")

        # Use the first garment product, or let the user pick if there are multiple
        product = garment_templates[0]

        wizard = self.env['crm.lead.variant.wizard'].create({
            'product_id': product.id,
            'lead_id': self.lead_id.id if self.lead_id else False,
            'sale_order_id': self.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': f'Add Variants – {product.name}',
            'res_model': 'crm.lead.variant.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'so_garment_template_ids': garment_templates.ids,
            },
        }
