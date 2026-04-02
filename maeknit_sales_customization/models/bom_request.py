from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
from odoo import _
from markupsafe import Markup, escape
import re
from datetime import timedelta
import json
import time
import psycopg2
class BOMRequest(models.Model):
    _name = 'maeknit.bom.request'
    _description = 'BOM Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Add mail functionality
    _order = 'create_date desc'
    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='Bom Request New')
    
    # Sales Order fields
    sale_order_id = fields.Many2one('sale.order', string='Related Sales Order')
    sale_order_line_id = fields.Many2one('sale.order.line', string='Sales Order Line')
    partner_id = fields.Many2one('res.partner', string='Customer', store=True, required=True)
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user)
    active = fields.Boolean('Active', default=True)
    
    project_task_id = fields.Many2one("project.task", string="Main Project Task")
    delivery_count = fields.Integer(
        string='Delivery Orders',
        related='sale_order_id.delivery_count',
        store=False,
    )
    sub_task_ids = fields.One2many(
        "project.task",
        "bom_request_id",
        string="Sub Tasks",
    )
    yarn_orchestration_ids = fields.One2many(
        'maeknit.yarn.orchestration',
        'bom_request_id',
        string="Yarn Orchestration",
    )
    
    sub_task_count = fields.Integer(
        string='Sub Task Count',
        compute='_compute_sub_task_count'
    )

    sample = fields.Char(
        related='bom_id.sample',
        store=True,
        readonly=True,
    )
    revision = fields.Char(
        related='bom_id.revision',
        store=True,
        readonly=False,
    )
    total_weight_g = fields.Float(
    string="Total Weight (g)", compute="_compute_total_weight", store=True
    )
    total_weight_kg = fields.Float(
        string="Total Weight (kg)", compute="_compute_total_weight", store=True
    )
    
    gauge_id = fields.Many2one(
        'gauge.library',
        string='Gauge',
        required=True
     )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('ready_to_program', 'Ready to Program'),
        ('mo_confirmed', 'Ready to Knit'),
        ('produced', 'Sent to the Shopfloor'),
        ('ready_to_spec', 'Preship QC'),
        ('done', 'Done'),
        ('production_ready', 'Production Ready'),        
        ('cancelled', 'Cancelled'),
    ], default='draft', string='Status', tracking=True)
    
    operation_template_id = fields.Many2one(
        'maeknit.bom.operation.template',
        string='Operation Template',
        help='Select a template to auto-populate default operations.'
        )
    
    rnd_task_template_id = fields.Many2one(
        'maeknit.rnd.task.template',
        string='R&D Task Template',
        help='Select a template to auto-populate default R&D sub-tasks.'
    )

    
    eco_id = fields.Many2one('mrp.eco', string='Related ECO', ondelete='set null')
    stage_id = fields.Many2one('mrp.eco.stage', string='ECO Stage', tracking=True)
    
    # BOM Reference - This is the key field
    bom_id = fields.Many2one('mrp.bom', string='Referenced BOM')
    # in BOMRequest
    product_id = fields.Many2one(
        'product.product',
        related='bom_id.product_id',
        store=True,
        readonly=True,
    )
    mo_id = fields.Many2one('mrp.production', string='Manufacturing Order', readonly=True)
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)

    # === BOM FIELDS (Some related, some editable and synced) ===
    
    # Product fields (related, not directly editable on BOM Request)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', store=True)
    product_tmpl_name = fields.Char(
        string="Product Name",
        related="product_tmpl_id.name",
        readonly=False,
        store=False
    )

    product_qty = fields.Float(related='bom_id.product_qty', string='Quantity', store=True) # This is the BOM's product qty
    product_uom_id = fields.Many2one(related='bom_id.product_uom_id', string='Unit of Measure', store=True)
    allowed_product_ids = fields.Many2many(
        'product.product',
        compute='_compute_allowed_products',
        store=False
    )
    # BOM Type fields (related)
    rel_service = fields.Many2one('product.product', string='Related Service', store=True)
    is_garment_bom = fields.Boolean(related='bom_id.is_garment_bom', string='Is Garment BOM', store=True)
    is_development_bom = fields.Boolean(related='bom_id.is_development_bom', string='Is Development BOM', store=True)
    is_grading_bom = fields.Boolean(related='bom_id.is_grading_bom', string='Is Grading BOM', store=True)
    is_swatch_bom = fields.Boolean(related='bom_id.is_swatch_bom', string='Is Swatch BOM', store=True)
    is_reverse_bom = fields.Boolean(related='bom_id.is_reverse_bom', string='Is Reverse BOM', store=True)
    is_production_bom = fields.Boolean(related='bom_id.is_production_bom', string='Is Production BOM', store=True)
    
    structure_ids = fields.One2many('maeknit.structure.line', 'bom_request_id', string='Structure Lines')


    @api.onchange('structure_ids')
    def _onchange_structure_ids_autosave(self):
        origin = self._origin
        logging.info("Custom Code: Autosaving structure lines: ui_id=%s origin_id=%s", self.id, origin.id)

        if not origin or not origin.id:
            return {}

        try:
            # Track which origin IDs are still present in the UI
            current_origin_ids = {
                line._origin.id
                for line in self.structure_ids
                if line._origin and line._origin.id
            }

            commands = []

            # Issue delete commands for lines removed in the UI
            for orig_line in origin.structure_ids:
                if orig_line.id not in current_origin_ids:
                    commands.append((2, orig_line.id))

            # Update existing lines or create new ones
            mo_id = origin.mo_id.id if origin.mo_id else False
            for line in self.structure_ids:
                if not line.name:
                    continue
                vals = {
                    'name': line.name,
                    'sequence': line.sequence or 10,
                    'description': line.description or False,
                }
                if line._origin and line._origin.id:
                    # Update in place — preserves production_id on the existing record
                    commands.append((1, line._origin.id, vals))
                else:
                    # New line — link to MO if one exists (single source of truth)
                    if mo_id:
                        vals['production_id'] = mo_id
                    commands.append((0, 0, vals))

            if commands:
                origin.write({'structure_ids': commands})

            # Reload from DB so the UI shows saved rows (clears empty new row)
            self.structure_ids = origin.structure_ids
        except Exception as e:
            logging.error("Custom Code: Error autosaving structure lines: %s", str(e))

        return {}

    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        """Set BOM type flags based on product category when product is selected"""
        if self.product_tmpl_id and not self.bom_id:
            product_category = self.product_tmpl_id.product_category

            # Set temporary flags based on product category
            if product_category == 'garment':
                # Default to development BOM for garment products
                self.is_garment_bom = True
                self.is_development_bom = True
                self.is_swatch_bom = False
            elif product_category == 'swatch':
                self.is_swatch_bom = True
                self.is_garment_bom = False
                self.is_development_bom = False

            # Set product_id to default variant
            if self.product_tmpl_id.product_variant_ids:
                self.product_id = self.product_tmpl_id.product_variant_ids[0]

    @api.depends('is_garment_bom', 'is_grading_bom', 'is_swatch_bom', 'is_reverse_bom', 'is_production_bom', 'is_development_bom')
    def _compute_allowed_products(self):
        Product = self.env['product.product']
        for rec in self:
            domain = []

            if rec.is_garment_bom or rec.is_development_bom or rec.is_grading_bom or rec.is_reverse_bom or rec.is_production_bom:
                domain = [('product_tmpl_id.product_category', '=', 'garment')]
            elif rec.is_swatch_bom:
                domain = [('product_tmpl_id.product_category', '=', 'swatch')]

            rec.allowed_product_ids = Product.search(domain)
            
    style_colorway_ids = fields.Many2many('product.attribute.value',
                                         compute='_compute_style_colorway_ids',
                                         string='Available Colorways')
    style_size_ids = fields.Many2many('product.attribute.value',
                                      relation='bom_request_style_size_rel',
                                      compute='_compute_style_size_ids',
                                      string='Available Sizes')
    style_yarn_variant_ids = fields.Many2many('product.attribute.value',
                                                compute='_compute_style_yarn_variant_ids',
                                                string='Available Yarn Variants')
    
    colorway_id = fields.Many2one('product.attribute.value', string='Colorway', 
                                 domain="[('attribute_id.name', '=', 'Colorway')]")
    
    yarn_variant = fields.Many2one('product.attribute.value', string='Yarn Variant', 
                                 domain="[('attribute_id.name', '=', 'Yarn Variant')]")
    

    def _next_version_name(self, name):
        """
        Rules:
        - "ABC"        → "ABC v2"
        - "ABC v2"     → "ABC v3"
        - "ABC v10"    → "ABC v11"
        - "ABC (foo)"  → "ABC (foo) v2"
        """
        m = re.search(r"(.*?)(?:\s+v(\d+))$", name, re.IGNORECASE)
        if m:
            base = m.group(1).strip()
            version = int(m.group(2)) + 1
            return f"{base} v{version}"
        return f"{name} v2"

    def copy(self, default=None):
        """
        Block default Odoo duplication - users must use the custom duplicate button
        """
        self.ensure_one()

        # Check if this is being called from the custom duplicate wizard
        if not self.env.context.get('allow_bom_request_copy'):
            from odoo.exceptions import UserError
            raise UserError(_(
                "Please use the 'Duplicate' button to create a duplicate of this BOM Request.\n\n"
                "The custom duplicate wizard allows you to:\n"
                "• Select new colorway/size/yarn variant\n"
                "• Ensure proper variant handling\n"
                "• Maintain data integrity\n\n"
                "You can find the Duplicate button on the BOM Request form."
            ))

        logging.info(" Custom Code:Starting duplication of BOM Request ID %s", self.id)

        default = dict(default or {})
        
        default['name'] = self._next_version_name(self.name)

        # Pull source values safely
        product_id = self.product_id.id
        product_tmpl_id = self.product_tmpl_id.id
        default_variant_id = self.product_tmpl_id.product_variant_id.id  # base/default variant

        # colorway_id = self.colorway_id.id
        # size_id = getattr(self, "size_id", False) and self.size_id.id
        partner_id = self.partner_id.id
        company_id = self.env.company.id
        # Build new BOM vals
        bom_vals = {
                    'product_tmpl_id': product_tmpl_id,
                    'product_id': default_variant_id,
                    'product_qty': 1.0,
                    'type': 'normal',
                    'company_id': company_id,
                    'partner_id': partner_id,
                    'rel_service': self.rel_service.id,
                }

        logging.info('BOM duplication - base vals: %s', bom_vals)   

        # Create BOM
        new_bom = self.env['mrp.bom'].create(bom_vals)
        new_bom.write({
                        'colorway_id': False,
                        'size_id': False,
                        'style_colorway_id': False,
                    })

        # Copy subcontractors if field exists
        if hasattr(self, 'subcontractor_ids') and self.subcontractor_ids:
            new_bom.subcontractor_ids = [(6, 0, self.subcontractor_ids.ids)]

        # Attach BOM to duplicated request
        default['bom_id'] = new_bom.id
        default['mo_id'] = False
        default['colorway_id'] = False
        default['style_colorway_id'] = False
        default['size_id'] = False
        logging.info('Default %s', default)
        self = self.with_context(skip_bom_request_create_logic=True)
        return super(BOMRequest, self).copy(default)


    def _get_uom_gram(self):
        try:
            return self.env.ref("uom.product_uom_gram")
        except Exception:
            return self.env["uom.uom"].search([
                ("category_id", "=", self.env.ref("uom.uom_categ_wt").id),
                ("name", "ilike", "gram"),
            ], limit=1)

    def _get_uom_kg(self):
        try:
            return self.env.ref("uom.product_uom_kgm")
        except Exception:
            return self.env["uom.uom"].search([
                ("category_id", "=", self.env.ref("uom.uom_categ_wt").id),
                ("name", "ilike", "kg"),
            ], limit=1)

    @api.depends('bom_line_ids.product_qty', 'bom_line_ids.product_uom_id')
    def _compute_total_weight(self):
        Uom = self.env['uom.uom']
        gram = self._get_uom_gram()
        kg = self._get_uom_kg()
        weight_categ = gram.category_id if gram else False

        for rec in self:
            total_g = 0.0
            for line in rec.bom_line_ids:
                uom = line.product_uom_id
                # Only convert if UoM is a weight UoM
                if weight_categ and uom.category_id.id == weight_categ.id:
                    # Convert any weight UoM to grams
                    qty_in_g = uom._compute_quantity(line.product_qty, gram)
                    total_g += qty_in_g
                else:
                    # Not a weight UoM; ignore safely
                    logging.info(
                        "Skipping non-weight UoM on line %s (uom=%s, categ=%s)",
                        line.id, uom.display_name, uom.category_id.display_name
                    )
            rec.total_weight_g = total_g
            rec.total_weight_kg = gram and kg and gram._compute_quantity(total_g, kg) or 0.0

    @api.depends('product_tmpl_id')
    def _compute_style_yarn_variant_ids(self):
        """Compute available yarn variants for the current style"""
        for record in self:
            if record.product_tmpl_id:
                style_yarns = self.env['style.yarn.variant'].search([
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                yarn_ids = style_yarns.mapped('yarn_variant_id.id')
                record.style_yarn_variant_ids = [(6, 0, yarn_ids)]
            else:
                record.style_yarn_variant_ids = [(6, 0, [])]
                
    @api.onchange('yarn_variant')
    def _onchange_yarn_variant(self):
        """Ensure style yarn variant exists when yarn variant is selected"""
        if self.yarn_variant and self.product_tmpl_id:
            self.env['style.yarn.variant'].get_or_create(self.product_tmpl_id.id, self.yarn_variant.id)
                
    def action_push_weight_to_product(self):
        self.ensure_one()
        logging.info('Pushing weight to product %s', self.product_id)
        logging.info('Wait %s', self.total_weight_kg)
        
        if not self.product_id:
            raise ValidationError(_("No product variant set on this request."))

        # In Odoo, product weight is stored on the template in kilograms
        tmpl = self.product_id.product_tmpl_id
        new_kg = self.total_weight_kg or 0.0
        try:
            tmpl.write({'weight': new_kg})
        except Exception as e:
            logging.info(" Custom Code: Standard weight write failed for %s: %s. Using SQL fallback.",
                         tmpl.display_name, e)
            # Direct SQL bypass for urgent needs - wrap in savepoint to prevent transaction abort
            try:
                with self.env.cr.savepoint():
                    query = "UPDATE product_template SET weight = %s WHERE id = %s;"
                    self.env.cr.execute(query, (new_kg, tmpl.id))
                    tmpl.invalidate_recordset(['weight'])
            except Exception as sql_e:
                logging.error(" Custom Code: SQL weight fallback ALSO failed for %s: %s", tmpl.display_name, sql_e)
        logging.info(" Custom Code:Pushed %.3f kg to product template %s from BOM Request %s",
                    new_kg, tmpl.display_name, self.name)

    
    @api.onchange('colorway_id')
    def _onchange_colorway_id_create(self):
        """Handle creation of new colorway values"""
        if self.colorway_id and not self.colorway_id.id and self.colorway_id.name:
            # This is a new record being created
            colorway_attr = self._get_colorway_attribute()
            if colorway_attr:
                new_colorway = self.env['product.attribute.value'].create({
                    'name': self.colorway_id.name,
                    'attribute_id': colorway_attr.id,
                })
                self.colorway_id = new_colorway
                
    style_colorway_id = fields.Many2one('style.colorway', string='Style Colorway',
                                       domain="[('product_tmpl_id', '=', product_tmpl_id)]")
    # Garment fields - EDITABLE and SYNCED
    run_id = fields.Many2one('product.attribute.value', string='Run', 
                            domain="[('attribute_id.name', '=', 'Run')]")
    size_id = fields.Many2one('product.attribute.value', string='Size', 
                             domain="[('attribute_id.name', '=', 'Size')]")
    
    # Swatch fields - EDITABLE and SYNCED
    swatch_number_id = fields.Many2one('product.attribute.value', string='Swatch #', 
                                      domain="[('attribute_id.name', '=', 'Swatch #')]")
    body_stitch_id = fields.Many2one('stitch.library', string='Body Stitch')
    cuff_stitch_id = fields.Many2one('stitch.library', string='Cuff Stitch')
    
    # Machine fields - EDITABLE and SYNCED
    machine_id = fields.Many2one('machine.library', string='Machine')
    machine_id_selection = fields.Selection(
        [
            ('shima', 'Shima'),
            ('stoll', 'Stoll'),
        ],
        default=lambda self: 'shima' if 'uk' in (self.env.company.name or '').lower() else 'stoll',
        string='Machine',
    )
    order_date = fields.Date(string='Order Date')
    due_date = fields.Date(
        string="Due Date",
        default=fields.Date.context_today
    )
    company_id = fields.Many2one(
        'res.company', 'Company', index=True,
        default=lambda self: self.env.company)
    is_uk_company = fields.Boolean(
        compute='_compute_is_uk_company',
        store=False,
    )
    type = fields.Selection([
        ('normal', 'Manufacture this product'),
        ('phantom', 'Kit'),
        ('subcontract', 'Subcontracting')   # NEW OPTION
    ], 'BoM Type', default='normal', required=True)
    subcontractor_ids = fields.Many2many(
        'res.partner',
        'bom_request_subcontractor_rel',
        'bom_request_id',
        'partner_id',
        string='Subcontractors',
        domain=[('supplier_rank', '>', 0)]
    )
    

    machine_file = fields.Binary(string='Machine File', attachment=True)
    machine_filename = fields.Char(string='Machine Filename')
    expected_machine_time = fields.Char(string='Expected Machine Time')
    hs_code = fields.Char(string='HS Code')
    excalidraw_link = fields.Char(string='Excalidraw Link')
    
    # Cost fields (computed from BOM Request lines)
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                 default=lambda self: self.env.company.currency_id.id)
    
    # BOM Lines (Components) - Custom One2many for editing and syncing
    bom_line_ids = fields.One2many('maeknit.bom.request.line', 'bom_request_id', string='Components')
    
    # Operations - Custom One2many for editing and syncing
    operation_ids = fields.One2many('maeknit.bom.request.operation', 'bom_request_id', string='Operations')
    
    # Additional BOM Request specific fields
    notes = fields.Text(string='Technical Notes')
    structure_cad_data = fields.Text(string='Structure CAD Data', help='Excalidraw scene JSON')
    artwork_data = fields.Text(string='Artwork Data')

    measurement_widget_data = fields.Json(string='Measurement Widget Data', default=lambda self: {
        'structurePanels': [],
        'customPanels': [],
        'hiddenPanels': [],
        'unit': 'inches'
    })
    
    measurement_panel_image_ids = fields.One2many(
        'ir.attachment',
        'res_id',
        domain=[('res_model', '=', 'maeknit.bom.request'), ('res_field', '=', 'measurement_widget_data')],
        string='Measurement Panel Images',
        copy=False
    )
    
    measurement_widget_data_with_images = fields.Json(
        string='Measurement Data with Images',
        compute='_compute_measurement_widget_data_with_images',
        store=False
    )

    whole_cad_data = fields.Json(
        string='Whole CAD Data',
        help='Lightweight whole CAD data (image stored as attachment ID)',
        default=lambda self: {
            'max_version': 0,
            'measurements': [],
            'image_attachment_id': None,
            'unit': 'inches'
        }
    )
    
    whole_cad_image_id = fields.Many2one(
        'ir.attachment',
        string='Whole CAD Image',
        help='Image attachment for whole CAD diagram'
    )
    
    whole_cad_data_with_images = fields.Json(
        string='Whole CAD Data (Full)',
        compute='_compute_whole_cad_data_with_images',
        help='Full whole CAD data with image restored from attachment for widget display'
    )

    cad_pom_data = fields.Json(
        string='CAD & POM Data',
        help='CAD & POM data (no versioning, image stored as attachment ID)',
        default=lambda self: {
            'max_version': 0,
            'measurements': [],
            'image_attachment_id': None,
            'unit': 'inches'
        }
    )

    cad_pom_image_id = fields.Many2one(
        'ir.attachment',
        string='CAD & POM Image',
        help='Image attachment for CAD & POM diagram'
    )

    cad_pom_data_with_images = fields.Json(
        string='CAD & POM Data (Full)',
        compute='_compute_cad_pom_data_with_images',
        help='Full CAD & POM data with image restored from attachment for widget display'
    )

    calibration_data = fields.Json(string='Calibration Data', default=lambda self: {
        'measurementUnit': 'inches',
        'bodySwatchSpecsX': 0,
        'bodySwatchSpecsY': 0,
        'bodyMeasurementX': 0,
        'bodyMeasurementY': 0,
        'bodyCalibrationX': 0,
        'bodyCalibrationY': 0,
        'cuffSwatchSpecsX': 0,
        'cuffSwatchSpecsY': 0,
        'cuffMeasurementX': 0,
        'cuffMeasurementY': 0,
        'cuffCalibrationX': 0,
        'cuffCalibrationY': 0,
        'widthImageAttachmentId': None,
        'heightImageAttachmentId': None,
        'widthImage2AttachmentId': None,
        'heightImage2AttachmentId': None,
    })
    
    calibration_data_with_images = fields.Json(
        string='Calibration Data (Full)',
        compute='_compute_calibration_data_with_images',
        help='Full calibration data with images restored from attachments for widget display'
    )
    
    calibration_image_ids = fields.One2many(
        'ir.attachment',
        'res_id',
        string='Calibration Images',
        domain=[('res_model', '=', 'maeknit.bom.request'), ('res_field', 'in', ['width_image', 'height_image', 'width_image_2', 'height_image_2'])],
        help='Image attachments for calibration measurements'
    )
    # Updates end here

    # Render Tab Fields
    style_3d_link = fields.Char(
        string='Style 3D Link',
        help='Link to the Style 3D rendering'
    )

    render_image_ids = fields.One2many(
        'render.image.line',
        'bom_request_id',
        string='Render Images',
        help='Render images for this BOM Request'
    )

    excalidraw_data = fields.Json(
        string='Excalidraw Sketch Data',
        help='Lightweight sketch elements (images stored as attachments)',
        default=lambda self: {'elements': [], 'appState': {}, 'fileIds': {}}
    )
    
    excalidraw_file_ids = fields.Many2many(
        'ir.attachment',
        'bom_request_excalidraw_attachment_rel',
        'bom_request_id',
        'attachment_id',
        string='Excalidraw Files',
        help='Image assets referenced by the sketch'
    )
    
    excalidraw_data_with_images = fields.Json(
        string='Excalidraw Data (Full)',
        compute='_compute_excalidraw_data_with_images',
        help='Full excalidraw data with images restored from attachments for widget display'
    )

    garment_construction_data = fields.Json(
        string='Garment Construction Data',
        help='Excalidraw sketch data for Garment Construction (images stored as attachments)',
        default=lambda self: {'elements': [], 'appState': {}, 'fileIds': {}}
    )

    garment_construction_file_ids = fields.Many2many(
        'ir.attachment',
        'bom_request_garment_construction_attachment_rel',
        'bom_request_id',
        'attachment_id',
        string='Garment Construction Files',
        help='Image assets referenced by the Garment Construction sketch'
    )

    garment_construction_data_with_images = fields.Json(
        string='Garment Construction Data (Full)',
        compute='_compute_garment_construction_data_with_images',
        help='Full garment construction data with images restored from attachments for widget display'
    )

    @api.depends('company_id')
    def _compute_is_uk_company(self):
        for record in self:
            record.is_uk_company = 'uk' in (record.company_id.name or '').lower()

    def action_add_render_image(self):
        """Add render image slots: 4 on first click, 1 on subsequent clicks."""
        self.ensure_one()
        existing = len(self.render_image_ids)
        count = 4 if existing == 0 else 1
        for i in range(count):
            self.env['render.image.line'].create({
                'name': f'Render Image {existing + i + 1}',
                'sequence': (existing + i + 1) * 10,
                'bom_request_id': self.id,
            })
        return True

    def increment_whole_cad_version(self):
        """Increment Whole CAD version and add empty version columns to measurements"""
        self.ensure_one()
        if not self.whole_cad_data:
            self.whole_cad_data = {
                'max_version': 0,
                'measurements': [],
                'image': None,
                'unit': 'inches'
            }
        
        current_max = self.whole_cad_data.get('max_version', 0)
        next_version = current_max + 1
        
        # Add empty version fields to all existing measurements
        measurements = self.whole_cad_data.get('measurements', [])
        for measurement in measurements:
            measurement[f'v{next_version}'] = ""
        
        # Update the data structure
        updated_data = dict(self.whole_cad_data)
        updated_data['max_version'] = next_version
        updated_data['measurements'] = measurements
        
        self.whole_cad_data = updated_data
        logging.info(f" Custom Code: Incremented Whole CAD version from V{current_max} to V{next_version} for BOM Request {self.name}")


    @api.depends('product_tmpl_id', 'style_colorway_ids')
    def _compute_style_colorway_ids(self):
        """Compute available colorways for the product template from style.colorway table"""
        for record in self:
            if record.product_tmpl_id:
                # Get colorways from custom style.colorway table
                style_colorways = self.env['style.colorway'].search([
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                # Extract the actual colorway_id values for domain filtering
                colorway_ids = style_colorways.mapped('colorway_id.id')
                record.style_colorway_ids = [(6, 0, colorway_ids)]
            else:
                record.style_colorway_ids = [(6, 0, [])]

    @api.depends('product_tmpl_id')
    def _compute_style_size_ids(self):
        """Compute available sizes for the product template from style.size table"""
        for record in self:
            if record.product_tmpl_id:
                style_sizes = self.env['style.size'].search([
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                size_ids = style_sizes.mapped('size_id.id')
                record.style_size_ids = [(6, 0, size_ids)]
            else:
                record.style_size_ids = [(6, 0, [])]

    @api.onchange('yarn_variant')
    def _onchange_yarn_variant(self):
        """Ensure customer yarn variant exists when yarn variant is selected"""
        if self.yarn_variant and self.product_id:
            self.env['style.yarn.variant'].get_or_create(self.product_tmpl_id.id, self.yarn_variant.id)


    @api.onchange('style_colorway_id')
    def _onchange_style_colorway_id(self):
        """Update colorway_id when style_colorway_id changes"""
        if self.style_colorway_id:
            self.colorway_id = self.style_colorway_id.colorway_id
        else:
            self.colorway_id = False
    
    @api.onchange('colorway_id')
    def _onchange_colorway_id(self):
        """Update or create style_colorway_id when colorway_id changes"""
        if self.colorway_id and self.product_tmpl_id:
            # Find existing style colorway
            style_colorway = self.env['style.colorway'].search([
                ('product_tmpl_id', '=', self.product_tmpl_id.id),
                ('colorway_id', '=', self.colorway_id.id)
            ], limit=1)
            
            if style_colorway:
                self.style_colorway_id = style_colorway
            else:
                # Create new style colorway automatically
                style_colorway = self.env['style.colorway'].create({
                    'product_tmpl_id': self.product_tmpl_id.id,
                    'colorway_id': self.colorway_id.id,
                    'created_by_bom': True
                })
                self.style_colorway_id = style_colorway
        elif not self.colorway_id:
            self.style_colorway_id = False

    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        """Handle product template change and find last BOM"""
        if self.product_tmpl_id:
            # Find the last BOM for this product template
            last_bom = self.env['mrp.bom'].search([
                ('product_tmpl_id', '=', self.product_tmpl_id.id)
            ], order='create_date desc', limit=1)
            
            if last_bom:
                self.bom_id = last_bom
                # Sync colorway from the last BOM
                if last_bom.colorway_id:
                    self.colorway_id = last_bom.colorway_id
                    self.style_colorway_ids = [(6, 0, [last_bom.colorway_id.id])]
            
            # Set default product
            product = self.env['product.product'].search([
                ('product_tmpl_id', '=', self.product_tmpl_id.id)
            ], limit=1)
            if product:
                self.product_id = product
    
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
    
    @api.model_create_multi
    def create(self, vals_list):
        bom_requests = self.env['maeknit.bom.request']
        for vals in vals_list:
            # Handle Excalidraw data splitting before processing other vals
            if 'excalidraw_data' in vals and vals.get('excalidraw_data'):
                vals = self._split_excalidraw_files(vals)
            # Handle Garment Construction data splitting
            if 'garment_construction_data' in vals and vals.get('garment_construction_data'):
                vals = self._split_garment_construction_files(vals)
            # Handle Structure CAD data splitting (same Excalidraw format)
            if 'structure_cad_data' in vals and vals.get('structure_cad_data'):
                vals = self._split_structure_cad_files(vals)
            # Handle Artwork data extraction
            if 'artwork_data' in vals and vals.get('artwork_data'):
                vals = self._process_artwork_data(vals)
            # Handle Measurement panel image extraction
            if 'measurement_widget_data' in vals and vals.get('measurement_widget_data'):
                vals = self._process_measurement_panel_images(vals)
            
            if self.env.context.get('default_is_garment_bom'):
                vals['is_garment_bom'] = True
            if self.env.context.get('default_is_grading_bom'):
                vals['is_grading_bom'] = True
            if self.env.context.get('default_is_swatch_bom'):
                vals['is_swatch_bom'] = True
            if self.env.context.get('default_is_reverse_bom'):
                vals['is_reverse_bom'] = True
            if self.env.context.get('default_is_production_bom'):
                vals['is_production_bom'] = True
            logging.info(" Custom Code:Creating BOM Request with vals: %s", vals)
            if not vals.get('product_tmpl_id') and not vals.get('product_id') and vals.get('product_tmpl_name'):

                # Decide category by BOM type
                is_swatch = vals.get('is_swatch_bom') or self.env.context.get('default_is_swatch_bom')
                category = 'swatch' if is_swatch else 'garment'

                # Search for existing product first (case-insensitive match)
                existing = self.env['product.template'].search([
                    ('name', '=ilike', vals['product_tmpl_name']),
                    ('product_category', '=', category),
                ], limit=1)

                if existing:
                    product_tmpl = existing
                    logging.info(" Custom Code: Found existing product '%s' (ID %s) for BOM Request", product_tmpl.name, product_tmpl.id)
                else:
                    # Generate style_family using partner initials + sequence (same logic as CRM lead)
                    partner_name = ''
                    if vals.get('partner_id'):
                        partner = self.env['res.partner'].browse(vals['partner_id'])
                        partner_name = partner.name or ''
                    style_family = self.env['crm.lead']._generate_style_family(partner_name)

                    # Create product template — categ_id is resolved from product_category name by product.template.create()
                    product_tmpl = self.env['product.template'].create({
                        'name': vals['product_tmpl_name'],
                        'product_category': category,
                        'type': 'consu',
                        'brand_id': vals.get('partner_id'),
                        'style_family': style_family,
                        'company_id': vals.get('company_id') or self.env.company.id,
                    })
                    logging.info(" Custom Code: Created new product '%s' (ID %s, category %s, style_family %s) for BOM Request", product_tmpl.name, product_tmpl.id, category, style_family)

                # Always one variant normally
                product_variant = product_tmpl.product_variant_id

                # Set create() vals so BOMRequest links properly
                vals['product_tmpl_id'] = product_tmpl.id
                vals['product_id'] = product_variant.id

                # Optional: prefill BOM's product
                vals.setdefault('bom_id', False)

            # Sync brand_id, style_family, company_id onto the product for Path 1 (quick-create via many2one)
            # For Path 2 (product_tmpl_name), fields are already set above — this is a no-op for those.
            product_tmpl_id_for_sync = vals.get('product_tmpl_id')
            if product_tmpl_id_for_sync:
                product_tmpl_sync = self.env['product.template'].browse(product_tmpl_id_for_sync)
                update_product_vals = {}

                # Client: set brand_id from BOM request partner if not already set on product
                if not product_tmpl_sync.brand_id and vals.get('partner_id'):
                    update_product_vals['brand_id'] = vals['partner_id']

                # Style Family: generate if not set on product
                if not product_tmpl_sync.style_family:
                    partner_name = ''
                    if vals.get('partner_id'):
                        partner = self.env['res.partner'].browse(vals['partner_id'])
                        partner_name = partner.name or ''
                    update_product_vals['style_family'] = self.env['crm.lead']._generate_style_family(partner_name)

                # Lab: set company_id from BOM request company if not already set on product
                if not product_tmpl_sync.company_id:
                    update_product_vals['company_id'] = vals.get('company_id') or self.env.company.id

                if update_product_vals:
                    # Separate company_id to handle it safely with a savepoint
                    company_id_to_sync = update_product_vals.pop('company_id', None)
                    
                    # Update other fields first (brand_id, style_family)
                    if update_product_vals:
                        product_tmpl_sync.write(update_product_vals)
                        logging.info(" Custom Code: Synced product '%s' from BOM Request — fields updated: %s", product_tmpl_sync.name, list(update_product_vals.keys()))
                    
                    # Attempt to update company_id safely
                    if company_id_to_sync:
                        try:
                            with self.env.cr.savepoint():
                                product_tmpl_sync.write({'company_id': company_id_to_sync})
                                logging.info(" Custom Code: Propagated company to product template %s", product_tmpl_sync.name)
                        except Exception as e:
                            logging.info(" Custom Code: Skipping company propagation for product %s: %s", product_tmpl_sync.name, str(e))
                
            # 1. Auto-generate sequence name
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('maeknit.bom.request') or 'New'

            if vals.get('yarn_variant') and vals.get('product_tmpl_id'):
                self.env['style.yarn.variant'].get_or_create(vals['product_tmpl_id'], vals['yarn_variant'])

            if vals.get('size_id') and vals.get('product_tmpl_id'):
                self.env['style.size'].get_or_create_style_size(vals['product_tmpl_id'], vals['size_id'])

            # 2. Style-colorway sync
            if vals.get('style_colorway_id'):
                style_colorway = self.env['style.colorway'].browse(vals['style_colorway_id'])
                if style_colorway.exists() and style_colorway.colorway_id and 'colorway_id' not in vals:
                    vals['colorway_id'] = style_colorway.colorway_id.id
            elif vals.get('colorway_id') and 'style_colorway_id' not in vals:
                product_tmpl_id = vals.get('product_tmpl_id')
                if product_tmpl_id:
                    style_colorway = self.env['style.colorway'].search([
                        ('product_tmpl_id', '=', product_tmpl_id),
                        ('colorway_id', '=', vals['colorway_id']),
                        ('active', '=', True)
                    ], limit=1)
                    if style_colorway:
                        vals['style_colorway_id'] = style_colorway.id

            service_name = ""
            sale_order = self.env['sale.order'].browse(vals.get('sale_order_id')) if vals.get('sale_order_id') else None
            
            # First try to detect from Sale Order
            if sale_order and sale_order.exists() and sale_order.x_rel_service_id:
                service_from_so = (sale_order.x_rel_service_id.name or "").lower().strip()
                if "reverse" in service_from_so:
                    service_name = "reverse"
                elif "grading" in service_from_so:
                    service_name = "grading"
                elif "swatch" in service_from_so:
                    service_name = "swatch"
                elif "development" in service_from_so:
                    service_name = "development"
                elif "production" in service_from_so:
                    service_name = "production"
                # Store the actual service product for the BOM
                if not vals.get('rel_service'):
                    vals['rel_service'] = sale_order.x_rel_service_id.id
            
            # If no SO, detect from context flags
            if not service_name:
                if vals.get('is_development_bom') or self.env.context.get('default_is_development_bom') or vals.get('is_garment_bom') or self.env.context.get('default_is_garment_bom'):
                    service_name = "development"
                elif vals.get('is_swatch_bom') or self.env.context.get('default_is_swatch_bom'):
                    service_name = "swatch"
                elif vals.get('is_grading_bom') or self.env.context.get('default_is_grading_bom'):
                    service_name = "grading"
                elif vals.get('is_reverse_bom') or self.env.context.get('default_is_reverse_bom'):
                    service_name = "reverse"
                elif vals.get('is_production_bom') or self.env.context.get('default_is_production_bom'):
                    service_name = "production"
                else:
                    service_name = "production"  # default fallback
            
            # Find the service product if not already set
            if not vals.get('rel_service') and service_name:
                service_product_name = ""
                if service_name == "production":
                    service_product_name = "Production Service"
                elif service_name == "development":
                    service_product_name = "Development Service"
                elif service_name == "grading":
                    service_product_name = "Grading Service"
                elif service_name == "swatch":
                    service_product_name = "Swatch Service"
                
                if service_product_name:
                    service_product = self.env['product.product'].search([
                        ('name', '=', service_product_name),
                        ('type', '=', 'service')
                    ], limit=1)
                    if service_product:
                        vals['rel_service'] = service_product.id
                        logging.info(" Custom Code:Set rel_service to %s (ID: %s) for service_name '%s'", 
                                   service_product_name, service_product.id, service_name)
            # 4. BOM handling
            if vals.get('bom_id'):
                bom = self.env['mrp.bom'].browse(vals['bom_id'])
                if bom.exists():
                    vals.update(self._get_bom_common_data(bom))
                else:
                    logging.warning("Provided bom_id %s does not exist.", vals['bom_id'])
                    vals['bom_id'] = False 

            # If no BOM ID provided, create one
            if not vals.get('bom_id'):
                product_tmpl_id = vals.get('product_tmpl_id')
                product_id = vals.get('product_id')
                
                # Ensure we have a product_id
                if not product_id and product_tmpl_id:
                    product = self.env['product.product'].search([('product_tmpl_id', '=', product_tmpl_id)], limit=1)
                    product_id = product.id if product else False

                if not product_id:
                    raise ValidationError(_("Cannot create a BOM without a specific product variant."))
                
                logging.info(f" Custom Code: Product ID for BOM creation: {product_id}")
                vals['product_id'] = product_id # Ensure product_id is in vals if created above
                company_id = vals.get('company_id') or self.env.company.id

                existing_bom = self.env['mrp.bom'].search([
                    ('product_id', '=', product_id),
                    ('company_id', '=', company_id),
                    ('colorway_id', '=', vals.get('colorway_id') or False),
                    ('size_id', '=', vals.get('size_id') or False),
                ], limit=1)

                if existing_bom:
                    bom = existing_bom
                    if vals.get('rel_service') and not bom.rel_service:
                        bom.write({'rel_service': vals['rel_service']})
                        logging.info(" Custom Code:Updated existing BOM %s with rel_service %s", bom.id, vals['rel_service'])
                        self.product_id = bom.product_id
                else:
                    bom_vals = {
                        'product_tmpl_id': product_tmpl_id or self.env['product.product'].browse(product_id).product_tmpl_id.id,
                        'product_id': product_id,
                        'colorway_id': vals.get('colorway_id'),
                        'size_id': vals.get('size_id'),
                        'product_qty': 1.0,
                        'type': 'normal',
                        'gauge_id': vals.get('gauge_id'),
                        'company_id': company_id,
                        'partner_id': vals.get('partner_id'),
                        'rel_service': vals.get('rel_service')  # Now includes the detected service
                    }
                    bom = self.env['mrp.bom'].create(bom_vals)
                    logging.info('bom.product_id %s', bom.product_id)
                    self.product_id = bom.product_id
                    logging.info(" Custom Code:Created BOM %s with rel_service %s", bom.id, vals.get('rel_service'))

                if 'subcontractor_ids' in vals:
                    bom.write({'subcontractor_ids': [(6, 0, vals['subcontractor_ids'])]})

                vals['bom_id'] = bom.id
                
                # Sync common fields from the newly created BOM
                vals.update(self._get_bom_common_data(bom))
            logging.info('vals after BOM handling: %s', vals)
            # 5. Set default operation and R&D task templates
            company_id = vals.get('company_id') or self.env.company.id
            if not vals.get('operation_template_id'):
                default_template = self.env["maeknit.bom.operation.template"].search(
                    [
                        ("related_service", "=", service_name),
                        ("company_id", "in", [company_id, False]),
                    ],
                    limit=1,
                )
                logging.info(" Custom Code:Found default operation template: %s", default_template)
                if default_template:
                    vals['operation_template_id'] = default_template.id 

            if not vals.get('rnd_task_template_id'):
                rnd_template = self.env["maeknit.rnd.task.template"].search(
                                    [
                                        ("related_service", "=", service_name),
                                        ("company_id", "in", [company_id, False]),
                                    ],
                                    limit=1,
                                )
                logging.info(" Custom Code:Found default R&D task template: %s", rnd_template)
                if rnd_template:
                    vals['rnd_task_template_id'] = rnd_template.id

            # sample is auto-computed from BOM version (related field)
            vals.pop('sample', None)

        # 6. Create all BOM Requests in one batch
        bom_requests = super(BOMRequest, self).create(vals_list)
           
        # 7. Post-creation logic per record
        for bom_request in bom_requests:
            # Create project and main task if manually created (no SO linked)
            if not bom_request.sale_order_id:
                logging.info(" Custom Code:BOM Request %s created manually; creating project and main task.", bom_request.name)
                bom_request._ensure_project_and_task()
        
            # Create default Yarn Orchestration lines
            for i in range(1, 9):
                self.env['maeknit.yarn.orchestration'].create({
                    'bom_request_id': bom_request.id,
                    'yarn_carrier': i,
                })

            # Populate operations from template if not already present
            if not bom_request.operation_ids and bom_request.operation_template_id:
                if bom_request.sale_order_line_id and bom_request.sale_order_line_id.pricing_id:
                    # Use pricing data from SO instead of template
                    pricing = bom_request.sale_order_line_id.pricing_id
                    logging.info(" Custom Code:[BOM_CREATE] Using SO pricing data for operations (pricing_id=%s)", pricing.id)
                    
                    for pricing_op in pricing.operation_ids.sorted('sequence'):
                        vals = {
                            'bom_request_id': bom_request.id,
                            'operation_id': pricing_op.operation_id.id,
                            'workcenter_id': pricing_op.workcenter_id.id if pricing_op.workcenter_id else False,
                            'time_cycle': (pricing_op.expected_minutes / 60.0) if pricing_op.expected_minutes else 60.0,
                            'sequence': pricing_op.sequence,
                        }
                        
                        # Add employee assignment if available
                        if pricing_op.employee_id:
                            vals['employee_assigned_ids'] = [(6, 0, [pricing_op.employee_id.id])]
                        
                        self.env['maeknit.bom.request.operation'].create(vals)
                        logging.info(" Custom Code:[BOM_CREATE] Created operation from SO pricing: %s", pricing_op.operation_name)
                else:
                    # Fallback to template if no SO pricing data
                    logging.info(" Custom Code:[BOM_CREATE] Using operation template (no SO pricing data)")
                    sequence = 1
                    for line in bom_request.operation_template_id.line_ids.sorted('sequence'):
                        self.env['maeknit.bom.request.operation'].create({
                            'bom_request_id': bom_request.id,
                            'operation_id': line.operation_id.id,
                            'sequence': sequence,
                        })
                        sequence += 1

            # Populate R&D Subtasks from template if not already present
            if not bom_request.sub_task_ids and bom_request.rnd_task_template_id:
                bom_request._create_rnd_subtasks(bom_request)
            
        return bom_requests
    def _ensure_project_and_task(self):
        """Create project + main task based on service type.
        Called only when BOM Request is created manually."""
        for req in self:
            if req.project_task_id:
                continue

            # Detect service_name using BOM booleans
            service_name = "production"
            if req.is_garment_bom or req.is_development_bom:
                service_name = "development"
            if req.is_reverse_bom:
                service_name = "reverse"
            if req.is_production_bom:
                service_name = "production"
            if req.is_grading_bom:
                service_name = "grading"
            if req.is_swatch_bom:
                service_name = "swatch"
            logging.info(" Custom Code:Detected service_name '%s' for BOM Request %s", service_name, req.name)
            # Tag
            tag_id = False
            if service_name:
                tag_id = req.env['project.tags'].search([('name', '=', service_name)], limit=1).id

            # Project
            project_vals = {
                "name": f"{req.product_id.display_name or 'Garment'} Project",
                "company_id": req.company_id.id,
                "partner_id": req.partner_id.id,
                "tag_ids": [(6, 0, [tag_id])] if tag_id else False,
            }
            project = req.env["project.project"].create(project_vals)

            # Task
            task_vals = {
                "name": req.product_id.display_name,
                "project_id": project.id,
                "tag_ids": [(6, 0, [tag_id])] if tag_id else False,
                "date_deadline": req.due_date,
            }
            task = req.env["project.task"].create(task_vals)

            # Link
            req.project_task_id = task.id

    def _create_rnd_subtasks(self, bom_request):
        main_task_id = bom_request.project_task_id.id if bom_request.project_task_id else False
        project_id = bom_request.project_task_id.project_id.id if bom_request.project_task_id else False

        if not project_id or not main_task_id:
            ProductTemplate = self.env['product.template']
            Project = self.env['project.project']
            ProjectTask = self.env['project.task']

            product = bom_request.product_id or False
            product_name = product.display_name if product else "Unnamed"

            # Derive service name
            if bom_request.is_development_bom:
                service_name = "Development Service"
            elif bom_request.is_swatch_bom:
                service_name = "Swatch Service"
            elif bom_request.is_grading_bom:
                service_name = "Grading Service"
            # elif bom_request.is_reverse_bom:
                # service_name = "Reverse Engineering Service"
            elif bom_request.is_production_bom:
                service_name = "Production Service"
            else:
                service_name = "Development Service"

            sample_label = bom_request.sample or "Sample 1"

            linked_product = ProductTemplate.search([
                ('id', '=', bom_request.product_tmpl_id.id)
            ], limit=1)

            base_name = str(linked_product.name or product_name)
            project_name = f"{base_name} - {service_name}"
            tag_id = self._get_or_create_service_tag(service_name)

            # Create project + main task
            project = Project.create({
                'name': project_name,
                'company_id': bom_request.company_id.id,
                'partner_id': bom_request.partner_id.id,
                'tag_ids': [(6, 0, [tag_id])] if tag_id else [(6, 0, [])],
            })
            main_task = ProjectTask.create({
                'name': f"{base_name} - {sample_label}",
                'project_id': project.id,
                'partner_id': bom_request.partner_id.id,
                'tag_ids': [(6, 0, [tag_id])] if tag_id else [(6, 0, [])],
            })
            bom_request.write({'project_task_id': main_task.id})
            main_task_id, project_id = main_task.id, project.id

        for line in bom_request.rnd_task_template_id.line_ids:
            self.env['project.task'].create({
                'name': line.name,
                'bom_request_id': bom_request.id,
                'project_id': project_id,
                'parent_id': main_task_id,
                'user_ids': [(6, 0, line.user_ids.ids)],
                'state': '00_ready_to_start',
                'date_deadline': bom_request.due_date - timedelta(days=3),
                'tag_ids': [(6, 0, [])],
            })

    def _get_bom_common_data(self, bom):
        """Extract common data from BOM but fallback to existing self values."""
        if not bom.exists():
            return {}

        def pick(field_name):
            """Choose BOM value → self value → False"""
            bom_val = getattr(bom, field_name, False)
            if bom_val:
                if isinstance(bom._fields[field_name], fields.Many2one):
                    return bom_val.id
                return bom_val

            self_val = getattr(self, field_name, False)
            if self_val:
                if isinstance(self._fields[field_name], fields.Many2one):
                    return self_val.id
                return self_val

            return False

        data = {
            'colorway_id': pick('colorway_id'),
            'size_id': pick('size_id'),
            'body_stitch_id': pick('body_stitch_id'),
            'cuff_stitch_id': pick('cuff_stitch_id'),
            'machine_id': pick('machine_id'),
            'gauge_id': pick('gauge_id'),
            'machine_file': pick('machine_file'),
            'machine_filename': pick('machine_filename'),
            'expected_machine_time': pick('expected_machine_time'),
            'hs_code': pick('hs_code'),
            'excalidraw_link': pick('excalidraw_link'),
            'type': pick('type'),
            'subcontractor_ids': [(6, 0, bom.subcontractor_ids.ids)]
                if bom.subcontractor_ids
                else ([(6, 0, self.subcontractor_ids.ids)] if self.subcontractor_ids else False),
        }

        # Style Colorway logic remains same
        if data['colorway_id'] and self.product_tmpl_id:
            style_colorway = self.env['style.colorway'].search([
                ('product_tmpl_id', '=', self.product_tmpl_id.id),
                ('colorway_id', '=', data['colorway_id']),
                ('active', '=', True)
            ], limit=1)
            if style_colorway:
                data['style_colorway_id'] = style_colorway.id
        logging.info(" Custom Code:Extracted BOM common data: %s", data)
        return data


    @api.depends('bom_line_ids.line_cost')
    def _compute_total_cost(self):
        """Compute total cost from BOM Request lines"""
        for request in self:
            request.total_cost = sum(line.line_cost for line in request.bom_line_ids)
    
    def write(self, vals):
        """
        Override write to:
        1. Handle Excalidraw data extraction before other processing
        2. Sync style/colorway data
        3. Sync CAD data to Manufacturing Order
        4. Sync calibration data to Manufacturing Order
        5. Handle state/stage changes
        """
        old_product_names = {request.id: request._get_related_product_name() for request in self}

        # Sync calibration data to MO before writing if present
        if 'calibration_data' in vals and self.mo_id:
            self.mo_id.with_context(skip_bom_request_calibration_sync=True).write({
                'calibration_data': vals['calibration_data']
            })
            
        if self.mo_id:
            mo_vals = {}

            if self.bom_id and self.mo_id.bom_id != self.bom_id:
                mo_vals["bom_id"] = self.bom_id.id

            if self.product_id and self.mo_id.product_id != self.product_id:
                mo_vals["product_id"] = self.product_id.id

            if mo_vals:
                self.mo_id.with_context(
                    skip_bom_request_calibration_sync=True
                ).write(mo_vals)

        # Step 1: Pre-process Excalidraw data if present (extract images to attachments)
        if 'excalidraw_data' in vals and vals.get('excalidraw_data'):
            vals = self._split_excalidraw_files(vals)

        # Step 1.1: Pre-process Garment Construction data if present
        if 'garment_construction_data' in vals and vals.get('garment_construction_data'):
            vals = self._split_garment_construction_files(vals)

        # Step 1.2: Pre-process Structure CAD data if present (same Excalidraw format)
        if 'structure_cad_data' in vals and vals.get('structure_cad_data'):
            vals = self._split_structure_cad_files(vals)

        # Step 1.3: Pre-process Artwork data if present
        if 'artwork_data' in vals and vals.get('artwork_data'):
            vals = self._process_artwork_data(vals)

        # Step 1.5: Pre-process Whole CAD data if present (extract image to attachment)
        if 'whole_cad_data' in vals and vals.get('whole_cad_data'):
            vals = self._process_whole_cad_image(vals)

        # Step 1.55: Pre-process CAD & POM data if present (extract image to attachment)
        if 'cad_pom_data' in vals and vals.get('cad_pom_data'):
            vals = self._process_cad_pom_image(vals)

        # Step 1.6: Pre-process Measurement data if present (extract images to attachments)
        if 'measurement_widget_data' in vals and vals.get('measurement_widget_data'):
            vals = self._process_measurement_panel_images(vals)
        
        # Step 2: Sync style_colorway_id and colorway_id
        if 'style_colorway_id' in vals and vals['style_colorway_id']:
            style_colorway = self.env['style.colorway'].browse(vals['style_colorway_id'])
            if style_colorway.exists() and style_colorway.colorway_id and 'colorway_id' not in vals:
                vals['colorway_id'] = style_colorway.colorway_id.id
        elif 'colorway_id' in vals and vals['colorway_id'] and 'style_colorway_id' not in vals:
            product_tmpl_id = self.product_tmpl_id.id
            if product_tmpl_id:
                style_colorway = self.env['style.colorway'].search([
                    ('product_tmpl_id', '=', product_tmpl_id),
                    ('colorway_id', '=', vals['colorway_id']),
                    ('active', '=', True)
                ], limit=1)
                if style_colorway:
                    vals['style_colorway_id'] = style_colorway.id
        
        # Step 3: Call parent write method
        result = super().write(vals)
        
        # Step 4: Sync yarn variant and size if present
        for req in self:
            if req.yarn_variant and req.product_tmpl_id:
                self.env['style.yarn.variant'].get_or_create(req.product_tmpl_id.id, req.yarn_variant.id)
            if req.size_id and req.product_tmpl_id:
                self.env['style.size'].get_or_create_style_size(req.product_tmpl_id.id, req.size_id.id)
        
        # Step 5: Sync common fields to BOM if in draft state
        logging.info(" Custom Code:BOM Request common fields synced to BOM")
        self._sync_common_to_bom(vals)
        
        # Step 6: Sync state/stage changes with ECO
        if 'state' in vals or 'stage_id' in vals:
            logging.info(" Custom Code:BOM Request state or stage changed, syncing with ECO")
            self._sync_state_with_eco(vals)
        
        # Step 7: Sync CAD data to Manufacturing Order
        if not self.env.context.get('skip_mo_cad_sync'):
            cad_fields_to_sync = {}
            if 'whole_cad_data' in vals:
                cad_fields_to_sync['whole_cad_data'] = vals['whole_cad_data']
            if 'measurement_widget_data' in vals:
                cad_fields_to_sync['measurement_widget_data'] = vals['measurement_widget_data']
            if 'structure_cad_data' in vals:
                cad_fields_to_sync['structure_cad_data'] = vals['structure_cad_data']
            if 'cad_pom_data' in vals:
                cad_fields_to_sync['cad_pom_data'] = vals['cad_pom_data']

            if cad_fields_to_sync:
                for request in self:
                    if request.mo_id:
                        request.mo_id.with_context(skip_bom_request_cad_sync=True).write(cad_fields_to_sync)
                        logging.info(
                            "[BOM_CAD_SYNC] Synced CAD data from BOM Request %s to MO %s: %s",
                            request.name,
                            request.mo_id.name,
                            list(cad_fields_to_sync.keys())
                        )

        # Step 7.5: Sync Render data to Manufacturing Order
        if not self.env.context.get('skip_mo_render_sync'):
            render_fields_to_sync = {}
            if 'style_3d_link' in vals:
                render_fields_to_sync['style_3d_link'] = vals['style_3d_link']

            if 'render_image_ids' in vals:
                for request in self:
                    if request.mo_id:
                        # Sync render images from BOM Request to MO
                        # Delete existing render images on MO
                        request.mo_id.render_image_ids.unlink()

                        # Create new render images on MO
                        for img in request.render_image_ids:
                            self.env['render.image.line'].create({
                                'name': img.name,
                                'sequence': img.sequence,
                                'image': img.image,
                                'image_filename': img.image_filename,
                                'production_id': request.mo_id.id,
                            })

            if render_fields_to_sync:
                for request in self:
                    if request.mo_id:
                        request.mo_id.with_context(skip_bom_request_render_sync=True).write(render_fields_to_sync)
                        logging.info(
                            "[BOM_RENDER_SYNC] Synced render data from BOM Request %s to MO %s: %s",
                            request.name,
                            request.mo_id.name,
                            list(render_fields_to_sync.keys())
                        )

        # Step 8: Sync calibration data to Manufacturing Order (already done at the beginning of write)
        # if not self.env.context.get('skip_mo_calibration_sync'):
        #     if 'calibration_data' in vals:
        #         for request in self:
        #             if request.mo_id:
        #                 request.mo_id.with_context(skip_bom_request_calibration_sync=True).write({
        #                     'calibration_data': vals['calibration_data']
        #                 })
        #                 logging.info(
        #                     "[BOM_CALIBRATION_SYNC] Synced calibration data from BOM Request %s to MO %s",
        #                     request.name,
        #                     request.mo_id.name
        #                 )
        
        self._sync_crm_leads_on_product_name(old_product_names)
        return result

    def _update_bom_state_and_add_task(self):
        self.state = 'produced'
        main_task_id = self.project_task_id.id if self.project_task_id else False
        project_id = self.project_task_id.project_id.id if self.project_task_id else False
        existing_tasks = self.env['project.task'].search([
            ('bom_request_id', '=', self.id),
            ('name', 'ilike', 'Machine Program V'),
        ], order='id asc')
        logging.info('Existing tasks: %s', existing_tasks.mapped('name'))
        existing_users = []
        if not existing_tasks:
            next_version = 1
        else:
            versions = []
            for task in existing_tasks:
                logging.info('task name: %s', task.name)
                logging.info('assigned users: %s', task.user_ids.mapped('name'))
                existing_users = task.user_ids
                name = task.name.strip()
                if "V" in name:
                    try:
                        v_num = int(name.split("V")[-1])
                        versions.append(v_num)
                    except ValueError:
                        continue
            next_version = max(versions or [0]) + 1

        new_name = f"Machine Program V{next_version}"

        existing_user_ids = existing_tasks.mapped('user_ids').ids  

        self.env['project.task'].create({
                    'name': new_name,
                    'bom_request_id': self.id,
                    'project_id': project_id,
                    'parent_id': main_task_id,  # link to main project task
                    'state': '00_ready_to_start',
                    'user_ids': [(6, 0, existing_user_ids)],
                    'tag_ids': [(6, 0, [])],
                })
    def _sync_common_to_bom(self, vals):
        """Sync common field changes back to BOM"""
        logging.info(" Custom Code:Syncing common fields to BOM")
        for request in self:
            if not request.bom_id:
                continue
                
            bom_vals = {}
            common_fields = ['colorway_id', 'style_colorway_id', 'yarn_variant', 'size_id', 'partner_id',
                           'body_stitch_id', 'cuff_stitch_id', 'machine_id', 'gauge_id',
                           'machine_file', 'machine_filename', 'expected_machine_time', 
                           'hs_code', 'excalidraw_link', 'type', 'subcontractor_ids',  
                            ]
            
            for field in common_fields:
                if field in vals:
                    bom_vals[field] = vals[field]
            
            # Special handling for style_colorway_id to update colorway_id as well
            if 'style_colorway_id' in vals and vals['style_colorway_id']:
                style_colorway = self.env['style.colorway'].browse(vals['style_colorway_id'])
                if style_colorway.exists() and style_colorway.colorway_id:
                    bom_vals['colorway_id'] = style_colorway.colorway_id.id
                    bom_vals['style_colorway_id'] = style_colorway.id
            
            if bom_vals:
                request.bom_id.write(bom_vals)
                logging.info(f" Custom Code: Synced BOM Request {request.name} common changes to BOM {request.bom_id.id}")

    def _sync_state_with_eco(self, vals):
        """Sync BOM Request state changes with related ECO"""
        logging.info(" Custom Code:Syncing BOM Request state with ECO")
        for request in self:
            logging.info(f" Custom Code: Syncing BOM Request {request.name} with ECO {request.eco_id.name if request.eco_id else 'None'}")
            if not request.eco_id:
                continue            
                
            # Mapping from BOM Request state to ECO state
            state_mapping = {
                            'draft': 'draft',
                            'ready_to_program': 'progress',
                            'mo_confirmed': 'progress',
                            'produced': 'progress',
                            'ready_to_spec': 'progress',
                            'done': 'done',
                            'cancelled': 'cancelled',
                        }
            
            eco_vals = {}
            logging.info(f" Custom Code: Values to sync: {vals}")

            logging.info(f" Custom Code: Current ECO state: {request.eco_id.state}")
            logging.info(f" Custom Code: Current BOM Request state: {request.state}")
            
            # Sync state if changed
            if 'state' in vals and vals['state'] in state_mapping:
                eco_state = state_mapping[vals['state']]
                if request.eco_id.state != eco_state:
                    eco_vals['state'] = eco_state
                    
                # Find appropriate ECO stage for the BOM Request state
                stage = self._find_stage_for_state(vals['state'])
                if stage and request.eco_id.stage_id != stage:
                    eco_vals['stage_id'] = stage.id
            
            # Sync ECO stage directly if changed
            if 'stage_id' in vals and vals['stage_id']:
                stage = self.env['mrp.eco.stage'].browse(vals['stage_id'])
                if stage.exists() and request.eco_id.stage_id != stage:
                    eco_vals['stage_id'] = stage.id
                    # Update BOM Request state based on ECO stage
                    bom_state = self._get_state_from_stage(stage)
                    if bom_state and request.state != bom_state:
                        # Use super().write to avoid recursion if state change triggers ECO sync again
                        super(BOMRequest, request).write({'state': bom_state})
            
            # Update ECO if there are changes
            if eco_vals:
                request.eco_id.sudo().with_context(skip_bom_request_sync=True).write(eco_vals)
                logging.info(f" Custom Code: Synced BOM Request {request.name} state changes to ECO {request.eco_id.name}")

    def _find_stage_for_state(self, state):
        """Find appropriate ECO stage for BOM Request state"""
        Stage = self.env['mrp.eco.stage']
        
        stage_mapping = {
                        'draft': 'Draft',
                        'produced': 'In Production',
                        'mo_confirmed': 'In Production',
                        'produced': 'Quality Check',
                        'ready_to_spec': 'Quality Check',
                        'done': 'Completed',
                        'cancelled': 'Cancelled',
                    }
        
        stage_name = stage_mapping.get(state)
        if stage_name:
            # Search for the stage by name, case-insensitive
            return Stage.search([('name', 'ilike', stage_name)], limit=1)
        return False

    def _get_state_from_stage(self, stage):
        """Map ECO stage names to new BOM Request states"""
        if not stage:
            return False

        stage_name = (stage.name or '').strip().lower()

        if 'draft' in stage_name:
            return 'draft'
        elif 'program' in stage_name or 'ready' in stage_name:
            return 'produced'
        elif 'confirm' in stage_name or 'mo' in stage_name:
            return 'mo_confirmed'
        elif 'produce' in stage_name or 'quality' in stage_name:
            return 'produced'
        elif 'done' in stage_name or 'complete' in stage_name or 'finish' in stage_name:
            return 'done'
        elif 'cancel' in stage_name:
            return 'cancelled'
        else:
            return 'draft'

    def _get_related_product_name(self):
        """Return the display name for the BOM request's product/template."""
        template = self.product_tmpl_id
        if template and template.display_name:
            return template.display_name
        if self.product_id and self.product_id.display_name:
            return self.product_id.display_name
        return self.product_tmpl_name or False

    def _sync_crm_leads_on_product_name(self, old_product_names):
        """Propagate product name changes to linked CRM leads."""
        for request in self:
            new_name = request._get_related_product_name()
            old_name = old_product_names.get(request.id)
            if not new_name or new_name == old_name:
                continue
            logging.info(
                "[CRM SYNC] BOM %s product name changed from %s to %s",
                request.name,
                old_name,
                new_name,
            )
            request._write_product_name_to_crm_leads(new_name)

    def _write_product_name_to_crm_leads(self, product_name):
        SaleOrder = self.sale_order_id
        sale_line = self.sale_order_line_id
        if sale_line and sale_line.crm_child_lead_id:
            sale_line.crm_child_lead_id.sudo().write({'name': product_name})


    def action_start_program(self):
        """Start BOM request Ready to Program"""
        self.write({'state': 'ready_to_program'})
    
    def action_ready_to_ship(self):
        """Ready to Ship"""
        # self.mo_id.button_mark_done()
        self.write({'state': 'done'})

    def action_ready_to_spec(self):
        self.write({'state': 'ready_to_spec'})
        
    def action_produced(self):
        """Mark MO as done and update BOM Request state to Produced"""
        self.ensure_one()
        # self.mo_id.button_mark_done()
        mo = self.mo_id
        product = mo.product_id
        location = mo.location_dest_id
        quants = self.env['stock.quant'].search([
        ('product_id', '=', product.id),
        ('location_id', '=', location.id)
        ])
        if quants:
            for quant in quants:
                quant.quantity = 1.0  # directly set physical qty
                quant.inventory_quantity = 1.0
                quant._apply_inventory()
        else:
            # If no quant exists, create one
            self.env['stock.quant'].create({
                'product_id': product.id,
                'location_id': location.id,
                'quantity': 1.0,
            })
        
        self.write({'state': 'produced'})

    def action_request_revision(self):
        """Request a revision for the BOM Request"""
        for request in self:
            # Create a new revision request wizard
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'revision.request.wizard', 
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_sale_order_line_id': request.sale_order_line_id.id,
                    'default_bom_request_id': request.id,
                }
            }
    def action_set_production_ready_status(self):
        if self.bom_id:
            self.bom_id.action_set_production_ready_status()
        self.write({'state': 'production_ready'})
    
    def action_draft(self):
        self.write({'state': 'draft'})
        
    def action_generate_mo(self):
        """Approve BOM request and create Manufacturing Order"""
        skip_validation = self.env.context.get('skip_component_validation')
        for req in self:
            t0 = time.time()
            logging.info(" Custom Code:[TIMING] action_generate_mo START for %s", req.name)

            # ── Concurrent-execution guard ─────────────────────────────────────
            # Acquires a PostgreSQL row-level lock (NOWAIT = fail immediately if
            # another session already holds it, e.g. from a double-click).
            try:
                self.env.cr.execute(
                    'SELECT id FROM maeknit_bom_request WHERE id = %s FOR UPDATE NOWAIT',
                    (req.id,)
                )
            except psycopg2.OperationalError:
                raise ValidationError(
                    _("Manufacturing Order generation is already in progress for %s. "
                      "Please wait for it to complete and then refresh the page.") % req.name
                )
            logging.info(" Custom Code:[TIMING] +%.2fs — DB lock acquired", time.time() - t0)

            # Re-read state after acquiring the lock: if the first concurrent call
            # already finished and set state to 'produced', skip this call.
            req.invalidate_recordset(['state', 'mo_id'])
            if req.state == 'produced' and req.mo_id:
                logging.info(
                    " Custom Code: [GUARD] BOM Request %s is already in 'produced' state "
                    "with MO %s — skipping duplicate execution.",
                    req.name, req.mo_id.name
                )
                continue
            # ──────────────────────────────────────────────────────────────────

            if not req.bom_id:
                raise ValidationError("BOM Reference is missing.")
            logging.info(" Custom Code:req_bom_line_ids: %s", req.bom_line_ids.ids)
            logging.info(" Custom Code:req.bom_line_ids.ids: len %s", len(req.bom_line_ids.ids))
            if not skip_validation and len(req.bom_line_ids.ids) == 0:
                raise ValidationError("Please input atleast one component line")
            try:
                req.action_push_weight_to_product()
            except Exception as e:
                logging.info(" Custom Code:Auto push weight failed on %s: %s", req.name, e)
            logging.info(" Custom Code:[TIMING] +%.2fs — action_push_weight_to_product done", time.time() - t0)

            if req.eco_id:
                eco = req.eco_id
                old_bom = eco.bom_id if eco and eco.bom_id else False
                new_bom = eco.new_bom_id if eco and eco.new_bom_id else req.bom_id
                # Activate the new bom if present
                if new_bom:
                    new_bom.write({'active': True})

                # Archive the old bom if it's different from the new one
                if old_bom and new_bom and old_bom.id != new_bom.id:
                    old_bom.write({'active': False})
                    # Archive other BOM requests using the old BOM
                    # EXCEPT those that already have an MO (completed samples should stay visible)
                    other_reqs = self.env['maeknit.bom.request'].search([
                        ('id', '!=', req.id),
                        ('bom_id', '=', old_bom.id),
                        ('active', '=', True),
                        ('mo_id', '=', False),  # Only archive if NO MO exists yet
                    ])
                    if other_reqs:
                        other_reqs.write({'active': False})
                        logging.info(" Custom Code: [ECO] Archived %d BOM requests without MOs that used old BOM %s",
                                    len(other_reqs), old_bom.id)


                # Make sure the request points to the now-active new BoM
                req.bom_id = new_bom.id if new_bom else req.bom_id
            else:
                # No ECO: at least ensure the BoM on the request is active
                req.bom_id.write({'active': True})
            logging.info(" Custom Code:[TIMING] +%.2fs — ECO / BOM activation done", time.time() - t0)

            # Final sync of common fields to BOM before creating MO
            req._sync_common_to_bom({
                'colorway_id': req.colorway_id.id if req.colorway_id else False,
                'size_id': req.size_id.id if req.size_id else False,
                'machine_id': req.machine_id.id if req.machine_id else False,
                'gauge_id': req.gauge_id.id if req.gauge_id else False,
                'excalidraw_link': req.excalidraw_link,
                'subcontractor_ids': [(6, 0, req.subcontractor_ids.ids)] if req.subcontractor_ids else False,
                'type': req.type,
            })
            logging.info(" Custom Code:[TIMING] +%.2fs — _sync_common_to_bom done", time.time() - t0)
            
            # Use BOM's specific variant (with size/colorway) if available
            mo_product = req.bom_id.product_id or req.product_id

            # Create Manufacturing Order
            mo_vals = {
                'product_id': mo_product.id,
                'product_qty': req.product_qty,
                'bom_id': req.bom_id.id,
                'origin': req.sale_order_id.sudo().name if req.sale_order_id else False,
                'user_id': req.user_id.id,
                'partner_id': req.partner_id.id if req.partner_id else False,
                'bom_request_id': req.id,
                'whole_cad_data': req.whole_cad_data,
                'measurement_widget_data': req.measurement_widget_data,
                'date_start': fields.Datetime.now(),
                'gauge_id': req.gauge_id.id if req.gauge_id else False,
                'calibration_data': req.calibration_data,
                # ── Tab data that must also land on the MO ──
                # structure_cad_data is fields.Text on BOM req but fields.Json on MO —
                # parse to dict to avoid double-encoding
                'structure_cad_data': json.loads(req.structure_cad_data) if isinstance(req.structure_cad_data, str) and req.structure_cad_data else req.structure_cad_data,
                'cad_pom_data': req.cad_pom_data,
                'style_3d_link': req.style_3d_link,
                'artwork_data_standalone': req.artwork_data,
                'excalidraw_data_standalone': req.excalidraw_data,
                'garment_construction_data_standalone': req.garment_construction_data,
            }
            
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'mrp_operation'),
                ('company_id', '=', req.company_id.id)
            ], limit=1)

            if not picking_type:
                picking_type = self.env.ref('mrp.picking_type_manufacturing', raise_if_not_found=False)

            if not picking_type:
                raise ValidationError(_("No Manufacturing picking type found for company %s.") % req.company_id.display_name)

            # Set default source and destination
            mo_vals.update({
                'picking_type_id': picking_type.id,
                'location_src_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
            })
            logging.info(" Custom Code:MO vals for BOM Request %s: %s", req.name, mo_vals)

            # Create or update Manufacturing Order
            # For revisions (ECO-linked), always create a new MO
            is_revision = bool(req.eco_id)
            logging.info(" Custom Code: BOM Request %s: mo_id=%s, eco_id=%s, is_revision=%s",
                        req.id, req.mo_id.id if req.mo_id else None, req.eco_id.id if req.eco_id else None, is_revision)

            if req.mo_id and not is_revision:
                # Update existing Manufacturing Order (only for non-revisions)
                t_write = time.time()
                req.mo_id.with_context(skip_bom_request_cad_sync=True).sudo().write(mo_vals)
                logging.info(" Custom Code:[TIMING] +%.2fs — mo.write() done (update path, %.2fs)", time.time() - t0, time.time() - t_write)
                mo = req.mo_id
                logging.info(" Custom Code:Updated existing MO %s for BOM Request %s", mo.name, req.name)
                # req._sync_operations_to_mo(mo, req, mode='update')

            else:
                # Create a new Manufacturing Order (always for revisions, or if no existing MO)
                t_create = time.time()
                t_company_id = self.env['res.company'].search([('name', '=', self.sale_order_id.factory_id.name)])
                picking_type = self.env['stock.picking.type'].search(
                    [('code', '=', 'incoming'), ('warehouse_id.company_id', '=', t_company_id.id)])
                mo_vals.update({
                    'picking_type_id': picking_type.id,
                })
                mo = self.env['mrp.production'].with_company(t_company_id).with_context(
                    skip_bom_request_cad_sync=True,
                    tracking_disable=True,
                    mail_notrack=True,
                ).sudo().create(mo_vals)
                logging.info(" Custom Code:[TIMING] +%.2fs — mrp.production.create() done (%.2fs)", time.time() - t0, time.time() - t_create)
                req.write({'mo_id': mo.id})
                logging.info(" Custom Code:Created new MO %s for BOM Request %s (revision=%s)", mo.name, req.name, is_revision)
                # Sync operations from BOM Request to the new MO workorders
                t_sync = time.time()
                req._sync_operations_to_mo(mo, req, mode='create')
                logging.info(" Custom Code:[TIMING] +%.2fs — _sync_operations_to_mo done (%.2fs)", time.time() - t0, time.time() - t_sync)

            # Sync structure lines: link existing BOM Req lines to MO (single source of truth)
            t_struct = time.time()
            # Remove orphan MO-only lines that were created the old (duplicate) way
            mo.structure_ids.filtered(lambda l: not l.bom_request_id).unlink()
            # Link all BOM Req structure lines to this MO (idempotent)
            if req.structure_ids:
                req.structure_ids.write({'production_id': mo.id})
            logging.info(" Custom Code:[TIMING] +%.2fs — structure lines done (%.2fs, %d lines)", time.time() - t0, time.time() - t_struct, len(req.structure_ids))

            t_state = time.time()
            req.write({'state': 'produced'})
            logging.info(" Custom Code:[TIMING] +%.2fs — state→produced write done (%.2fs)", time.time() - t0, time.time() - t_state)
            logging.info(" Custom Code:[TIMING] action_generate_mo TOTAL for %s: %.2fs", req.name, time.time() - t0)

    def action_generate_rfq(self):
        """Create Purchase Order (RFQ) for the products in the BOM Requests, aggregating by product."""
        PurchaseOrder = self.env['purchase.order']
        PurchaseOrderLine = self.env['purchase.order.line']

        # Filter out requests that already have an MO or PO
        valid_requests = self.filtered(lambda r: not r.mo_id and not r.purchase_order_id)
        if not valid_requests:
            return

        # Group by Sale Order and Product to aggregate quantities
        # (Assuming all requests in 'self' belong to SOs with the same factory requirements)
        grouped_data = {}  # Key: (po_key, product_id, uom_id), Value: {'qty': total, 'reqs': recordset}

        for req in valid_requests:
            sale_order = req.sale_order_id
            if not sale_order or not sale_order.factory_id:
                logging.warning("BOM Request %s has no Sale Order or Factory. Skipping.", req.name)
                continue

            # Key for unique PO: (Origin, Factory, Company)
            po_key = (sale_order.name, sale_order.factory_id.id, req.company_id.id)
            # Key for unique Line: (Product, UOM)
            line_key = (req.product_id.id, req.product_uom_id.id or req.product_id.uom_po_id.id)

            full_key = (po_key, line_key)
            if full_key not in grouped_data:
                grouped_data[full_key] = {
                    'qty': 0.0,
                    'reqs': self.env['maeknit.bom.request'],
                    'factory_id': sale_order.factory_id.id,
                    'origin': sale_order.name,
                    'company_id': req.company_id.id,
                }

            grouped_data[full_key]['qty'] += req.product_qty or 1.0
            grouped_data[full_key]['reqs'] |= req

        for (po_key, line_key), data in grouped_data.items():
            origin, factory_id, company_id = po_key
            product_id, uom_id = line_key
            total_qty = data['qty']
            reqs = data['reqs']

            # Find or Create Purchase Order
            po = PurchaseOrder.search([
                ('origin', '=', origin),
                ('partner_id', '=', factory_id),
                ('state', '=', 'draft'),
                ('company_id', '=', company_id),
            ], limit=1)
            if not po:
                po_vals = {
                    'partner_id': factory_id,
                    'origin': origin,
                    'company_id': company_id,
                    'date_order': fields.Datetime.now(),
                    'picking_type_id': self.sale_order_id.fg_shipping_destinations.id,
                    'dest_address_id': self.sale_order_id.partner_id.id,
                }
                po = PurchaseOrder.create(po_vals)
                logging.info("Created new RFQ %s for origin %s", po.name, origin)

            # Find or Create/Update Purchase Order Line
            po_line = po.order_line.filtered(lambda l: l.product_id.id == product_id and l.product_uom.id == uom_id)

            if po_line:
                po_line.write({'product_qty': po_line.product_qty + total_qty})
                logging.info("Updated qty for product %s in RFQ %s", po_line.product_id.display_name, po.name)
            else:
                po_line_vals = {
                    'order_id': po.id,
                    'name': self.env['product.product'].browse(product_id).display_name,
                    'product_id': product_id,
                    'product_qty': total_qty,
                    'product_uom': uom_id,
                    'price_unit': self.env['product.product'].browse(product_id).standard_price or 0.0,
                    'date_planned': fields.Datetime.now(),
                }
                PurchaseOrderLine.create(po_line_vals)
                logging.info("Added aggregated line for product %s to RFQ %s", po_line_vals['name'], po.name)

            # Link all requests to the PO
            reqs.write({'purchase_order_id': po.id})

    def action_add_to_grading(self):
        for request in self:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'production.ready.wizard', 
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_source_bom_request_id': request.id,
                }
            }

    
    def action_production_ready(self):
        for request in self:
            # Create a new revision request wizard
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'production.ready.wizard', 
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_source_bom_request_id': request.id,
                }
            }
            
    def action_generate_another_mo(self):
        """Approve BOM request and create Manufacturing Order
        """
        self.ensure_one()
            
        if not self.mo_id:
            raise ValidationError(_("No existing Manufacturing Order found to restart."))
        
        # Find the last finished work order to use as the restart point
        last_finished_wo = self.env['mrp.workorder'].search([
            ('production_id', '=', self.mo_id.id),
            ('state', '=', 'done')
        ], order='sequence desc', limit=1)
        
        if not last_finished_wo:
            raise ValidationError(_("No finished work orders found. Cannot restart MO."))
        
        # Open the restart wizard
        return {
            'type': 'ir.actions.act_window',
            'name': _('Restart Manufacturing Order'),
            'res_model': 'workorder.restart.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_workorder_id': last_finished_wo.id,
                'default_restart_option': 'programming',  # Default to programming
            }
        }
    
    
    def _renumber_wos_to_ops(self, mo, req):
        Workorder = self.env['mrp.workorder']

        # 1) WO order = BOM op order (stable: sequence then id)
        ordered_ids = []
        for r in req.operation_ids.sorted(lambda r: (int(r.sequence or 0), r.id)):
            wo = r.mo_workorder_id
            if wo and wo.exists():
                ordered_ids.append(wo.id)

        # 2) Leftovers (WOs not linked to any op), keep current order
        all_wos = Workorder.search([('production_id', '=', mo.id)], order='sequence,id')
        leftovers = all_wos - Workorder.browse(ordered_ids)

        # 3) Final order = linked first, then leftovers
        final_ids = ordered_ids + leftovers.ids
        final = Workorder.browse(final_ids)
    
        for w in final:
            if w.blocked_by_workorder_ids:
                w.write({'blocked_by_workorder_ids': [(5, 0, 0)]})
        
        # 4) Contiguous 1..N
        seq = 1
        for w in final:
            if w.sequence != seq:
                w.write({'sequence': seq})
            seq += 1

    def _sync_operations_to_mo(self, mo, req, mode='update'):
        """Sync BOM Request operations to MO workorders with attachments.
        Invariants:
        - Sequences come from req.operation_ids (persist them).
        - Preserve any existing done workorders.
        - Knit naming carries 'Attempt X' consistently.
        Modes:
        - create: create all WOs from scratch for a new MO
        - update: align MO to BOM Request ops (no re-insertion gymnastics)
        - reknit: insert a new Knit WO right after the last done Knit (shift tail)
        - reprogram: bump program version counters across MO
        """
        Workorder = self.env['mrp.workorder']
        Routing = self.env['mrp.routing.workcenter']

        # --- helpers --------------------------------------------------------------
        def _is_knit_name(name):
            return bool(name and 'Knit' in name)

        def _compute_current_attempt(wos):
            knit_wos = wos.filtered(lambda w: _is_knit_name(w.name))
            return max(knit_wos.mapped('knit_attempt') or [0]) or 1  # default to 1

        def _prepare_worksheet(op):
            content = op._prepare_worksheet_content(op)
            pdf = op._get_primary_pdf_attachment(op)
            if pdf:
                return {'worksheet': pdf, 'worksheet_type': 'pdf'}
            if content:
                return {'worksheet': content, 'worksheet_type': 'html'}
            return {}

        def _copy_all_attachments(from_op, to_wo):
            for att in from_op.instruction_attachment_ids:
                att.copy({'res_model': 'mrp.workorder', 'res_id': to_wo.id, 'attachment_type': 'instruction'})
            for att in from_op.program_attachment_ids:
                att.copy({'res_model': 'mrp.workorder', 'res_id': to_wo.id, 'attachment_type': 'program'})
            for att in from_op.attachment_ids:
                att.copy({'res_model': 'mrp.workorder', 'res_id': to_wo.id, 'attachment_type': 'general'})

        # --- load once ------------------------------------------------------------
        ts0 = time.time()
        logging.info(" Custom Code:[SYNC_TIMING] _sync_operations_to_mo START mode=%s mo=%s", mode, mo.name)
        existing_wos = Workorder.search([('production_id', '=', mo.id)], order='sequence,id')
        logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — existing_wos search (%d found)", time.time() - ts0, len(existing_wos))
        # --- main logic -----------------------------------------------------------
        if mode == 'create':
            # Clear any auto-generated WOs from _compute_workorder_ids to avoid duplicates
            if existing_wos:
                logging.info(" Custom Code:[MO_SYNC] Clearing %d auto-generated WOs before custom creation", len(existing_wos))
                t_unlink = time.time()
                existing_wos.unlink()
                logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — existing_wos.unlink() done (%.2fs)", time.time() - ts0, time.time() - t_unlink)
            # Clear existing BOM routing lines that were copied from the old BOM,
            # so we can recreate them properly from the template/pricing data
            if req.bom_id.operation_ids:
                logging.info(" Custom Code:[MO_SYNC] Clearing %d existing BOM routing lines", len(req.bom_id.operation_ids))
                t_routing_unlink = time.time()
                req.bom_id.operation_ids.unlink()
                logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — bom routing_lines.unlink() done (%.2fs)", time.time() - ts0, time.time() - t_routing_unlink)

            if req.sale_order_line_id and req.sale_order_line_id.pricing_id:
                # Use operations from SO pricing data
                pricing = req.sale_order_line_id.pricing_id
                logging.info(" Custom Code:[MO_SYNC] Using SO pricing operations for MO %s", mo.name)

                sorted_pricing_ops = pricing.operation_ids.sorted('sequence').filtered(lambda p: p.operation_id)
                if not sorted_pricing_ops:
                    return

                first_pricing_seq = sorted_pricing_ops[0].sequence

                # Pre-fetch all matching shopfloor operations in one query
                t_shop = time.time()
                pricing_op_names = [p.operation_id.name for p in sorted_pricing_ops]
                all_shop_ops = self.env['maeknit.shopfloor.operation'].search([('name', 'in', pricing_op_names)])
                shop_op_map = {s.name.lower(): s for s in all_shop_ops}
                logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — shopfloor ops prefetch done (%.2fs, %d ops)", time.time() - ts0, time.time() - t_shop, len(all_shop_ops))

                routing_vals_list = []
                wo_vals_list = []
                sequence = 10

                for pricing_op in sorted_pricing_ops:
                    operation = pricing_op.operation_id
                    is_knit = _is_knit_name(operation.name)
                    name_final = operation.name
                    state_final = 'ready' if pricing_op.sequence == first_pricing_seq else 'waiting'
                    workcenter_id = pricing_op.workcenter_id.id if pricing_op.workcenter_id else False

                    routing_v = {
                        'name': name_final,
                        'sequence': sequence,
                        'workcenter_id': workcenter_id,
                        'company_id': req.company_id.id,
                        'bom_id': req.bom_id.id,
                    }
                    if pricing_op.expected_minutes:
                        routing_v['time_cycle_manual'] = pricing_op.expected_minutes
                    routing_vals_list.append(routing_v)

                    wo_v = {
                        'production_id': mo.id,
                        'name': name_final,
                        'sequence': sequence,
                        'product_id': mo.product_id.id,
                        'product_uom_id': mo.product_uom_id.id,
                        'qty_production': mo.product_qty,
                        'state': state_final,
                        'workcenter_id': workcenter_id,
                        'duration_expected': pricing_op.expected_minutes or 60.0,
                    }
                    shop_op = shop_op_map.get(name_final.lower())
                    if shop_op:
                        wo_v['shopfloor_operation_id'] = shop_op.id
                    if is_knit:
                        wo_v['knit_attempt'] = 1
                        wo_v['program_version'] = 1
                    if pricing_op.employee_id:
                        wo_v['employee_assigned_ids'] = [(6, 0, [pricing_op.employee_id.id])]
                    wo_vals_list.append(wo_v)
                    sequence += 10

                t_routing_create = time.time()
                if routing_vals_list:
                    Routing.create(routing_vals_list)
                logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — Routing.create(%d) done (%.2fs)", time.time() - ts0, len(routing_vals_list), time.time() - t_routing_create)

                t_wo_create = time.time()
                if wo_vals_list:
                    Workorder.with_context(skip_bom_sync=True, tracking_disable=True).create(wo_vals_list)
                logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — Workorder.create(%d) done (%.2fs)", time.time() - ts0, len(wo_vals_list), time.time() - t_wo_create)

                logging.info(" Custom Code:[MO_SYNC] Created %d WOs from SO pricing for MO %s", len(wo_vals_list), mo.name)
                logging.info(" Custom Code:[SYNC_TIMING] _sync_operations_to_mo TOTAL (pricing path): %.2fs", time.time() - ts0)
                return
            
            # ops = req.operation_ids.sorted('sequence')
            service_name = ""
            bom_request = req
            if bom_request.is_garment_bom:
                service_name = "development"
            elif bom_request.is_swatch_bom:
                service_name = "swatch"
            elif bom_request.is_grading_bom:
                service_name = "grading"
            elif bom_request.is_reverse_bom:
                service_name = "reverse"
            else:
                service_name = "production"
            company_id = self.env.company.id

            t_tmpl_search = time.time()
            default_template = self.env["maeknit.bom.operation.template"].search(
                [("related_service", "=", service_name),
                 ("company_id", "in", [company_id, False]),
                ],
                limit=1
            )
            logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — template search done (%.2fs, service=%s)", time.time() - ts0, time.time() - t_tmpl_search, service_name)

            if not default_template or not default_template.line_ids:
                logging.info(" Custom Code:[MO_SYNC] No template or SO pricing data found, skipping operation creation")
                return

            logging.info(" Custom Code:[MO_SYNC] Using operation template as fallback (no SO pricing data)")
            ops = default_template.line_ids.sorted('sequence')

            initial_attempt = 1
            program_version = 1
            first_seq = ops[0].sequence
            gauge_id = getattr(self, 'gauge_id', False)

            # Pre-fetch target employees once (case-insensitive match)
            t_emp = time.time()
            kadri = self.env['hr.employee'].search([('name', 'ilike', 'Kadri')], limit=1)
            mallory = self.env['hr.employee'].search([('name', 'ilike', 'Mallory')], limit=1)
            sevan = self.env['hr.employee'].search([('name', 'ilike', 'Sevan')], limit=1)
            logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — employee prefetch done (%.2fs)", time.time() - ts0, time.time() - t_emp)

            # Pre-fetch all matching shopfloor operations in one query
            t_shop2 = time.time()
            tmpl_op_names = [line.operation_id.name for line in ops if line.operation_id]
            all_shop_ops = self.env['maeknit.shopfloor.operation'].search([('name', 'in', tmpl_op_names)])
            shop_op_map = {s.name.lower(): s for s in all_shop_ops}
            logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — shopfloor ops prefetch done (%.2fs, %d ops)", time.time() - ts0, time.time() - t_shop2, len(all_shop_ops))

            # Cache workcenter lookups by tag_ids tuple to avoid repeated DB queries
            wc_cache = {}
            routing_vals_list = []
            wo_vals_list = []
            t_loop = time.time()

            for line in ops:
                operation = line.operation_id
                if not operation:
                    continue
                is_knit = _is_knit_name(operation.name)
                name_final = operation.name
                state_final = 'ready' if line.sequence == first_seq else 'waiting'

                tag_key = tuple(sorted(operation.workcenter_tag_ids.ids))
                if tag_key not in wc_cache:
                    t_wc = time.time()
                    wc_cache[tag_key] = self._filter_workcenters_by_tags_and_gauge(
                        operation.workcenter_tag_ids.ids, gauge_id
                    )
                    logging.info(" Custom Code:[SYNC_TIMING] workcenter filter for tags=%s: %.2fs (cache miss)", tag_key, time.time() - t_wc)
                filtered_wcs = wc_cache[tag_key]
                workcenter_id = filtered_wcs and filtered_wcs[0].id or False

                routing_v = {
                    'name': name_final,
                    'sequence': line.sequence,
                    'workcenter_id': workcenter_id,
                    'company_id': company_id,
                    'bom_id': self.bom_id.id,
                }
                if hasattr(line, 'time_cycle_manual') and line.time_cycle_manual:
                    routing_v['time_cycle_manual'] = line.time_cycle_manual
                routing_vals_list.append(routing_v)

                wo_v = {
                    'production_id': mo.id,
                    'name': name_final,
                    'sequence': line.sequence,
                    'product_id': mo.product_id.id,
                    'product_uom_id': mo.product_uom_id.id,
                    'qty_production': mo.product_qty,
                    'state': state_final,
                    'workcenter_id': workcenter_id,
                }
                shop_op = shop_op_map.get(name_final.lower())
                if shop_op:
                    wo_v['shopfloor_operation_id'] = shop_op.id
                if is_knit:
                    wo_v['knit_attempt'] = initial_attempt
                    wo_v['program_version'] = program_version

                # Assign default employees based on operation name
                assigned_ids = []
                if 'program' in operation.name.lower() and kadri:
                    assigned_ids.append(kadri.id)
                elif 'knit' in operation.name.lower():
                    if mallory:
                        assigned_ids.append(mallory.id)
                    if sevan:
                        assigned_ids.append(sevan.id)
                line_user_ids = line.user_ids.ids or []

                final_employee_ids = line_user_ids or assigned_ids
                if final_employee_ids:
                    wo_v['employee_assigned_ids'] = [(6, 0, final_employee_ids)]
                wo_vals_list.append(wo_v)

            logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — ops loop done (%.2fs, %d routing, %d wo, %d wc cache hits avoided)", time.time() - ts0, time.time() - t_loop, len(routing_vals_list), len(wo_vals_list), len(wc_cache))

            t_routing_create2 = time.time()
            if routing_vals_list:
                Routing.create(routing_vals_list)
            logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — Routing.create(%d) done (%.2fs)", time.time() - ts0, len(routing_vals_list), time.time() - t_routing_create2)

            t_wo_create2 = time.time()
            if wo_vals_list:
                Workorder.with_context(skip_bom_sync=True, tracking_disable=True).create(wo_vals_list)
            logging.info(" Custom Code:[SYNC_TIMING] +%.2fs — Workorder.create(%d) done (%.2fs)", time.time() - ts0, len(wo_vals_list), time.time() - t_wo_create2)

            logging.info(" Custom Code:[MO_SYNC] Created %d WOs from template for MO %s", len(wo_vals_list), mo.name)
            logging.info(" Custom Code:[SYNC_TIMING] _sync_operations_to_mo TOTAL (template path): %.2fs", time.time() - ts0)

        
        elif mode == 'update':
            Workorder = self.env['mrp.workorder']
            wos = Workorder.search([('production_id', '=', mo.id)], order='sequence,id')

            ops = req.operation_ids.sorted('sequence')
            if not ops:
                return
            for op in ops:
                is_knit = _is_knit_name(op.name)
                worksheet_vals = _prepare_worksheet(op)
                knit_attempt = (op.knit_attempt or 1) if is_knit else False
                program_version = (op.program_version or 1) if is_knit else False

                name_final = f"{op.name}" if is_knit else op.name
                seq = max(1, int(op.sequence or 0))
                base_vals = {
                    'production_id': mo.id,
                    'name': name_final,
                    'workcenter_id': op.workcenter_id.id,
                    'duration_expected': op.time_cycle,
                    'sequence': seq,                  
                    'product_id': mo.product_id.id,
                    'product_uom_id': mo.product_uom_id.id,
                    'qty_production': mo.product_qty,
                }
                logging.info(" Custom Code:Syncing WO for OP %s: base_vals=%s", op.name, base_vals)

                logging.info(" Custom Code:Syncing WO for OP %s: base_vals=%s", op.name, base_vals)
                if is_knit:
                    logging.info('Update attempt: %s', knit_attempt)
                    logging.info('Update program version: %s', program_version)
                    base_vals['knit_attempt'] = knit_attempt
                    base_vals['program_version'] = program_version
                if op.employee_assigned_ids:
                    base_vals['employee_assigned_ids'] = [(6, 0, op.employee_assigned_ids.ids)]  # fix: was vals

                target_wo = op.mo_workorder_id if (op.mo_workorder_id and op.mo_workorder_id.exists()) else False

                if target_wo:
                    logging.info(" Custom Code:Syncing WO for OP %s: target_wo=%s", op.name, target_wo.id)
                    logging.info(" Custom Code:base_vals SQ: %s", base_vals)
                    logging.info(" Custom Code:worksheet_vals SQ: %s", worksheet_vals)
                    target_wo.with_context(skip_bom_sync=True).write({**base_vals, **worksheet_vals})
                else:
                    knit_wos = existing_wos.filtered(lambda w: _is_knit_name(w.name))
                    done_knit_wos = knit_wos.filtered(lambda w: w.state == 'done').sorted('sequence')
                    last_knit = knit_wos and knit_wos[-1] or False

                    pivot_wo = False
                    if done_knit_wos:
                        pivot_wo = done_knit_wos[-1]
                    elif knit_wos:
                        pivot_wo = knit_wos.sorted('sequence')[0]
                        if pivot_wo.state != 'done':
                            pivot_wo.write({'state': 'done'})
                    else:
                        pivot_wo = existing_wos[-1] if existing_wos else False

                    insertion_seq = (pivot_wo.sequence if pivot_wo else 0) + 1

                    # shift tail
                    tail_wos = existing_wos.filtered(lambda w: w.sequence >= insertion_seq).sorted(
                        reverse=True, key=lambda w: w.sequence
                    )
                    for tw in tail_wos:
                        tw.write({'sequence': tw.sequence + 1})

                    # base Knit op = last Knit op in BOM Request
                    knit_ops = req.operation_ids.filtered(lambda o: _is_knit_name(o.name)).sorted('sequence')
                    base_knit_op = knit_ops and knit_ops[-1] or False
                    if not base_knit_op:
                        return  # nothing to insert

                    vals = {
                        'production_id': mo.id,
                        'name': f"{base_knit_op.name}",
                        'duration_expected': base_knit_op.time_cycle,
                        'sequence': insertion_seq,
                        'product_id': mo.product_id.id,
                        'product_uom_id': mo.product_uom_id.id,
                        'qty_production': mo.product_qty,
                        'state': 'ready',
                        'knit_attempt': knit_attempt,
                        'program_version': program_version,
                    }
                    
                    if base_knit_op.employee_assigned_ids:
                        vals['employee_assigned_ids'] = [(6, 0, base_knit_op.employee_assigned_ids.ids)]
                    
                    vals.update(_prepare_worksheet(base_knit_op))

                    new_wo = Workorder.with_context(skip_bom_sync=True).create(vals)
                    base_knit_op.write({'mo_workorder_id': new_wo.id})

                    # everything strictly after becomes waiting (unless done)
                    tail_after = Workorder.search([('production_id', '=', mo.id), ('sequence', '>', insertion_seq)])
                    for w in tail_after:
                        if w.state in ('ready', 'pending', 'waiting'):
                            w.write({'state': 'waiting'})
                    return new_wo.id
            
            
            # self._renumber_wos_to_ops(mo, req)
            self.env.cr.flush()
            self.env.invalidate_all()   
                        
        elif mode == 'reknit':
            # pick pivot = last done Knit, else first Knit (force to done), else last WO
            knit_wos = existing_wos.filtered(lambda w: _is_knit_name(w.name))
            done_knit_wos = knit_wos.filtered(lambda w: w.state == 'done').sorted('sequence')
            last_knit = knit_wos and knit_wos[-1] or False

            pivot_wo = False
            if done_knit_wos:
                pivot_wo = done_knit_wos[-1]
            elif knit_wos:
                pivot_wo = knit_wos.sorted('sequence')[0]
                if pivot_wo.state != 'done':
                    pivot_wo.write({'state': 'done'})
            else:
                pivot_wo = existing_wos[-1] if existing_wos else False

            insertion_seq = (pivot_wo.sequence if pivot_wo else 0) + 1

            # shift tail
            tail_wos = existing_wos.filtered(lambda w: w.sequence >= insertion_seq).sorted(
                reverse=True, key=lambda w: w.sequence
            )
            for tw in tail_wos:
                tw.write({'sequence': tw.sequence + 1})

            # base Knit op = last Knit op in BOM Request
            knit_ops = req.operation_ids.filtered(lambda o: _is_knit_name(o.name)).sorted('sequence')
            base_knit_op = knit_ops and knit_ops[-1] or False
            if not base_knit_op:
                return  # nothing to insert

            # new attempt = last_knit.knit_attempt + 1 else 1
            new_attempt = (last_knit.knit_attempt + 1) if last_knit and last_knit.knit_attempt else 1
            program_version = last_knit.program_version if last_knit and last_knit.program_version else (req.program_version or 1)

            vals = {
                'production_id': mo.id,
                'name': f"{base_knit_op.name}",
                'duration_expected': base_knit_op.time_cycle,
                'sequence': insertion_seq,
                'product_id': mo.product_id.id,
                'product_uom_id': mo.product_uom_id.id,
                'qty_production': mo.product_qty,
                'state': 'ready',
                'knit_attempt': new_attempt,
                'program_version': program_version,
            }
            
            if base_knit_op.employee_assigned_ids:
                vals['employee_assigned_ids'] = [(6, 0, base_knit_op.employee_assigned_ids.ids)]
            
            vals.update(_prepare_worksheet(base_knit_op))

            new_wo = Workorder.with_context(skip_bom_sync=True).create(vals)
            base_knit_op.write({'mo_workorder_id': new_wo.id})

            # everything strictly after becomes waiting (unless done)
            tail_after = Workorder.search([('production_id', '=', mo.id), ('sequence', '>', insertion_seq)])
            for w in tail_after:
                if w.state in ('ready', 'pending', 'waiting'):
                    w.write({'state': 'waiting'})
            return new_wo.id
        # Step 1
        elif mode == 'reprogram':
            Workorder = self.env['mrp.workorder']
            wos = Workorder.search([('production_id', '=', mo.id)], order='sequence,id')
            open_wos = wos.filtered(lambda w: w.state != 'done')
            for w in open_wos:
                w.write({
                    'blocked_by_workorder_ids': [(5, 0, 0)],
                    'state': 'pending',
                })
            logging.info(" Custom Code:[REPROGRAM] Forced %d open WOs to pending", len(open_wos))

    def _filter_workcenters_by_tags_and_gauge(self, tag_ids, gauge_id):
        """Return workcenters that share at least one tag with the operation, with optional gauge filter for Knit/Link ops."""
        Workcenter = self.env['mrp.workcenter']
        company_id = self.env.company.id

        if not tag_ids:
            return Workcenter.search([('company_id', '=', company_id)], order='sequence,id')

        domain = [('company_id', '=', company_id), ('tag_ids', 'in', tag_ids)]

        # Apply gauge filter when any of the operation's tags relate to knitting or linking
        knit_link_tag_names = {'knitting machine', 'linking machine'}
        op_tags = self.env['mrp.workcenter.tag'].browse(tag_ids)
        use_gauge_filter = any(t.name.lower() in knit_link_tag_names for t in op_tags)

        if use_gauge_filter and gauge_id and gauge_id.exists():
            wc_with_gauge = Workcenter.search(domain + [('gauge_ids', 'in', [gauge_id.id])], order='sequence,id')
            if wc_with_gauge:
                logging.info(" Custom Code:[WORKCENTER_FILTER] Found match with gauge %s → %s", gauge_id.display_name, wc_with_gauge.mapped('name'))
                return wc_with_gauge
            logging.info(" Custom Code:[WORKCENTER_FILTER] Gauge %s not matched, fallback to tag-only", gauge_id.display_name)

        workcenters = Workcenter.search(domain, order='sequence,id')
        logging.info(" Custom Code:[WORKCENTER_FILTER] tags=%s | gauge=%s | result=%s",
            tag_ids, gauge_id.display_name if gauge_id and gauge_id.exists() else None, workcenters.mapped('name'))
        return workcenters
        
    def action_draft(self):
        """Draft BOM request"""
        self.write({'state': 'draft'})

    def action_reset_to_draft(self):
        """Reset to draft state"""
        self.write({'state': 'draft'})

    def action_view_mo(self):
        """Open related Manufacturing Order"""
        self.ensure_one()
        if not self.mo_id:
            return
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'res_id': self.mo_id.id,
            'view_mode': 'form',
            'name': f'Manufacturing Order - {self.mo_id.name}',
        }
    
    def action_view_bom(self):
        """Open referenced BOM"""
        self.ensure_one()
        if not self.bom_id:
            return
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.bom',
            'res_id': self.bom_id.id,
            'view_mode': 'form',
            'name': f'BOM - {self.bom_id.display_name}',
        }

    def action_open_attachment_wizard(self):
        """Open attachment wizard for operations"""
        self.ensure_one()
        return {
            'name': 'Add Operation Attachments',
            'type': 'ir.actions.act_window',
            'res_model': 'operation.attachment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_bom_request_id': self.id,
            }
        }

    def action_manage_client_files(self):
        """Open client attachment wizard"""
        self.ensure_one()
        return {
            'name': 'Manage Client Files',
            'type': 'ir.actions.act_window',
            'res_model': 'client.attachment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_bom_request_id': self.id,
            }
        }

    @api.depends('sale_order_id', 'sale_order_line_id')
    def _compute_project_task_id(self):
        logging.info(" Custom Code:Computing project task")
        logging.info('sale_order_id: %s', self.sale_order_id)
        logging.info('sale_order_line_id: %s', self.sale_order_line_id)
        Task = self.env['project.task']
        SaleOrderLine = self.env['sale.order.line']
        ProjectTask = self.env['project.task']
        for rec in self:
            main_task = False
            if not rec.sale_order_id:
                rec.project_task_id = False
                continue

            project = False
            # 1) Best: project linked to this SOL
            if rec.sale_order_line_id:
                try:
                    # Safely browse and check existence
                    sale_line = SaleOrderLine.browse(rec.sale_order_line_id.id)
                    if sale_line.exists() and hasattr(sale_line, 'project_id') and sale_line.project_id:
                        project = sale_line.project_id
                except Exception as e:
                    logging.info(f" Custom Code: Error accessing project from sale order line: {e}")
                    project = False
            
            logging.info(f" Custom Code: Logging - Project: {project}")
            # 2) Fallback: project linked to this SO
            if project:
                # Find the main task (parent_id is False) within this project
                main_task = ProjectTask.search([('project_id', '=', project.id), ('parent_id', '=', False)], limit=1)
            
            logging.info(f" Custom Code: Logging - Main Task: {main_task}")
            rec.project_task_id = main_task.id if main_task else False
                
    @api.depends('project_task_id')
    def _compute_sub_task_count(self):
        """Compute the number of sub-tasks"""
        for record in self:
            if record.project_task_id:
                # Count tasks where parent_id is the project_task_id of the BOM Request
                record.sub_task_count = self.env['project.task'].search_count([
                    ('parent_id', '=', record.project_task_id.id)
                ])
            else:
                record.sub_task_count = 0

    def action_view_sub_tasks(self):
        """Open sub-tasks view"""
        self.ensure_one()
        # Ensure project_task_id exists before trying to open its subtasks
        if not self.project_task_id:
            raise ValidationError("No main project task found for this BOM Request.")
        
        return {
            'name': f'Sub Tasks - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('parent_id', '=', self.project_task_id.id)],
            'context': {
                'default_parent_id': self.project_task_id.id,
                'default_project_id': self.project_task_id.project_id.id if self.project_task_id else False,
                'default_partner_id': self.partner_id.id,
            }
        }
    
    def action_view_delivery(self):
        """Open sub-tasks view"""
        self.ensure_one()
        if not self.sale_order_id:
            return
        return self.sale_order_id.action_view_delivery()

    def action_add_to_grading(self):
        """Open Grading Wizard to create grading BOMs"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add to Grading'),
            'res_model': 'grading.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
            }
        }



    @api.depends('excalidraw_data', 'excalidraw_file_ids')
    def _compute_excalidraw_data_with_images(self):
        """Prepare data with image URLs (not base64) for widget to fetch separately"""
        for record in self:
            if not record.excalidraw_data:
                record.excalidraw_data_with_images = {'elements': [], 'appState': {}, 'files': {}, 'fileIds': {}}
                continue
            
            # Handle both dict and string formats
            try:
                if isinstance(record.excalidraw_data, str):
                    data = json.loads(record.excalidraw_data)
                elif isinstance(record.excalidraw_data, dict):
                    data = dict(record.excalidraw_data)
                else:
                    record.excalidraw_data_with_images = {'elements': [], 'appState': {}, 'files': {}, 'fileIds': {}}
                    continue
            except (ValueError, TypeError, json.JSONDecodeError):
                record.excalidraw_data_with_images = {'elements': [], 'appState': {}, 'files': {}, 'fileIds': {}}
                continue
            
            # Include fileIds map so widget knows which attachments to fetch
            file_ids_map = data.get('fileIds', {})
            
            logging.info(f" Custom Code: [Excalidraw] Prepared data with {len(file_ids_map)} image IDs for {record.name}")
            
            # Return lightweight data with fileIds, widget will fetch images via URLs
            record.excalidraw_data_with_images = {
                'elements': data.get('elements', []),
                'appState': data.get('appState', {}),
                'files': {},  # Empty - widget fetches via URLs
                'fileIds': file_ids_map,  # Attachment ID mapping
            }

    @api.depends('garment_construction_data', 'garment_construction_file_ids')
    def _compute_garment_construction_data_with_images(self):
        """Prepare garment construction data with image URLs for widget to fetch separately"""
        for record in self:
            if not record.garment_construction_data:
                record.garment_construction_data_with_images = {'elements': [], 'appState': {}, 'files': {}, 'fileIds': {}}
                continue

            try:
                if isinstance(record.garment_construction_data, str):
                    data = json.loads(record.garment_construction_data)
                elif isinstance(record.garment_construction_data, dict):
                    data = dict(record.garment_construction_data)
                else:
                    record.garment_construction_data_with_images = {'elements': [], 'appState': {}, 'files': {}, 'fileIds': {}}
                    continue
            except (ValueError, TypeError, json.JSONDecodeError):
                record.garment_construction_data_with_images = {'elements': [], 'appState': {}, 'files': {}, 'fileIds': {}}
                continue

            file_ids_map = data.get('fileIds', {})

            logging.info(f" Custom Code: [Garment Construction] Prepared data with {len(file_ids_map)} image IDs for {record.name}")

            record.garment_construction_data_with_images = {
                'elements': data.get('elements', []),
                'appState': data.get('appState', {}),
                'files': {},
                'fileIds': file_ids_map,
            }

    def _split_garment_construction_files(self, vals):
        """
        Extract images from Garment Construction Excalidraw and store as attachments.
        Same pattern as _split_excalidraw_files but for garment_construction_data field.
        """
        gc_data = vals.get('garment_construction_data')

        if not gc_data:
            return vals

        if isinstance(gc_data, str):
            try:
                gc_data = json.loads(gc_data)
            except json.JSONDecodeError:
                logging.error(f"Failed to parse Garment Construction JSON data")
                return vals

        existing_file_ids = {}
        if self and self.garment_construction_data:
            try:
                if isinstance(self.garment_construction_data, dict):
                    existing_file_ids = self.garment_construction_data.get('fileIds', {})
                elif isinstance(self.garment_construction_data, str):
                    db_data = json.loads(self.garment_construction_data)
                    existing_file_ids = db_data.get('fileIds', {})
            except (json.JSONDecodeError, AttributeError):
                existing_file_ids = {}
        if existing_file_ids and not gc_data.get('files'):
            logging.info(f" Custom Code: Garment Construction data already processed with {len(existing_file_ids)} attachment IDs, skipping")
            return vals

        files = gc_data.get('files', {})

        if not files:
            lightweight_data = {
                'elements': gc_data.get('elements', []),
                'appState': gc_data.get('appState', {}),
                'fileIds': existing_file_ids,
            }
            vals['garment_construction_data'] = lightweight_data
            return vals

        logging.info(f" Custom Code: Processing {len(files)} Garment Construction images")

        attachment_ids_to_link = []
        file_ids_map = dict(existing_file_ids)

        for file_id, file_data in files.items():
            if file_id in existing_file_ids:
                existing_attachment_id = existing_file_ids[file_id]
                attachment_ids_to_link.append(existing_attachment_id)
                continue

            data_url = None
            mime_type = 'image/png'

            if isinstance(file_data, dict):
                data_url = file_data.get('dataURL') or file_data.get('dataUrl')
                mime_type = file_data.get('mimeType', mime_type)
            elif isinstance(file_data, str):
                data_url = file_data

            if not data_url or not isinstance(data_url, str) or not data_url.startswith('data:image'):
                continue

            try:
                if ',' in data_url:
                    header, base64_data = data_url.split(',', 1)

                    extension = 'png'
                    if 'jpeg' in header.lower() or 'jpg' in header.lower():
                        extension = 'jpg'
                    elif 'gif' in header.lower():
                        extension = 'gif'
                    elif 'svg' in header.lower():
                        extension = 'svg'

                    attachment = self.env['ir.attachment'].create({
                        'name': f'garment_construction_{file_id[:8]}.{extension}',
                        'res_model': 'maeknit.bom.request',
                        'type': 'binary',
                        'datas': base64_data,
                        'mimetype': mime_type,
                        'attachment_type': 'sketch',
                    })

                    attachment_ids_to_link.append(attachment.id)
                    file_ids_map[file_id] = attachment.id

            except Exception as e:
                logging.error(f"Failed to create attachment for garment construction file {file_id}: {e}")

        lightweight_data = {
            'elements': gc_data.get('elements', []),
            'appState': gc_data.get('appState', {}),
            'fileIds': file_ids_map,
        }

        vals['garment_construction_data'] = lightweight_data

        if attachment_ids_to_link:
            vals['garment_construction_file_ids'] = [(6, 0, attachment_ids_to_link)]

        return vals

    def _split_structure_cad_files(self, vals):
        """
        Extract images from Structure CAD Excalidraw data and store as ir.attachment records.
        Identical pattern to _split_garment_construction_files — stores fileIds instead of dataURL.
        Controller already looks up 'structure_cad_data' for fileIds to serve images.
        """
        raw = vals.get('structure_cad_data')
        if not raw:
            return vals

        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logging.error("Failed to parse structure_cad_data JSON")
                return vals
        elif isinstance(raw, dict):
            data = dict(raw)
        else:
            return vals

        # Read existing fileIds from DB to avoid duplicate attachments
        existing_file_ids = {}
        if self and self.structure_cad_data:
            try:
                existing = json.loads(self.structure_cad_data) if isinstance(self.structure_cad_data, str) else self.structure_cad_data
                existing_file_ids = existing.get('fileIds', {}) if isinstance(existing, dict) else {}
            except (json.JSONDecodeError, AttributeError):
                existing_file_ids = {}

        if existing_file_ids and not data.get('files'):
            # Already processed, no new raw files — keep as-is
            vals['structure_cad_data'] = json.dumps({
                'elements': data.get('elements', []),
                'appState': data.get('appState', {}),
                'fileIds': existing_file_ids,
            })
            return vals

        files = data.get('files', {})
        file_ids_map = dict(existing_file_ids)
        # Preserve fileIds already embedded in incoming data (e.g. extracted by MO pre-write)
        for fid, att_id in data.get('fileIds', {}).items():
            if fid not in file_ids_map:
                file_ids_map[fid] = att_id

        for file_id, file_data in (files or {}).items():
            if file_id in existing_file_ids:
                continue
            data_url = file_data.get('dataURL') or file_data.get('dataUrl') if isinstance(file_data, dict) else file_data
            mime_type = file_data.get('mimeType', 'image/png') if isinstance(file_data, dict) else 'image/png'
            if not data_url or not isinstance(data_url, str) or not data_url.startswith('data:image'):
                continue
            if ',' not in data_url:
                continue
            header, b64 = data_url.split(',', 1)
            ext = 'jpg' if ('jpeg' in header or 'jpg' in header) else ('gif' if 'gif' in header else ('svg' if 'svg' in header else 'png'))
            try:
                att = self.env['ir.attachment'].create({
                    'name': f'structure_cad_{file_id[:8]}.{ext}',
                    'res_model': 'maeknit.bom.request',
                    'type': 'binary',
                    'datas': b64,
                    'mimetype': mime_type,
                    'attachment_type': 'sketch',
                })
                file_ids_map[file_id] = att.id
                logging.info("[STRUCT_CAD] Extracted file %s → attachment %s", file_id[:8], att.id)
            except Exception as e:
                logging.error("[STRUCT_CAD] Failed to create attachment for file %s: %s", file_id, e)

        vals['structure_cad_data'] = json.dumps({
            'elements': data.get('elements', []),
            'appState': data.get('appState', {}),
            'fileIds': file_ids_map,
        })
        return vals

    def _process_artwork_data(self, vals):
        """
        Extract base64 images from artwork_data items and store as ir.attachment.
        Format: {"items": [{"filename": "...", "data": "data:image/..."}, ...]}
        After extraction: {"items": [{"filename": "...", "attachment_id": 123}, ...]}
        """
        raw = vals.get('artwork_data')
        if not raw:
            return vals

        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logging.error("Failed to parse artwork_data JSON")
                return vals
        elif isinstance(raw, dict):
            data = dict(raw)
        else:
            return vals

        items = data.get('items', [])
        changed = False
        for item in items:
            if not isinstance(item, dict):
                continue
            img = item.get('data', '')
            if not isinstance(img, str) or not img.startswith('data:image'):
                continue
            if ',' not in img:
                continue
            header, b64 = img.split(',', 1)
            mime_type = 'image/png'
            ext = 'png'
            if 'jpeg' in header or 'jpg' in header:
                mime_type, ext = 'image/jpeg', 'jpg'
            elif 'gif' in header:
                mime_type, ext = 'image/gif', 'gif'
            elif 'svg' in header:
                mime_type, ext = 'image/svg+xml', 'svg'
            try:
                att = self.env['ir.attachment'].create({
                    'name': item.get('filename', f'artwork.{ext}'),
                    'res_model': 'maeknit.bom.request',
                    'res_id': self.id if self else 0,
                    'type': 'binary',
                    'datas': b64,
                    'mimetype': mime_type,
                })
                item['attachment_id'] = att.id
                item['data'] = f'/web/image/{att.id}'  # URL replaces base64 — widget img src still works
                changed = True
                logging.info("[ARTWORK] Extracted '%s' → attachment %s", item.get('filename'), att.id)
            except Exception as e:
                logging.error("[ARTWORK] Failed to create attachment for '%s': %s", item.get('filename'), e)

        if changed:
            vals['artwork_data'] = json.dumps(data)
        return vals

    def _split_excalidraw_files(self, vals):
        """
        Extract images from Excalidraw and store as attachments (same pattern as calibration).
        Updates excalidraw_data to reference attachment IDs instead of storing base64.
        Prevents duplicates by checking if attachment already exists in the DATABASE.
        """
        excalidraw_data = vals.get('excalidraw_data')
        
        if not excalidraw_data:
            return vals
        
        # Ensure excalidraw_data is a dictionary
        if isinstance(excalidraw_data, str):
            try:
                excalidraw_data = json.loads(excalidraw_data)
            except json.JSONDecodeError:
                logging.error(f"Failed to parse Excalidraw JSON data")
                return vals
        
        # Get existing fileIds from DATABASE record, not from incoming data
        # (incoming data has base64 images we injected, but empty fileIds)
        existing_file_ids = {}
        if self and self.excalidraw_data:
            try:
                if isinstance(self.excalidraw_data, dict):
                    existing_file_ids = self.excalidraw_data.get('fileIds', {})
                elif isinstance(self.excalidraw_data, str):
                    db_data = json.loads(self.excalidraw_data)
                    existing_file_ids = db_data.get('fileIds', {})
            except (json.JSONDecodeError, AttributeError):
                existing_file_ids = {}
        if existing_file_ids and not excalidraw_data.get('files'):
            logging.info(f" Custom Code: Excalidraw data already processed with {len(existing_file_ids)} attachment IDs, skipping")
            return vals
        
        # Extract 'files' which contain base64 image data
        files = excalidraw_data.get('files', {})
        
        if not files:
            # No new files to process, keep existing fileIds
            lightweight_data = {
                'elements': excalidraw_data.get('elements', []),
                'appState': excalidraw_data.get('appState', {}),
                'fileIds': existing_file_ids,
            }
            vals['excalidraw_data'] = lightweight_data
            return vals
        
        logging.info(f" Custom Code: Processing {len(files)} Excalidraw images")
        
        attachment_ids_to_link = []
        file_ids_map = dict(existing_file_ids)  # Start with existing IDs
        
        for file_id, file_data in files.items():
            # Skip if attachment already exists for this file_id
            if file_id in existing_file_ids:
                existing_attachment_id = existing_file_ids[file_id]
                logging.info(f" Custom Code: Skipping file {file_id[:8]} - attachment {existing_attachment_id} already exists")
                attachment_ids_to_link.append(existing_attachment_id)
                continue
            
            # Extract dataURL
            data_url = None
            mime_type = 'image/png'
            
            if isinstance(file_data, dict):
                data_url = file_data.get('dataURL') or file_data.get('dataUrl')
                mime_type = file_data.get('mimeType', mime_type)
            elif isinstance(file_data, str):
                data_url = file_data
            
            # Process only valid image data URLs
            if not data_url or not isinstance(data_url, str) or not data_url.startswith('data:image'):
                continue
            
            try:
                # Parse data URL to extract base64 data
                if ',' in data_url:
                    header, base64_data = data_url.split(',', 1)
                    
                    # Determine extension
                    extension = 'png'
                    if 'jpeg' in header.lower() or 'jpg' in header.lower():
                        extension = 'jpg'
                    elif 'gif' in header.lower():
                        extension = 'gif'
                    elif 'svg' in header.lower():
                        extension = 'svg'
                    
                    # Create attachment
                    attachment = self.env['ir.attachment'].create({
                        'name': f'excalidraw_{file_id[:8]}.{extension}',
                        'res_model': 'maeknit.bom.request',
                        'type': 'binary',
                        'datas': base64_data,
                        'mimetype': mime_type,
                        'attachment_type': 'sketch',
                    })
                    
                    attachment_ids_to_link.append(attachment.id)
                    file_ids_map[file_id] = attachment.id  # Simple ID mapping
                    
                    logging.info(f" Custom Code: Created attachment {attachment.id} for file {file_id[:8]}")
                    
            except Exception as e:
                logging.error(f"Failed to create attachment for file {file_id}: {e}")
        
        # Construct lightweight data (no base64 images, only IDs)
        lightweight_data = {
            'elements': excalidraw_data.get('elements', []),
            'appState': excalidraw_data.get('appState', {}),
            'fileIds': file_ids_map,  # Simple map: fileId -> attachmentId
        }
        
        # Calculate size reduction
        old_size = len(json.dumps(excalidraw_data))
        new_size = len(json.dumps(lightweight_data))
        reduction = ((old_size - new_size) / old_size * 100) if old_size > 0 else 0
        
        logging.info(f" Custom Code: Excalidraw: {old_size/1024:.1f}KB → {new_size/1024:.1f}KB ({reduction:.1f}% reduction)")
        
        # Update vals
        vals['excalidraw_data'] = lightweight_data
        
        if attachment_ids_to_link:
            vals['excalidraw_file_ids'] = [(6, 0, attachment_ids_to_link)]
        
        return vals

    def _process_whole_cad_image(self, vals):
        """
        Extract image from Whole CAD data and store as attachment.
        Updates whole_cad_data to reference attachment ID instead of storing base64.
        """
        whole_cad_data = vals.get('whole_cad_data')
        
        if not whole_cad_data:
            return vals
        
        # Ensure whole_cad_data is a dictionary
        if isinstance(whole_cad_data, str):
            try:
                whole_cad_data = json.loads(whole_cad_data)
            except json.JSONDecodeError:
                logging.error(f"Failed to parse Whole CAD JSON data")
                return vals
        
        # Extract image field
        image_data = whole_cad_data.get('image')
        
        # If no image or already has attachment ID, skip
        if not image_data:
            return vals
        
        # Check if already processed (has image_attachment_id but no image data URL)
        if whole_cad_data.get('image_attachment_id') and not image_data.startswith('data:image'):
            logging.info(" Custom Code:Whole CAD image already processed, skipping")
            return vals
        
        # Process only valid image data URLs
        if not isinstance(image_data, str) or not image_data.startswith('data:image'):
            return vals
        
        try:
            # Parse data URL to extract base64 data
            if ',' in image_data:
                header, base64_data = image_data.split(',', 1)
                
                # Determine extension and mime type
                mime_type = 'image/png'
                extension = 'png'
                if 'jpeg' in header.lower() or 'jpg' in header.lower():
                    extension = 'jpg'
                    mime_type = 'image/jpeg'
                elif 'gif' in header.lower():
                    extension = 'gif'
                    mime_type = 'image/gif'
                elif 'svg' in header.lower():
                    extension = 'svg'
                    mime_type = 'image/svg+xml'
                
                # Delete old attachment if exists
                if self and self.whole_cad_image_id:
                    old_attachment = self.whole_cad_image_id
                    logging.info(f" Custom Code: Deleting old Whole CAD image attachment {old_attachment.id}")
                    old_attachment.unlink()
                
                # Create new attachment
                attachment = self.env['ir.attachment'].create({
                    'name': f'whole_cad_image.{extension}',
                    'res_model': 'maeknit.bom.request',
                    'res_id': self.id if self else False,
                    'type': 'binary',
                    'datas': base64_data,
                    'mimetype': mime_type,
                })
                
                # Calculate size reduction
                old_size = len(json.dumps(whole_cad_data))
                
                # Update data structure to reference attachment
                whole_cad_data['image_attachment_id'] = attachment.id
                del whole_cad_data['image']  # Remove base64 data
                
                new_size = len(json.dumps(whole_cad_data))
                reduction = ((old_size - new_size) / old_size * 100) if old_size > 0 else 0
                
                logging.info(f" Custom Code: Whole CAD: {old_size/1024:.1f}KB → {new_size/1024:.1f}KB ({reduction:.1f}% reduction)")
                logging.info(f" Custom Code: Created Whole CAD image attachment {attachment.id}")
                
                # Update vals
                vals['whole_cad_data'] = whole_cad_data
                vals['whole_cad_image_id'] = attachment.id
                
        except Exception as e:
            logging.error(f"Failed to process Whole CAD image: {e}")

        return vals

    def _process_cad_pom_image(self, vals):
        """
        Extract image from CAD & POM data and store as attachment.
        Same pattern as _process_whole_cad_image but for cad_pom_data field.
        """
        cad_pom_data = vals.get('cad_pom_data')

        if not cad_pom_data:
            return vals

        if isinstance(cad_pom_data, str):
            try:
                cad_pom_data = json.loads(cad_pom_data)
            except json.JSONDecodeError:
                logging.error(f"Failed to parse CAD & POM JSON data")
                return vals

        image_data = cad_pom_data.get('image')

        if not image_data:
            return vals

        if cad_pom_data.get('image_attachment_id') and not image_data.startswith('data:image'):
            return vals

        if not isinstance(image_data, str) or not image_data.startswith('data:image'):
            return vals

        try:
            if ',' in image_data:
                header, base64_data = image_data.split(',', 1)

                mime_type = 'image/png'
                extension = 'png'
                if 'jpeg' in header.lower() or 'jpg' in header.lower():
                    extension = 'jpg'
                    mime_type = 'image/jpeg'
                elif 'gif' in header.lower():
                    extension = 'gif'
                    mime_type = 'image/gif'
                elif 'svg' in header.lower():
                    extension = 'svg'
                    mime_type = 'image/svg+xml'

                if self and self.cad_pom_image_id:
                    old_attachment = self.cad_pom_image_id
                    old_attachment.unlink()

                attachment = self.env['ir.attachment'].create({
                    'name': f'cad_pom_image.{extension}',
                    'res_model': 'maeknit.bom.request',
                    'res_id': self.id if self else False,
                    'type': 'binary',
                    'datas': base64_data,
                    'mimetype': mime_type,
                })

                cad_pom_data['image_attachment_id'] = attachment.id
                del cad_pom_data['image']

                vals['cad_pom_data'] = cad_pom_data
                vals['cad_pom_image_id'] = attachment.id

        except Exception as e:
            logging.error(f"Failed to process CAD & POM image: {e}")

        return vals

    def _process_measurement_panel_images(self, vals):
        """
        Extract images from Measurement panel data and store as attachments.
        Updates measurement_widget_data to reference attachment IDs instead of storing base64.
        """
        measurement_data = vals.get('measurement_widget_data')
        
        if not measurement_data:
            return vals
        
        # Ensure measurement_data is a dictionary
        if isinstance(measurement_data, str):
            try:
                measurement_data = json.loads(measurement_data)
            except json.JSONDecodeError:
                logging.error(f"Failed to parse Measurement Widget JSON data")
                return vals
        
        measurement_data = dict(measurement_data)  # Make a copy
        
        try:
            # Process all panels (front, back, sleeve, collar, customPanels)
            panels_to_process = {}
            
            # Standard panels
            for panel_name in ['front', 'back', 'sleeve', 'collar']:
                if panel_name in measurement_data and isinstance(measurement_data[panel_name], dict):
                    panels_to_process[panel_name] = measurement_data[panel_name]
            
            # Custom panels
            custom_panels = measurement_data.get('customPanels', [])
            if isinstance(custom_panels, list):
                for custom_panel in custom_panels:
                    if isinstance(custom_panel, dict) and 'id' in custom_panel:
                        panel_id = custom_panel['id']
                        if panel_id in measurement_data and isinstance(measurement_data[panel_id], dict):
                            panels_to_process[panel_id] = measurement_data[panel_id]

            # Structure panels (driven by structure tab)
            struct_panels = measurement_data.get('structurePanels', [])
            if isinstance(struct_panels, list):
                for struct_panel in struct_panels:
                    if isinstance(struct_panel, dict) and 'id' in struct_panel:
                        panel_id = struct_panel['id']
                        if panel_id in measurement_data and isinstance(measurement_data[panel_id], dict):
                            panels_to_process[panel_id] = measurement_data[panel_id]

            def _extract_image_to_attachment(panel_name, panel_data, image_field, attachment_field, suffix=''):
                """Extract a base64 image from panel_data and store as ir.attachment."""
                image_data = panel_data.get(image_field)
                if not image_data:
                    return
                if panel_data.get(attachment_field) and not (isinstance(image_data, str) and image_data.startswith('data:image')):
                    return
                if not isinstance(image_data, str) or not image_data.startswith('data:image'):
                    return
                try:
                    if ',' in image_data:
                        header, base64_data = image_data.split(',', 1)
                        mime_type = 'image/png'
                        extension = 'png'
                        if 'jpeg' in header.lower() or 'jpg' in header.lower():
                            extension = 'jpg'
                            mime_type = 'image/jpeg'
                        elif 'gif' in header.lower():
                            extension = 'gif'
                            mime_type = 'image/gif'
                        attachment = self.env['ir.attachment'].create({
                            'name': f'measurement_panel_{panel_name}{suffix}.{extension}',
                            'res_model': 'maeknit.bom.request',
                            'res_id': self.id if self else False,
                            'type': 'binary',
                            'datas': base64_data,
                            'mimetype': mime_type,
                            'res_field': 'measurement_widget_data',
                        })
                        panel_data[attachment_field] = attachment.id
                        del panel_data[image_field]
                        logging.info(f" Custom Code: Extracted measurement panel '{panel_name}{suffix}' image to attachment {attachment.id}")
                except Exception as e:
                    logging.error(f"Failed to process measurement panel '{panel_name}{suffix}' image: {e}")

            # Process each panel for image extraction (image, image2, annotated_image)
            for panel_name, panel_data in panels_to_process.items():
                _extract_image_to_attachment(panel_name, panel_data, 'image', 'image_attachment_id')
                _extract_image_to_attachment(panel_name, panel_data, 'image2', 'image2_attachment_id', suffix='_structure')
                _extract_image_to_attachment(panel_name, panel_data, 'annotated_image', 'annotated_image_attachment_id', suffix='_annotated')
            
            # Update vals with processed data
            vals['measurement_widget_data'] = measurement_data
            
        except Exception as e:
            logging.error(f"Failed to process measurement panel images: {e}")
        
        return vals

    # Updates start here
    @api.depends('calibration_data', 'calibration_image_ids')
    def _compute_calibration_data_with_images(self):
        """Restore images from attachments for widget display"""
        for record in self:
            if not record.calibration_data:
                record.calibration_data_with_images = {}
                continue
            
            # Handle both dict and string formats
            try:
                if isinstance(record.calibration_data, str):
                    import json
                    data = json.loads(record.calibration_data)
                elif isinstance(record.calibration_data, dict):
                    data = dict(record.calibration_data)
                else:
                    record.calibration_data_with_images = {}
                    continue
            except (ValueError, TypeError, json.JSONDecodeError):
                record.calibration_data_with_images = {}
                continue
            
            if data.get('widthImageAttachmentId'):
                attachment = self.env['ir.attachment'].browse(data['widthImageAttachmentId'])
                if attachment.exists():
                    data['widthImage'] = attachment.datas.decode('utf-8') if attachment.datas else None
            
            if data.get('heightImageAttachmentId'):
                attachment = self.env['ir.attachment'].browse(data['heightImageAttachmentId'])
                if attachment.exists():
                    data['heightImage'] = attachment.datas.decode('utf-8') if attachment.datas else None
            
            if data.get('widthImage2AttachmentId'):
                attachment = self.env['ir.attachment'].browse(data['widthImage2AttachmentId'])
                if attachment.exists():
                    data['widthImage2'] = attachment.datas.decode('utf-8') if attachment.datas else None
            
            if data.get('heightImage2AttachmentId'):
                attachment = self.env['ir.attachment'].browse(data['heightImage2AttachmentId'])
                if attachment.exists():
                    data['heightImage2'] = attachment.datas.decode('utf-8') if attachment.datas else None
            
            record.calibration_data_with_images = data
    # Updates end here

    @api.depends('whole_cad_data', 'whole_cad_image_id')
    def _compute_whole_cad_data_with_images(self):
        """Restore image from attachment for widget display"""
        for record in self:
            if not record.whole_cad_data:
                record.whole_cad_data_with_images = {
                    'max_version': 0,
                    'measurements': [],
                    'image': None,
                    'unit': 'inches'
                }
                continue
            
            # Handle both dict and string formats
            try:
                if isinstance(record.whole_cad_data, str):
                    data = json.loads(record.whole_cad_data)
                elif isinstance(record.whole_cad_data, dict):
                    data = dict(record.whole_cad_data)
                else:
                    record.whole_cad_data_with_images = {
                        'max_version': 0,
                        'measurements': [],
                        'image': None,
                        'unit': 'inches'
                    }
                    continue
            except (ValueError, TypeError, json.JSONDecodeError):
                record.whole_cad_data_with_images = {
                    'max_version': 0,
                    'measurements': [],
                    'image': None,
                    'unit': 'inches'
                }
                continue
            
            # Use URL instead of embedding base64 for whole CAD image
            image_attachment_id = data.get('image_attachment_id')
            
            if image_attachment_id or record.whole_cad_image_id:
                # Set image URL for widget to fetch
                data['image'] = f"/maeknit/whole_cad/image/{record.id}"
                logging.info(f" Custom Code: Set whole CAD image URL for BOM Request {record.id}")
            else:
                data['image'] = None
            
            record.whole_cad_data_with_images = data

    @api.depends('cad_pom_data', 'cad_pom_image_id')
    def _compute_cad_pom_data_with_images(self):
        """Restore image from attachment for CAD & POM widget display"""
        for record in self:
            if not record.cad_pom_data:
                record.cad_pom_data_with_images = {
                    'max_version': 0,
                    'measurements': [],
                    'image': None,
                    'unit': 'inches'
                }
                continue

            try:
                if isinstance(record.cad_pom_data, str):
                    data = json.loads(record.cad_pom_data)
                elif isinstance(record.cad_pom_data, dict):
                    data = dict(record.cad_pom_data)
                else:
                    record.cad_pom_data_with_images = {
                        'max_version': 0, 'measurements': [], 'image': None, 'unit': 'inches'
                    }
                    continue
            except (ValueError, TypeError, json.JSONDecodeError):
                record.cad_pom_data_with_images = {
                    'max_version': 0, 'measurements': [], 'image': None, 'unit': 'inches'
                }
                continue

            image_attachment_id = data.get('image_attachment_id')

            if image_attachment_id or record.cad_pom_image_id:
                data['image'] = f"/maeknit/cad_pom/image/{record.id}"
            else:
                data['image'] = None

            record.cad_pom_data_with_images = data

    @api.depends('measurement_widget_data', 'measurement_panel_image_ids')
    def _compute_measurement_widget_data_with_images(self):
        """Restore image URLs from attachments for widget display"""
        for record in self:
            if not record.measurement_widget_data:
                record.measurement_widget_data_with_images = {
                    'structurePanels': [],
                    'customPanels': [],
                    'hiddenPanels': [],
                    'unit': 'inches'
                }
                continue

            # Handle both dict and string formats
            try:
                if isinstance(record.measurement_widget_data, str):
                    data = json.loads(record.measurement_widget_data)
                elif isinstance(record.measurement_widget_data, dict):
                    data = dict(record.measurement_widget_data)
                else:
                    record.measurement_widget_data_with_images = record.measurement_widget_data
                    continue
            except (ValueError, TypeError, json.JSONDecodeError):
                record.measurement_widget_data_with_images = record.measurement_widget_data
                continue

            def _restore_panel_images(panel_key, panel_data):
                """Restore image, image2, and annotated_image URLs from attachment IDs."""
                att_id = panel_data.get('image_attachment_id')
                panel_data['image'] = record._measurement_panel_image_url(panel_key, att_id)
                att2_id = panel_data.get('image2_attachment_id')
                panel_data['image2'] = record._measurement_panel_image_url(panel_key + '_2', att2_id)
                ann_id = panel_data.get('annotated_image_attachment_id')
                panel_data['annotated_image_url'] = record._measurement_panel_image_url(panel_key + '_annotated', ann_id)

            # Restore image URLs for every panel body in the data (core, custom, structure)
            _meta_keys = {'structurePanels', 'customPanels', 'hiddenPanels', 'unit', 'status'}
            for key, value in data.items():
                if key not in _meta_keys and isinstance(value, dict):
                    _restore_panel_images(key, value)

            record.measurement_widget_data_with_images = data

    def _get_attachment_timestamp(self, attachment):
        """Return integer timestamp for attachment write_date to bust cache"""
        if not attachment or not attachment.exists() or not attachment.write_date:
            return int(time.time())
        try:
            dt = fields.Datetime.from_string(attachment.write_date)
            if dt:
                return int(dt.timestamp())
        except Exception:
            pass
        return int(time.time())

    def _measurement_panel_image_url(self, panel_name, attachment_id):
        """Build panel image URL with cache-busting timestamp."""
        if not attachment_id:
            return None
        attachment = self.env['ir.attachment'].browse(attachment_id)
        if not attachment.exists():
            return None
        ts = self._get_attachment_timestamp(attachment)
        return f"/maeknit/measurement/panel/{self.id}/{panel_name}?ts={ts}"

    def get_excalidraw_image_url(self, file_id):
        """Return URL to fetch image data for a given file_id"""
        self.ensure_one()
        if not self.excalidraw_data:
            return None
        
        # Get fileIds mapping
        try:
            if isinstance(self.excalidraw_data, dict):
                file_ids_map = self.excalidraw_data.get('fileIds', {})
            elif isinstance(self.excalidraw_data, str):
                data = json.loads(self.excalidraw_data)
                file_ids_map = data.get('fileIds', {})
            else:
                return None
        except (json.JSONDecodeError, AttributeError):
            return None
        
        # Get attachment ID for this file
        attachment_id = file_ids_map.get(file_id)
        if not attachment_id:
            return None
        
        # Return Odoo's native attachment URL
        return f'/web/content/{attachment_id}?download=false'
