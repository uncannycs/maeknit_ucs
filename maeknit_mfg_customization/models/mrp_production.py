from odoo import models, fields, api, _
from odoo.tools.safe_eval import safe_eval
import logging
import json
from odoo.exceptions import ValidationError, UserError
# Code needs to delete old references.

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    excalidraw_link = fields.Char(
        string='Excalidraw Link',
        help='Optional link to the Excalidraw diagram that documents this MO.',
    )
    bom_request_id = fields.Many2one(
        'maeknit.bom.request',
        string='BOM Request',
        help='Link to the originating BOM Request',
        ondelete='set null',
        copy=False
    )
    
    whole_cad_data = fields.Json(
        string='Whole CAD Data',
        help='Whole CAD data synced from BOM Request',
        default=lambda self: {
            'max_version': 0,
            'measurements': [],
            'image': None,
            'unit': 'inches'
        }
    )
    
    whole_cad_data_with_images = fields.Json(
        string='Whole CAD Data (Full)',
        compute='_compute_whole_cad_data_with_images',
        help='Full whole CAD data with image URL for widget display'
    )

    cad_pom_data = fields.Json(
        string='CAD & POM Data',
        help='CAD & POM data synced from BOM Request',
        default=lambda self: {
            'max_version': 0,
            'measurements': [],
            'image': None,
            'unit': 'inches'
        }
    )

    cad_pom_data_with_images = fields.Json(
        string='CAD & POM Data (Full)',
        compute='_compute_cad_pom_data_with_images',
        help='Full CAD & POM data with image URL for widget display'
    )

    measurement_widget_data = fields.Json(
        string='Panel CAD Data',
        help='Panel CAD data (measurement widget) synced from BOM Request',
        default=lambda self: {
            'structurePanels': [],
            'customPanels': [],
            'hiddenPanels': [],
            'unit': 'inches'
        }
    )

    measurement_widget_data_with_images = fields.Json(
        string='Panel CAD Data (Full)',
        compute='_compute_measurement_widget_data_with_images',
        help='Full panel CAD data with image URLs restored from attachments for widget display'
    )

    toile_doc_data = fields.Json(
        string='Toile Documentation Data',
        help='Actual measurement records per panel for Toile MOs',
        default=lambda self: {},
    )

    calibration_data = fields.Json(
        string='Calibration Data',
        help='Calibration swatch data including body/cuff specs and measurements',
        default=lambda self: {
            'hasPreExistingSwatch': False,
            'calibrationSwatchId': None,
            'calibrationSwatchName': '',
            'bodySwatchSpecsX': 0,
            'bodySwatchSpecsY': 0,
            'bodyMeasurementX': 0,
            'bodyMeasurementY': 0,
            'bodyMeasurementXUnit': 'inches',
            'bodyMeasurementYUnit': 'inches',
            'bodyCalibrationX': 0,
            'bodyCalibrationY': 0,
            'cuffSwatchSpecsX': 0,
            'cuffSwatchSpecsY': 0,
            'cuffMeasurementX': 0,
            'cuffMeasurementY': 0,
            'cuffMeasurementXUnit': 'inches',
            'cuffMeasurementYUnit': 'inches',
            'cuffCalibrationX': 0,
            'cuffCalibrationY': 0,
            'widthImageAttachmentId': None,
            'heightImageAttachmentId': None,
            'widthImage2AttachmentId': None,
            'heightImage2AttachmentId': None,
        }
    )
    
    is_blocked_for_calibration = fields.Boolean(
        string='Blocked for Calibration',
        default=False,
        help='Indicates if this MO is blocked waiting for calibration swatch completion'
    )
    calibration_swatch_mo_id = fields.Many2one(
        'mrp.production',
        string='Calibration Swatch MO',
        help='Link to the calibration swatch MO generated for this garment',
        ondelete='set null'
    )
    parent_garment_mo_id = fields.Many2one(
        'mrp.production',
        string='Parent Garment MO',
        help='Link to the parent garment MO (for calibration swatch MOs)',
        ondelete='set null'
    )

    origin_mo_id = fields.Many2one(
        'mrp.production',
        string='Origin Manufacturing Order',
        help='The parent MO that this swatch MO was generated for',
        ondelete='set null',
        copy=False,
    )
    swatch_mo_ids = fields.One2many(
        'mrp.production',
        'origin_mo_id',
        string='Linked Swatch MOs',
    )
    swatch_count = fields.Integer(
        string='Swatch Count',
        compute='_compute_swatch_count',
        store=False,
    )

    # Render Tab Fields
    style_3d_link = fields.Char(
        string='Style 3D Link',
        help='Link to the Style 3D rendering'
    )

    render_image_ids = fields.One2many(
        'render.image.line',
        'production_id',
        string='Render Images',
        help='Render images for this Manufacturing Order'
    )

    # Fields to store BOM attribute data
    product_category = fields.Selection(related='product_id.product_tmpl_id.product_category',
                                       string='Product Category', store=True)
    product_tmpl_name = fields.Char(
        string="Product Name",
        compute='_compute_product_tmpl_name',
        inverse='_set_product_tmpl_name',
        store=False,
    )

    is_swatch_mo = fields.Boolean(
        string="Swatch",
        compute='_compute_is_swatch_mo',
        inverse='_set_is_swatch_mo',
        store=False,
        default=False,
    )
    
    # BOM Type field - for all product categories
    bom_type = fields.Selection(related='bom_id.type', string='BOM Type', store=True, readonly=False)
    
    workorder_attachment_count = fields.Integer(
        string='Workorder Attachments',
        compute='_compute_workorder_attachment_count',
        store=True
    )
    
    has_instruction_files = fields.Boolean(
        string='Has Instructions',
        compute='_compute_has_files',
        store=True
    )
    has_program_files = fields.Boolean(
        string='Has Programs',
        compute='_compute_has_files',
        store=True
    )

    latest_program_workorder_id = fields.Many2one(
        'mrp.workorder',
        string='Latest Program Workorder',
        compute='_compute_latest_program_workorder_id',
        store=False,
        help='The latest Knit/Program workorder that has program files attached'
    )
    
    # Garment fields - make them editable with readonly=False
    run_id = fields.Many2one('product.attribute.value', string='Run', 
                            compute='_compute_bom_attributes', store=True, readonly=False,
                            domain="[('attribute_id.name', '=', 'Run')]")
    style_colorway_ids = fields.Many2many('product.attribute.value',
                                         compute='_compute_style_colorway_ids',
                                         string='Available Colorways')
    style_size_ids = fields.Many2many('product.attribute.value',
                                      relation='mrp_production_style_size_rel',
                                      compute='_compute_style_size_ids',
                                      string='Available Sizes')
    style_yarn_variant_ids = fields.Many2many('product.attribute.value',
                                              relation='mrp_production_style_yarn_variant_rel',
                                              compute='_compute_style_yarn_variant_ids',
                                              string='Available Yarn Variants')
    colorway_id = fields.Many2one('product.attribute.value', string='Colorway',
                                 compute='_compute_bom_attributes', store=True, readonly=False,
                                 domain="[('id', 'in', style_colorway_ids)]")
    size_id = fields.Many2one('product.attribute.value', string='Size',
                             compute='_compute_bom_attributes', store=True, readonly=False,
                             domain="[('id', 'in', style_size_ids)]")
    yarn_variant = fields.Many2one('product.attribute.value', string='Yarn Variant',
                                   store=True,
                                   domain="[('attribute_id.name', '=', 'Yarn Variant')]")

    is_uk_company = fields.Boolean(
        string='Is UK Company',
        compute='_compute_is_uk_company',
        store=True,
        readonly=True,
    )
    
    # Swatch fields - make them editable with readonly=False
    swatch_number_id = fields.Many2one('product.attribute.value', string='Swatch #', 
                                      compute='_compute_bom_attributes', store=True, readonly=False,
                                      domain="[('attribute_id.name', '=', 'Swatch #')]")
    # Machine and stitch fields from BOM - make them editable with readonly=False
    machine_id = fields.Many2one('machine.library', string='Machine', 
                                compute='_compute_bom_attributes', store=True, readonly=False)

    body_stitch_id = fields.Many2one('stitch.library', string='Body Stitch', 
                                  compute='_compute_bom_attributes', store=True, readonly=False)
    cuff_stitch_id = fields.Many2one('stitch.library', string='Cuff Stitch', 
                                  compute='_compute_bom_attributes', store=True, readonly=False)
    
    # Additional fields from BOM
    machine_file = fields.Binary(string='Machine File', attachment=True,
                             compute='_compute_bom_attributes', store=True, readonly=False)
    machine_filename = fields.Char(string='Machine Filename',
                               compute='_compute_bom_attributes', store=True, readonly=False)
    expected_machine_time = fields.Char(string='Expected Machine Time', 
                                     compute='_compute_bom_attributes', store=True, readonly=False)
    hs_code = fields.Char(string='HS Code',
                       compute='_compute_bom_attributes', store=True, readonly=False)
    total_cost = fields.Float(string='Total Cost',
                           compute='_compute_bom_attributes', store=True, readonly=False)
    
    # Status tracking fields
    is_sample = fields.Boolean(string='Is Sample', compute='_compute_is_sample', store=True)
    # New fields to indicate if BOM exists for current attribute values
    run_exists_in_bom = fields.Boolean(string='Run Exists in BOM', 
                                    compute='_compute_attribute_exists_in_bom', store=True)
    swatch_exists_in_bom = fields.Boolean(string='Swatch Exists in BOM', 
                                       compute='_compute_attribute_exists_in_bom', store=True)
    
    all_workorders_completed = fields.Boolean(
        string='All Workorders Completed',
        compute='_compute_all_workorders_completed',
        store=False
    )

    show_bom_duplicate_button = fields.Boolean(
        string='Show BOM Duplicate Button',
        compute='_compute_variant_buttons',
        store=False,
        help='True when a BOM request exists and it is marked as a swatch BOM.'
    )

    show_create_variant_button = fields.Boolean(
        string='Show Create Variant Button',
        compute='_compute_variant_buttons',
        store=False,
        help='True when a BOM request exists, is for Development Service, and a BOM is linked.'
    )
    
    rel_service = fields.Many2one(
        'product.product',
        string='Service',
        store=True,
        domain="[('type','=','service'), ('name','in',['Development Service','Swatch Service','Toile Service','Grading Service','Production Service'])]",
    )

    service_badge = fields.Selection(
        [('success', 'Success'), ('info', 'Info'), ('secondary', 'Secondary'), ('primary', 'Primary'), ('warning', 'Warning')],
        compute='_compute_service_badge',
        store=False,
    )

    is_toile_mo = fields.Boolean(
        string='Is Toile MO',
        compute='_compute_is_toile_mo',
        store=False,
        default=False,
    )

    is_dev_mo = fields.Boolean(
        string='Is Development MO',
        compute='_compute_is_dev_mo',
        store=False,
        default=False,
    )

    def _link_workorders_and_moves(self):
        """Override to clear dependencies before re-linking.
        This prevents cyclic dependencies when reordering WOs in Confirmed state.
        """
        self.workorder_ids.write({'blocked_by_workorder_ids': [(5, 0, 0)]})
        return super()._link_workorders_and_moves()

    @api.depends('rel_service')
    def _compute_service_badge(self):
        for production in self:
            name = production.rel_service.name or ''
            if name == 'Development Service':
                production.service_badge = 'success'
            elif name == 'Swatch Service':
                production.service_badge = 'info'
            elif name == 'Toile Service':
                production.service_badge = 'secondary'
            elif name == 'Grading Service':
                production.service_badge = 'primary'
            elif name == 'Production Service':
                production.service_badge = 'warning'
            else:
                production.service_badge = False

    @api.depends('rel_service')
    def _compute_is_toile_mo(self):
        for record in self:
            record.is_toile_mo = bool(record.rel_service) and record.rel_service.name == 'Toile Service'

    @api.depends('rel_service')
    def _compute_is_dev_mo(self):
        for record in self:
            record.is_dev_mo = bool(record.rel_service) and record.rel_service.name == 'Development Service'
    
    @api.onchange('rel_service')
    def _onchange_rel_service_populate_workorders(self):
        """When a service is selected on a new MO, auto-fill Work Orders from
        the matching BOM Operation Template (prefers is_default=True).
        Does nothing when the MO is already confirmed to avoid overwriting
        existing workorders."""
        if self.state != 'draft':
            return

        _service_map = {
            'Development Service': 'development',
            'Swatch Service': 'swatch',
            'Toile Service': 'toile',
            'Grading Service': 'grading',
            'Production Service': 'production',
        }
        service_type = self.rel_service and _service_map.get(self.rel_service.name)
        if not service_type:
            return

        template = self.env['maeknit.bom.operation.template'].search([
            ('related_service', '=', service_type),
            ('company_id', '=', (self.company_id or self.env.company).id),
        ], order='is_default desc, id asc', limit=1)
        if not template or not template.line_ids:
            return

        # Preserve any manually-added WOs (no shopfloor_operation_id) in case
        # the user changed the service after adding custom WOs.
        uom_id = self.product_uom_id.id if self.product_uom_id else self.env.ref('uom.product_uom_unit').id
        manual_wo_vals = []
        for wo in self.workorder_ids:
            if not wo.shopfloor_operation_id:
                manual_wo_vals.append({
                    'name': wo.name,
                    'workcenter_id': wo.workcenter_id.id if wo.workcenter_id else False,
                    'sequence': wo.sequence,
                    'product_uom_id': wo.product_uom_id.id if wo.product_uom_id else uom_id,
                    'employee_assigned_ids': [(6, 0, wo.employee_assigned_ids.ids)],
                })

        # Build WO vals from template lines
        template_wo_vals = []
        for line in template.line_ids.sorted('sequence'):
            workcenter = self._get_default_workcenter_for_operation(line.operation_id)
            template_wo_vals.append({
                'name': line.operation_id.name,
                'shopfloor_operation_id': line.operation_id.id,
                'workcenter_id': workcenter.id if workcenter else False,
                'sequence': line.sequence,
                'product_uom_id': uom_id,
                'employee_assigned_ids': [(6, 0, line.user_ids.ids)],
            })

        # (5,) clears the current O2M list, then re-add preserved + template WOs
        commands = [(5,)]
        commands += [(0, 0, v) for v in manual_wo_vals]
        commands += [(0, 0, v) for v in template_wo_vals]
        self.workorder_ids = commands

    def _get_default_workcenter_for_operation(self, shopfloor_op):
        """Return the first active workcenter whose tags overlap with the operation's
        workcenter_tag_ids; fall back to any active workcenter in the company."""
        company = self.company_id or self.env.company
        tag_ids = shopfloor_op.workcenter_tag_ids.ids
        domain = [('company_id', '=', company.id), ('active', '=', True)]
        if tag_ids:
            domain.append(('tag_ids', 'in', tag_ids))
        return self.env['mrp.workcenter'].search(domain, limit=1)

    wizard_measurements_submitted = fields.Boolean(
        string='Wizard Measurements Submitted',
        default=False,
        help='Flag to prevent automatic version bump when measurements submitted via wizard'
    )
    
    calibration_data_with_images = fields.Json(
        string='Calibration Data (Full)',
        compute='_compute_calibration_data_with_images',
        help='Full calibration data with images restored from attachments for widget display'
    )
    
    calibration_image_ids = fields.One2many(
        'ir.attachment',
        'res_id',
        string='Calibration Images',
        domain=[('res_model', '=', 'mrp.production'), ('res_field', 'in', ['width_image', 'height_image', 'width_image_2', 'height_image_2'])],
        help='Image attachments for calibration measurements'
    )

    @api.depends('bom_id', 'product_id', 'product_qty', 'product_uom_id', 'never_product_template_attribute_value_ids')
    def _compute_workorder_ids(self):
        """Override to:
        1. Preserve template-sourced WOs (shopfloor_operation_id) when product changes on new MO with no BOM.
        2. Skip regeneration when saved manual WOs (no operation_id) already exist in DB.
        """
        # Snapshot template WOs (virtual, no DB id) before super() clears them
        template_wo_snapshots = {}
        for production in self:
            if production.state == 'draft' and not production.bom_id:
                template_wos = production.workorder_ids.filtered(
                    lambda wo: wo.shopfloor_operation_id
                )
                if template_wos:
                    template_wo_snapshots[production] = [
                        {
                            'name': wo.name,
                            'shopfloor_operation_id': wo.shopfloor_operation_id.id,
                            'workcenter_id': wo.workcenter_id.id if wo.workcenter_id else False,
                            'sequence': wo.sequence,
                            'product_uom_id': wo.product_uom_id.id if wo.product_uom_id else False,
                            'employee_assigned_ids': [(6, 0, wo.employee_assigned_ids.ids)],
                        }
                        for wo in template_wos
                    ]

        # Skip regeneration for MOs that already have saved manual WOs (no operation_id)
        skip_ids = self.env['mrp.production']
        for production in self:
            if production.state != 'draft':
                continue
            existing_wos = production.workorder_ids.filtered(lambda wo: wo.ids)
            if existing_wos and any(not wo.operation_id for wo in existing_wos):
                skip_ids |= production
        remaining = self - skip_ids
        if remaining:
            super(MrpProduction, remaining)._compute_workorder_ids()

        # Restore template WOs if super() cleared them and no BOM-driven WOs remain
        for production in self:
            if production not in template_wo_snapshots:
                continue
            if production.workorder_ids:
                continue  # BOM populated WOs — leave them alone
            snapshots = template_wo_snapshots[production]
            uom_id = production.product_uom_id.id if production.product_uom_id else self.env.ref('uom.product_uom_unit').id
            for snap in snapshots:
                if not snap['product_uom_id']:
                    snap['product_uom_id'] = uom_id
            production.workorder_ids = [(0, 0, snap) for snap in snapshots]

    #override autoconfirm to prevent consolidation of duplicate components
    def _autoconfirm_production(self):
        moves_to_confirm_raw = self.env["stock.move"]
        moves_to_confirm_finished = self.env["stock.move"]

        for production in self:
            if production.state in ("done", "cancel"):
                continue

            # Only the newly added draft raw moves
            additional_raw = production.move_raw_ids.filtered(lambda m: m.state == "draft")
            additional_raw._adjust_procure_method()
            moves_to_confirm_raw |= additional_raw

            # Newly added draft finished/byproduct moves
            additional_finished = production.move_finished_ids.filtered(lambda m: m.state == "draft")
            moves_to_confirm_finished |= additional_finished

        if moves_to_confirm_raw:
            # Key line: prevents consolidation of duplicate components
            moves_to_confirm_raw = moves_to_confirm_raw._action_confirm(merge=False)
            moves_to_confirm_raw._trigger_scheduler()

        if moves_to_confirm_finished:
            # optional: keep default merge, or set merge=False if you also want duplicates there
            moves_to_confirm_finished = moves_to_confirm_finished._action_confirm()
            moves_to_confirm_finished._trigger_scheduler()

        self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))._action_confirm()

    
    @api.depends('workorder_ids', 'workorder_ids.state')
    def _compute_all_workorders_completed(self):
        for production in self:
            workorders = production.workorder_ids
            logging.info(f" Custom Code: MO {production.name} - Workorders found: {len(workorders)}")
            if not workorders:
                production.all_workorders_completed = False
            else:
                production.all_workorders_completed = all(
                    wo.state == 'done' for wo in workorders
                )
                logging.info(f" Custom Code: MO {production.name} - All Workorders Completed: {production.all_workorders_completed}")

    @api.depends('rel_service', 'product_category', 'bom_id')
    def _compute_variant_buttons(self):
        for record in self:
            is_garment_product = record.product_category in ('garment', 'swatch')
            has_service = bool(record.rel_service)
            has_bom = bool(record.bom_id)
            show = is_garment_product and has_service and has_bom
            record.show_bom_duplicate_button = show
            record.show_create_variant_button = show

    @api.depends('product_id', 'run_id', 'swatch_number_id')
    def _compute_attribute_exists_in_bom(self):
        """Check if current attribute values exist in any BOM for this product, this is for the UI to indicate if BOM is already set up."""
        for record in self:
            record.run_exists_in_bom = False
            record.swatch_exists_in_bom = False
            
            if not record.product_id:
                continue
                
            # Check for Run existence in BOMs
            if record.run_id:
                existing_bom = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', record.product_id.product_tmpl_id.id),
                    ('run_id', '=', record.run_id.id)
                ], limit=1)
                record.run_exists_in_bom = bool(existing_bom)
            
            # Check for Swatch # existence in BOMs
            if record.swatch_number_id:
                existing_bom = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', record.product_id.product_tmpl_id.id),
                    ('swatch_number_id', '=', record.swatch_number_id.id)
                ], limit=1)
                record.swatch_exists_in_bom = bool(existing_bom)
    
    @api.depends('run_id')
    def _compute_is_sample(self):
        """Determine if this is a sample production based on the Run"""
        for record in self:
            # If Run contains 'sample' or is '1', mark as sample
            if record.run_id:
                record.is_sample = True
            else:
                record.is_sample = False
    
    @api.depends('product_id.product_tmpl_id.name')
    def _compute_product_tmpl_name(self):
        for record in self:
            record.product_tmpl_name = record.product_id.product_tmpl_id.name if record.product_id else False

    def _set_product_tmpl_name(self):
        for record in self:
            if record.product_id and record.product_tmpl_name:
                record.product_id.product_tmpl_id.sudo().with_context(
                    no_recompute=True
                ).write({'name': record.product_tmpl_name})

    @api.depends('rel_service', 'product_category')
    def _compute_is_swatch_mo(self):
        for record in self:
            if record.rel_service:
                record.is_swatch_mo = record.rel_service.name == 'Swatch Service'
            else:
                record.is_swatch_mo = record.product_category == 'swatch'

    def _set_is_swatch_mo(self):
        # For new records: no-op; the view uses is_swatch_mo to set domain/context on product_id
        pass

    @api.depends('swatch_mo_ids')
    def _compute_swatch_count(self):
        for record in self:
            record.swatch_count = len(record.swatch_mo_ids)

    def action_open_swatches(self):
        self.ensure_one()
        if self.swatch_count == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production',
                'res_id': self.swatch_mo_ids[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Swatches',
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'domain': [('origin_mo_id', '=', self.id)],
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Keep origin_mo_id in sync with parent_garment_mo_id so swatch_count stays
            # accurate regardless of which path created the record.
            if vals.get('parent_garment_mo_id') and not vals.get('origin_mo_id'):
                vals['origin_mo_id'] = vals['parent_garment_mo_id']
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            # Auto-create BOM only for standalone MOs (no bom_request, no existing bom)
            if not vals.get('bom_id') and not vals.get('bom_request_id') and record.product_id:
                record._auto_create_standalone_bom(vals)
        return records

    def write(self, vals):
        result = super().write(vals)
        # When parent_garment_mo_id is set via a separate write() call (e.g. Odoo 17
        # One2many dialog forms link the inverse field after record creation), mirror it
        # into origin_mo_id so swatch_count stays accurate.
        if vals.get('parent_garment_mo_id') and not vals.get('origin_mo_id'):
            self.filtered(lambda r: not r.origin_mo_id).write(
                {'origin_mo_id': vals['parent_garment_mo_id']}
            )
        return result

    def _auto_create_standalone_bom(self, vals=None):
        """Create a BOM (and the matching product variant) automatically when saving a
        standalone MO that has no BOM request and no pre-selected BOM.

        Garment: colorway_id + size_id required.
        Swatch:  colorway_id required, yarn_variant optional.
        """
        self.ensure_one()
        if vals is None:
            vals = {}

        product_tmpl = self.product_id.product_tmpl_id
        category = self.product_category

        if not category or category not in ('garment', 'swatch'):
            return

        # Prefer live record values; fall back to raw vals if the field is non-stored/related
        colorway_id = (self.colorway_id.id if self.colorway_id else None) or vals.get('colorway_id')
        size_id = (self.size_id.id if self.size_id else None) or vals.get('size_id')
        yarn_variant_id = (self.yarn_variant.id if self.yarn_variant else None) or vals.get('yarn_variant')

        bom_vals = {
            'product_tmpl_id': product_tmpl.id,
            'company_id': self.company_id.id,
        }
        if self.gauge_id:
            bom_vals['gauge_id'] = self.gauge_id.id

        if category == 'garment':
            if not colorway_id or not size_id:
                return
            # Reuse existing BOM if one already matches
            existing_bom = self.env['mrp.bom'].search([
                ('product_tmpl_id', '=', product_tmpl.id),
                ('colorway_id', '=', colorway_id),
                ('size_id', '=', size_id),
            ], limit=1)
            if existing_bom:
                self.bom_id = existing_bom.id
                if existing_bom.product_id:
                    self.product_id = existing_bom.product_id
                self._update_product_tmpl_from_mo(product_tmpl)
                return
            bom_vals.update({
                'colorway_id': colorway_id,
                'size_id': size_id,
            })

        elif category == 'swatch':
            if not colorway_id:
                return
            domain = [
                ('product_tmpl_id', '=', product_tmpl.id),
                ('colorway_id', '=', colorway_id),
            ]
            if yarn_variant_id:
                domain.append(('yarn_variant', '=', yarn_variant_id))
            existing_bom = self.env['mrp.bom'].search(domain, limit=1)
            if existing_bom:
                self.bom_id = existing_bom.id
                if existing_bom.product_id:
                    self.product_id = existing_bom.product_id
                self._update_product_tmpl_from_mo(product_tmpl)
                return
            bom_vals['colorway_id'] = colorway_id
            if yarn_variant_id:
                bom_vals['yarn_variant'] = yarn_variant_id

        new_bom = self.env['mrp.bom'].create(bom_vals)
        self.bom_id = new_bom.id
        # Sync product_id to the specific variant created by the BOM
        if new_bom.product_id:
            self.product_id = new_bom.product_id
        self._update_product_tmpl_from_mo(product_tmpl)

    def _update_product_tmpl_from_mo(self, product_tmpl):
        """Populate product template metadata from this MO (only sets fields that are empty)."""
        tmpl_vals = {}

        # Client: propagate MO customer → product template brand
        if self.partner_id and not product_tmpl.brand_id:
            tmpl_vals['brand_id'] = self.partner_id.id

        # Style Family: generate a new sequence-based code (same logic as CRM leads)
        if not product_tmpl.style_family:
            partner_name = self.partner_id.name if self.partner_id else ''
            tmpl_vals['style_family'] = self.env['crm.lead']._generate_style_family(partner_name)

        # Lab: propagate MO company → product template company
        # Only attempt if the product is shared (no company)
        if self.company_id and not product_tmpl.company_id:
            try:
                # Use a savepoint to catch the validation error from Odoo core
                with self.env.cr.savepoint():
                    product_tmpl.sudo().write({'company_id': self.company_id.id})
                    logging.info(" Custom Code: Propagated company %s to product template %s", self.company_id.name, product_tmpl.name)
            except Exception as e:
                logging.info(" Custom Code: Skipping company propagation for product %s: %s", product_tmpl.name, str(e))

        if tmpl_vals:
            product_tmpl.write(tmpl_vals)

    @api.depends('bom_id', 'product_id')
    def _compute_bom_attributes(self):
        '''Compute Values if bom_id / product_id changes'''
        """Pull attribute data from the BOM only if fields are not set yet"""
        for record in self:
            # Skip if no BOM or product
            if not record.product_id:
                # If no BOM is linked, clear the computed fields to allow manual entry
                record.run_id = False
                record.colorway_id = False
                record.size_id = False
                record.swatch_number_id = False
                record.body_stitch_id = False
                record.cuff_stitch_id = False
                record.machine_id = False
                record.machine_file = False
                record.machine_filename = False
                record.expected_machine_time = False
                record.hs_code = False
                record.total_cost = False
                continue
                
            # Get the product template
            product_tmpl = record.product_id.product_tmpl_id
            
            # Get the product category
            product_category = product_tmpl.product_category if hasattr(product_tmpl, 'product_category') else False
            
            # Find the specific BOM for this variant
            specific_bom = self.env['mrp.bom'].search([
                ('product_tmpl_id', '=', product_tmpl.id),
                ('product_id', '=', record.product_id.id)
            ], limit=1)
            
            # If no specific BOM found, use the general BOM
            bom = specific_bom or record.bom_id
            
            # Extract attributes based on product category - only if not already set
            if product_category == 'garment':
                # For garment products
                if not record.run_id and hasattr(bom, 'run_id') and bom.run_id:
                    record.run_id = bom.run_id.id
                if not record.colorway_id and hasattr(bom, 'colorway_id') and bom.colorway_id:
                    record.colorway_id = bom.colorway_id.id
                if not record.size_id and hasattr(bom, 'size_id') and bom.size_id:
                    record.size_id = bom.size_id.id
                # Ensure swatch fields are cleared if product category is garment
                record.swatch_number_id = False
                record.body_stitch_id = False
                record.cuff_stitch_id = False
            elif product_category == 'swatch':
                # For swatch products
                if not record.swatch_number_id and hasattr(bom, 'swatch_number_id') and bom.swatch_number_id:
                    record.swatch_number_id = bom.swatch_number_id.id
                if not record.colorway_id and hasattr(bom, 'colorway_id') and bom.colorway_id:
                    record.colorway_id = bom.colorway_id.id
                if not record.body_stitch_id and hasattr(bom, 'body_stitch_id') and bom.body_stitch_id:
                    record.body_stitch_id = bom.body_stitch_id.id
                if not record.cuff_stitch_id and hasattr(bom, 'cuff_stitch_id') and bom.cuff_stitch_id:
                    record.cuff_stitch_id = bom.cuff_stitch_id.id
                # Ensure garment fields are cleared if product category is swatch
                record.run_id = False
                record.size_id = False
            else:
                # For other products, clear all category-specific attributes
                record.run_id = False
                record.colorway_id = False
                record.size_id = False
                record.swatch_number_id = False
                record.body_stitch_id = False
                record.cuff_stitch_id = False
            
            # Extract machine and stitch data - only if not already set
            if not record.machine_id and hasattr(bom, 'machine_id') and bom.machine_id:
                record.machine_id = bom.machine_id.id
            if not record.gauge_id and hasattr(bom, 'gauge_id') and bom.gauge_id:
                record.gauge_id = bom.gauge_id.id
            
            # Extract additional fields from BOM
            if not record.machine_file and hasattr(bom, 'machine_file'):
                record.machine_file = bom.machine_file
            if not record.machine_filename and hasattr(bom, 'machine_filename'):
                record.machine_filename = bom.machine_filename
            if not record.expected_machine_time and hasattr(bom, 'expected_machine_time'):
                record.expected_machine_time = bom.expected_machine_time
            if not record.hs_code and hasattr(bom, 'hs_code'):
                record.hs_code = bom.hs_code
            if not record.total_cost and hasattr(bom, 'total_cost'):
                record.total_cost = bom.total_cost

    def action_reknit(self):
        self.ensure_one()
        workorder_id = self.env.context.get("workorder_id")
        bom_request = self.env['maeknit.bom.request'].search([
            ('bom_id', '=', self.bom_id.id)
        ], limit=1)
        return self.env['reknit.wizard'].open_reknit_wizard(self.id, bom_request.id, workorder_id if workorder_id else None)
    
    def action_generate_bom(self):
        """
        Generates a new Bill of Material based on the Manufacturing Order's product,
        components, workorders and by-products, and assigns it to the MO.
        Creates the BOM directly without navigating away from the current page.
        """
        self.ensure_one()

        bom_lines_vals, byproduct_vals, operations_vals = self._get_bom_values()
        
        # Prepare values for BOM creation
        bom_vals = {
            'product_tmpl_id': self.product_id.product_tmpl_id.id,
            'product_id': self.product_id.id, # Link to the specific product variant
            'product_qty': self.product_qty,
            'product_uom_id': self.product_uom_id.id,
            'code': _("New BoM from %(mo_name)s", mo_name=self.display_name),
            'company_id': self.company_id.id,
            'bom_line_ids': bom_lines_vals, # Use all lines, create command (0,0,vals)
            'byproduct_ids': byproduct_vals,
            'operation_ids': operations_vals,
        }
        
        # Add custom attribute values based on product category
        if hasattr(self.product_id.product_tmpl_id, 'product_category'):
            product_category = self.product_id.product_tmpl_id.product_category
            
            if product_category == 'garment':
                # For garment products, add Run, Colorway, Size
                if self.run_id:
                    bom_vals['run_id'] = self.run_id.id
                if self.colorway_id:
                    bom_vals['colorway_id'] = self.colorway_id.id
                if self.size_id:
                    bom_vals['size_id'] = self.size_id.id
                bom_vals['is_garment_bom'] = True
                    
            elif product_category == 'swatch':
                # For swatch products, add Swatch #, Colorway, Body/Cuff Stitch
                if self.swatch_number_id:
                    bom_vals['swatch_number_id'] = self.swatch_number_id.id
                if self.colorway_id:
                    bom_vals['colorway_id'] = self.colorway_id.id
                if self.body_stitch_id:
                    bom_vals['body_stitch_id'] = self.body_stitch_id.id
                if self.cuff_stitch_id:
                    bom_vals['cuff_stitch_id'] = self.cuff_stitch_id.id
                bom_vals['is_swatch_bom'] = True
        # Add machine and technical data for both categories
        if self.product_category in ('garment', 'swatch'):
            if self.machine_id:
                bom_vals['machine_id'] = self.machine_id.id
            if self.gauge_id:
                bom_vals['gauge_id'] = self.gauge_id.id
            if self.machine_file:
                bom_vals['machine_file'] = self.machine_file
            if self.machine_filename:
                bom_vals['machine_filename'] = self.machine_filename
            if self.expected_machine_time:
                bom_vals['expected_machine_time'] = self.expected_machine_time
            if self.hs_code:
                bom_vals['hs_code'] = self.hs_code
            if self.total_cost:
                bom_vals['total_cost'] = self.total_cost
        
        # Create the BOM
        new_bom = self.env['mrp.bom'].create(bom_vals)
        
        # Assign the new BOM to the current MO
        self.bom_id = new_bom.id
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_update_bom(self):
        """
        Updates the existing Bill of Material associated with the Manufacturing Order
        based on the MO's current product, components, workorders, and by-products.
        """
        self.ensure_one()
        logging.info(" Custom Code:Updating BOM for MO: %s", self)
        if not self.bom_id:
            # Try to auto-link the BOM based on run/swatch if applicable
            if self.product_category == 'garment' and self.run_id:
                matching_bom = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
                    ('run_id', '=', self.run_id.id)
                ], limit=1)
                if matching_bom:
                    self.bom_id = matching_bom.id

            elif self.product_category == 'swatch' and self.swatch_number_id:
                matching_bom = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
                    ('swatch_number_id', '=', self.swatch_number_id.id)
                ], limit=1)
                if matching_bom:
                    self.bom_id = matching_bom.id

            # After attempting auto-assign, check again
            if not self.bom_id:
                raise ValidationError(_("No Bill of Materials is associated with this Manufacturing Order to update."))

        # 1. Get current components, by-products, and operations from the MO
        mo_bom_lines_vals, mo_byproduct_vals, mo_operations_vals = self._get_bom_values()

        # 2. Prepare update commands for BOM lines
        bom_line_commands = []
        existing_bom_lines_map = {
            (line.product_id.id, line.product_uom_id.id): line
            for line in self.bom_id.bom_line_ids
        }

        for line_val in mo_bom_lines_vals:
            product_id = line_val[2]['product_id']
            product_uom_id = line_val[2]['product_uom_id']
            key = (product_id, product_uom_id)

            if key in existing_bom_lines_map:
                # Update existing line
                existing_line = existing_bom_lines_map.pop(key)
                # Only update quantity if it changed, or other fields if necessary
                if existing_line.product_qty != line_val[2]['product_qty']:
                    bom_line_commands.append((1, existing_line.id, {'product_qty': line_val[2]['product_qty']}))
                # Consider updating other fields if they can change from MO to BOM
            else:
                # Create new line
                bom_line_commands.append((0, 0, line_val[2]))

        # Remove lines that are in BOM but not in MO
        for line_to_remove in existing_bom_lines_map.values():
            bom_line_commands.append((2, line_to_remove.id))

        # 3. Prepare update commands for BOM operations
        operation_commands = []
        existing_bom_ops_map = {
            op.name: op
            for op in self.bom_id.operation_ids
        }

        for op_val in mo_operations_vals:
            op_name = op_val[2]['name']
            if op_name in existing_bom_ops_map:
                # Update existing operation
                existing_op = existing_bom_ops_map.pop(op_name)
                operation_commands.append((1, existing_op.id, op_val[2])) # Update all fields
            else:
                # Create new operation
                operation_commands.append((0, 0, op_val[2]))

        # Remove operations that are in BOM but not in MO
        for op_to_remove in existing_bom_ops_map.values():
            operation_commands.append((2, op_to_remove.id))


        # 4. Prepare update commands for BOM by-products
        byproduct_commands = []
        existing_bom_byproducts_map = {
            (bp.product_id.id, bp.product_uom_id.id): bp
            for bp in self.bom_id.byproduct_ids
        }

        for bp_val in mo_byproduct_vals:
            product_id = bp_val[2]['product_id']
            product_uom_id = bp_val[2]['product_uom_id']
            key = (product_id, product_uom_id)

            if key in existing_bom_byproducts_map:
                # Update existing by-product
                existing_bp = existing_bom_byproducts_map.pop(key)
                if existing_bp.product_qty != bp_val[2]['product_qty']:
                    byproduct_commands.append((1, existing_bp.id, {'product_qty': bp_val[2]['product_qty']}))
            else:
                # Create new by-product
                byproduct_commands.append((0, 0, bp_val[2]))

        # Remove by-products that are in BOM but not in MO
        for bp_to_remove in existing_bom_byproducts_map.values():
            byproduct_commands.append((2, bp_to_remove.id))


        # 5. Prepare values for BOM update (attributes and relations)
        bom_update_vals = {
            'product_tmpl_id': self.product_id.product_tmpl_id.id,
            'product_id': self.product_id.id, # Ensure BOM is linked to the specific product variant
            'product_qty': self.product_qty,
            'product_uom_id': self.product_uom_id.id,
            'code': _("Updated BoM from %(mo_name)s", mo_name=self.display_name), # Update code to reflect update
            'company_id': self.company_id.id,
            'bom_line_ids': bom_line_commands,
            'byproduct_ids': byproduct_commands,
            'operation_ids': operation_commands,
        }

        # Add custom attribute values based on product category
        if hasattr(self.product_id.product_tmpl_id, 'product_category'):
            product_category = self.product_id.product_tmpl_id.product_category
            
            if product_category == 'garment':
                bom_update_vals.update({
                    'run_id': self.run_id.id if self.run_id else False,
                    'colorway_id': self.colorway_id.id if self.colorway_id else False,
                    'size_id': self.size_id.id if self.size_id else False,
                    'is_garment_bom': True,
                    'swatch_number_id': False, # Ensure swatch fields are cleared for garment
                    'body_stitch_id': False,
                    'cuff_stitch_id': False,
                })
            elif product_category == 'swatch':
                bom_update_vals.update({
                    'swatch_number_id': self.swatch_number_id.id if self.swatch_number_id else False,
                    'colorway_id': self.colorway_id.id if self.colorway_id else False,
                    'body_stitch_id': self.body_stitch_id.id if self.body_stitch_id else False,
                    'cuff_stitch_id': self.cuff_stitch_id.id if self.cuff_stitch_id else False,
                    'is_swatch_bom': True,
                    'run_id': False, # Ensure garment fields are cleared for swatch
                    'size_id': False,
                })
            else: # For other products, clear all category-specific attributes
                bom_update_vals.update({
                    'run_id': False,
                    'colorway_id': False,
                    'size_id': False,
                    'swatch_number_id': False,
                    'body_stitch_id': False,
                    'cuff_stitch_id': False,
                    'is_garment_bom': False,
                    'is_swatch_bom': False,
                })
        
        # Add machine and technical data for both categories
        if self.product_category in ('garment', 'swatch'):
            bom_update_vals.update({
                'machine_id': self.machine_id.id if self.machine_id else False,
                'gauge_id': self.gauge_id.id if self.gauge_id else False,
                'machine_file': self.machine_file,
                'machine_filename': self.machine_filename,
                'expected_machine_time': self.expected_machine_time,
                'hs_code': self.hs_code,
                'total_cost': self.total_cost,
            })
        else: # Clear machine/technical data if not garment/swatch
            bom_update_vals.update({
                'machine_id': False,
                'gauge_id': False,
                'machine_file': False,
                'machine_filename': False,
                'expected_machine_time': False,
                'hs_code': False,
                'total_cost': False,
            })

        # 6. Update the BOM
        self.bom_id.write(bom_update_vals)
        
        # Show a success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Bill of Materials has been updated successfully.'),
                'sticky': False,
                'type': 'success',
            },
        }

    def _update_bom_request_from_mo(self):
        """Mirror MO raw components and structure lines to the linked BOM Request."""
        for production in self:
            bom_request = production.bom_request_id
            if not bom_request:
                continue

            component_commands = [(5, 0, 0)]
            for move in production.move_raw_ids.filtered(lambda m: m.state != 'cancel' and not m.scrap_id):
                component_commands.append((0, 0, {
                    'sequence': move.sequence,
                    'product_id': move.product_id.id,
                    'product_qty': move.product_uom_qty,
                    'product_uom_id': move.product_uom.id,
                    'ply': move.x_ply,
                    'left_carrier': move.left_carrier,
                    'right_carrier': move.right_carrier,
                    'structure_id': move.structure_id.id if move.structure_id else False,
                }))

            bom_request.write({'bom_line_ids': component_commands})

            # Sync structure lines from MO back to BOM Request
            if production.structure_ids:
                structure_commands = [(5, 0, 0)]
                for line in production.structure_ids:
                    structure_commands.append((0, 0, {
                        'bom_request_id': bom_request.id,
                        'sequence': line.sequence,
                        'name': line.name,
                        'description': line.description,
                    }))
                bom_request.write({'structure_ids': structure_commands})

            # Sync Excalidraw / CAD fields from MO → BOM Request
            excal_sync_vals = {}
            if production.excalidraw_data_standalone:
                excal_sync_vals['excalidraw_data'] = production.excalidraw_data_standalone
            if production.garment_construction_data_standalone:
                excal_sync_vals['garment_construction_data'] = production.garment_construction_data_standalone
            if production.structure_cad_data:
                excal_sync_vals['structure_cad_data'] = json.dumps(production.structure_cad_data) if isinstance(production.structure_cad_data, dict) else production.structure_cad_data
            if excal_sync_vals:
                bom_request.with_context(skip_mo_cad_sync=True).write(excal_sync_vals)
                logging.info(
                    "[PRODUCE ALL] Synced excalidraw fields %s from MO %s → BOM Request %s",
                    list(excal_sync_vals.keys()), production.name, bom_request.name
                )

    def action_prepare_produce_all(self):
        """Open the Produce All confirmation wizard."""
        self.ensure_one()

        # Validate all work orders are finished
        incomplete_wos = self.workorder_ids.filtered(lambda wo: wo.state != 'done')
        if incomplete_wos:
            wo_names = ', '.join(incomplete_wos.mapped('name'))
            raise ValidationError(
                _("Please complete all work orders before producing.\n\nIncomplete: %s") % wo_names
            )

        # Validate all finished work orders have a duration entered
        no_duration_wos = self.workorder_ids.filtered(
            lambda wo: wo.state == 'done' and not wo.duration
        )
        if no_duration_wos:
            wo_names = ', '.join(no_duration_wos.mapped('name'))
            raise ValidationError(
                _("Please ensure all work orders have a duration.\n\nMissing duration: %s") % wo_names
            )

        view = self.env.ref('maeknit_mfg_customization.view_mrp_produce_all_wizard_form')
        return {
            'name': _('Produce All'),
            'type': 'ir.actions.act_window',
            'res_model': 'maeknit.mrp.produce.all.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': {
                'default_production_id': self.id,
                'default_update_bom': 'yes',
            },
        }
        
    def name_get(self):
        """Override name_get to include attribute information in the display name"""
        result = []
        for record in self:
            name = record.name
            
            # Add attribute information based on product category
            if hasattr(record.product_id.product_tmpl_id, 'product_category'):
                product_category = record.product_id.product_tmpl_id.product_category
                
                if product_category == 'garment':
                    # For garment products, add Run, Colorway, Size
                    attributes = []
                    if record.run_id:
                        attributes.append(f"Run: {record.run_id.name}")
                    if record.colorway_id:
                        attributes.append(f"Colorway: {record.colorway_id.name}")
                    if record.size_id:
                        attributes.append(f"Size: {record.size_id.name}")
                    
                    if attributes:
                        name = f"{name} ({', '.join(attributes)})"
                
                elif product_category == 'swatch':
                    # For swatch products, add Swatch #, Colorway
                    attributes = []
                    if record.swatch_number_id:
                        attributes.append(f"Swatch #: {record.swatch_number_id.name}")
                    if record.colorway_id:
                        attributes.append(f"Colorway: {record.colorway_id.name}")
                    
                    if attributes:
                        name = f"{name} ({', '.join(attributes)})"
            
            result.append((record.id, name))
        return result
    
    def action_view_bom(self):
        """Override to pass the proper context for BOM view"""
        action = super(MrpProduction, self).action_view_bom()
        
        # Add context for proper BOM view based on product category
        if hasattr(self.product_id.product_tmpl_id, 'product_category'):
            product_category = self.product_id.product_tmpl_id.product_category
            
            if product_category == 'garment':
                action['context'] = dict(action.get('context', {}))
                action['context'].update({
                    'default_is_garment_bom': True,
                    'default_is_swatch_bom': False
                })
            elif product_category == 'swatch':
                action['context'] = dict(action.get('context', {}))
                action['context'].update({
                    'default_is_garment_bom': False,
                    'default_is_swatch_bom': True
                })
        
        return action
    
    def action_assign(self):
        """Override to check machine availability before assigning"""
        result = super(MrpProduction, self).action_assign()
        
        # Check machine availability
        for record in self:
            if record.machine_id:
                # Check if the machine is already in use in another production
                conflicting_productions = self.search([
                    ('id', '!=', record.id),
                    ('machine_id', '=', record.machine_id.id),
                    ('state', 'in', ['confirmed', 'planned', 'progress']),
                    ('date_planned_start', '<=', record.date_planned_finished),
                    ('date_planned_finished', '>=', record.date_planned_start)
                ])
                
                if conflicting_productions:
                    # Log a warning about machine conflict
                    logging.info(f" Custom Code: Machine {record.machine_id.name} is already scheduled for use in productions: {', '.join(conflicting_productions.mapped('name'))}")
                    
                    # Add a note to the chatter
                    record.message_post(
                        body=f"Warning: Machine {record.machine_id.name} is already scheduled for use in other productions during this time period.",
                        subject="Machine Scheduling Conflict"
                    )
                    
        return result

    @api.model
    def get_existing_bom_attributes(self, product_id, attribute_name):
        """Get existing attribute values for a product from BOMs"""
        if not product_id:
            return []
        
        product = self.env['product.product'].browse(product_id)
        if not product.exists():
            return []
        
        # Find all BOMs for this product template
        boms = self.env['mrp.bom'].search([
            ('product_tmpl_id', '=', product.product_tmpl_id.id)
        ])
        
        existing_values = []
        for bom in boms:
            if hasattr(bom, attribute_name):
                attr_value = getattr(bom, attribute_name)
                if attr_value:
                    existing_values.append(attr_value.id)
        
        return existing_values

    @api.model
    def get_existing_runs_for_product(self, product_id):
        """Get existing Run values for a product from BOMs"""
        return self.get_existing_bom_attributes(product_id, 'run_id')

    @api.model
    def get_existing_swatches_for_product(self, product_id):
        """Get existing Swatch # values for a product from BOMs"""
        return self.get_existing_bom_attributes(product_id, 'swatch_number_id')

    @api.model
    def get_run_attributes_for_product_template(self, product_tmpl_id, current_run_id=False):
        """
        Returns a list of run attribute values that exist in BOMs for a given product template,
        marking the currently selected run as active.
        """
        if not product_tmpl_id:
            return []

        product_tmpl = self.env['product.template'].browse(product_tmpl_id)
        if not product_tmpl.exists():
            return []

        # Find all BOMs for this product template that have a run_id
        boms_with_runs = self.env['mrp.bom'].search([
            ('product_tmpl_id', '=', product_tmpl_id),
            ('run_id', '!=', False)
        ])
        
        # Get unique run_id records from these BOMs
        unique_run_ids = boms_with_runs.mapped('run_id')
        
        # Sort for consistent display
        sorted_run_values = unique_run_ids.sorted(key=lambda r: r.name)

        result = []
        for run_val in sorted_run_values:
            result.append({
                'id': run_val.id,
                'name': run_val.name,
                'active': run_val.id == current_run_id,
                'has_bom': True, # By definition, these runs come from existing BOMs
            })
        return result


    @api.model
    def get_swatch_attributes_for_product_template(self, product_tmpl_id, current_swatch_id=False):
        """
        Returns a list of swatch attribute values that exist in BOMs for a given product template,
        marking the currently selected swatch as active.
        """
        if not product_tmpl_id:
            return []

        product_tmpl = self.env['product.template'].browse(product_tmpl_id)
        if not product_tmpl.exists():
            return []

        # Find all BOMs for this product template that have a swatch_number_id
        boms_with_swatches = self.env['mrp.bom'].search([
            ('product_tmpl_id', '=', product_tmpl_id),
            ('swatch_number_id', '!=', False)
        ])
        
        # Get unique swatch_number_id records from these BOMs
        unique_swatch_ids = boms_with_swatches.mapped('swatch_number_id')
        
        # Sort for consistent display
        sorted_swatch_values = unique_swatch_ids.sorted(key=lambda s: s.name)

        result = []
        for swatch_val in sorted_swatch_values:
            result.append({
                'id': swatch_val.id,
                'name': swatch_val.name,
                'active': swatch_val.id == current_swatch_id,
                'has_bom': True, # By definition, these swatches come from existing BOMs
            })
        return result

    def action_confirm(self):
        for mo in self:
            # Skip wizard if already shown or if this is a calibration swatch MO
            if not self.env.context.get('skip_calibration_wizard') and mo.product_category == 'garment' and not mo.parent_garment_mo_id:
                # Show wizard asking if user wants to generate calibration swatch
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Generate Calibration Swatch?'),
                    'res_model': 'calibration.swatch.confirm.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_mo_id': mo.id,
                        'default_generate_swatch': False,
                    },
                }
            
            # Check if any work orders are missing workcenters
            workorders_without_workcenter = mo.workorder_ids.filtered(lambda wo: not wo.workcenter_id)
            
            if workorders_without_workcenter:
                workorder_names = ', '.join(workorders_without_workcenter.mapped('name'))
                raise ValidationError(_(
                    "Cannot confirm Manufacturing Order. The following work orders are missing a Work Center:\n%s\n\n"
                    "Please assign a Work Center to all work orders before confirming."
                ) % workorder_names)
            
            # Existing BOM generation logic
            if not mo._is_called_from_crm_lead_sales_order():
                if not mo.bom_id and (
                        (mo.product_category == 'garment' and not mo.run_exists_in_bom) or
                        (mo.product_category == 'swatch' and not mo.swatch_exists_in_bom)
                    ):
                        mo.action_generate_bom()

            # Sync product to BOM's specific variant (with size/colorway)
            # so the MO lines show the correct variant before producing
            if mo.bom_id and mo.bom_id.product_id and mo.bom_id.product_id != mo.product_id:
                mo.product_id = mo.bom_id.product_id

        return super(MrpProduction, self).action_confirm()

    def action_print_mfg_sheet(self):
        """Print the MFG Sheet PDF for this Manufacturing Order."""
        self.ensure_one()
        return self.env.ref('maeknit_mfg_customization.action_report_mfg_sheet').report_action(self)

    def _is_called_from_crm_lead_sales_order(self):

        ctx = self.env.context
        params = ctx.get('params') or {}

        logging.info("Context in helper: %s", ctx)

        return (
            ctx.get('active_model') == 'crm.lead'
            or params.get('action') == 'sales'
        )

    def action_open_bom_request(self):
        """Open the related BOM Request form view"""
        self.ensure_one()
        if not self.bom_request_id:
            raise ValidationError(_("No BOM Request is linked to this Manufacturing Order."))

        return {
            'name': 'BOM Request',
            'type': 'ir.actions.act_window',
            'res_model': 'maeknit.bom.request',
            'view_mode': 'form',
            'res_id': self.bom_request_id.id,
            'target': 'current',
        }

    def action_open_bom_duplicate_wizard(self):
        """Launch the duplicate/variant BOM request wizard for the linked BOM request."""
        self.ensure_one()
        if not self.bom_request_id:
            raise ValidationError(_("No BOM Request is linked to this Manufacturing Order."))
        if not self.bom_id:
            raise ValidationError(_("A Bill of Materials must be linked before duplicating a BOM request."))
        is_swatch_service = self.rel_service and self.rel_service.name == 'Swatch Service'
        if is_swatch_service and not self.colorway_id:
            raise ValidationError(_("Select a colorway on the Manufacturing Order before duplicating the BOM request."))

        action = self.env.ref('maeknit_sales_customization.action_bom_duplicate_wizard')
        result = action.read()[0]
        context_value = result.get('context')
        if isinstance(context_value, dict):
            ctx = dict(context_value)
        else:
            ctx = safe_eval(context_value) if context_value else {}
        logging.info(" Custom Code: Launching BOM Duplicate Wizard from MO %s with BOM Request %s", self.name, self.bom_request_id.name)
        ctx = dict(ctx,
            default_source_bom_request_id=self.bom_request_id.id,
            default_source_mo_id=self.id,
        )
        logging.info(" Custom Code: Context for BOM Duplicate Wizard: %s", ctx)
        result['context'] = ctx
        return result
    
    @api.depends('workorder_ids.program_attachment_count', 'workorder_ids.instruction_attachment_count')
    def _compute_workorder_attachment_count(self):
        """Compute total number of attachments across all workorders"""
        for production in self:
            total_count = 0
            for workorder in production.workorder_ids:
                total_count += workorder.program_attachment_count
                total_count += workorder.instruction_attachment_count
            production.workorder_attachment_count = total_count
    
    def action_view_workorder_attachments(self):
        """Open a view showing all attachments from all workorders"""
        self.ensure_one()
        workorder_ids = self.workorder_ids.ids
        
        return {
            'name': 'Work Order Attachments',
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'tree,form',
            'domain': [
                ('res_model', '=', 'mrp.workorder'),
                ('res_id', 'in', workorder_ids)
            ],
            'context': {
                'default_res_model': 'mrp.workorder',
            },
        }

    def _process_measurement_panel_images_for_mo(self, vals):
        """
        Convert base64 image data-URLs in panel CAD JSON to ir.attachment records
        linked to this mrp.production record.  Called when no bom_request_id exists.
        Mirrors the logic in maeknit.bom.request._process_measurement_panel_images().
        """
        self.ensure_one()
        measurement_data = vals.get('measurement_widget_data')
        if not measurement_data:
            return vals

        if isinstance(measurement_data, str):
            try:
                measurement_data = json.loads(measurement_data)
            except (ValueError, json.JSONDecodeError):
                return vals

        measurement_data = dict(measurement_data)

        try:
            panels_to_process = {}

            custom_panels = measurement_data.get('customPanels', [])
            if isinstance(custom_panels, list):
                for cp in custom_panels:
                    if isinstance(cp, dict) and 'id' in cp:
                        pid = cp['id']
                        if pid in measurement_data and isinstance(measurement_data[pid], dict):
                            panels_to_process[pid] = measurement_data[pid]

            struct_panels = measurement_data.get('structurePanels', [])
            if isinstance(struct_panels, list):
                for sp in struct_panels:
                    if isinstance(sp, dict) and 'id' in sp:
                        pid = sp['id']
                        if pid in measurement_data and isinstance(measurement_data[pid], dict):
                            panels_to_process[pid] = measurement_data[pid]

            def _extract(panel_name, panel_data, image_field, att_field, suffix=''):
                image_data = panel_data.get(image_field)
                if not image_data:
                    return
                if panel_data.get(att_field) and not (
                    isinstance(image_data, str) and image_data.startswith('data:image')
                ):
                    return
                if not isinstance(image_data, str) or not image_data.startswith('data:image'):
                    return
                try:
                    if ',' not in image_data:
                        return
                    header, b64 = image_data.split(',', 1)
                    mime = 'image/png'
                    ext = 'png'
                    if 'jpeg' in header.lower() or 'jpg' in header.lower():
                        mime, ext = 'image/jpeg', 'jpg'
                    elif 'gif' in header.lower():
                        mime, ext = 'image/gif', 'gif'
                    att = self.env['ir.attachment'].create({
                        'name': f'panel_{panel_name}{suffix}.{ext}',
                        'res_model': 'mrp.production',
                        'res_id': self.id,
                        'type': 'binary',
                        'datas': b64,
                        'mimetype': mime,
                        'res_field': 'measurement_widget_data',
                    })
                    panel_data[att_field] = att.id
                    del panel_data[image_field]
                    logging.info(
                        "[MO_PANEL_IMG] Created attachment %s for panel '%s%s' on MO %s",
                        att.id, panel_name, suffix, self.name
                    )
                except Exception as e:
                    logging.error("[MO_PANEL_IMG] Failed for panel '%s%s': %s", panel_name, suffix, e)

            for name, pdata in panels_to_process.items():
                _extract(name, pdata, 'image', 'image_attachment_id')
                _extract(name, pdata, 'image2', 'image2_attachment_id', suffix='_2')

            vals['measurement_widget_data'] = measurement_data

        except Exception as e:
            logging.error("[MO_PANEL_IMG] Outer error: %s", e)

        return vals


    def _split_structure_cad_standalone(self, data_dict):
        """
        Extract Excalidraw files from structure_cad_data on a standalone MO
        (no bom_request_id).  Mirrors _split_structure_cad_files on bom.request
        but links attachments to mrp.production.
        Returns a clean dict with fileIds instead of files, or None on failure.
        """
        self.ensure_one()
        files = data_dict.get('files', {})
        if not files:
            return None
        file_ids_map = {}
        for file_id, file_data in files.items():
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
                    'res_model': 'mrp.production',
                    'type': 'binary',
                    'datas': b64,
                    'mimetype': mime_type,
                })
                file_ids_map[file_id] = att.id
                logging.info("[MO_STRUCT_CAD] Extracted file %s → attachment %s on MO %s", file_id[:8], att.id, self.name)
            except Exception as e:
                logging.error("[MO_STRUCT_CAD] Failed: %s", e)
        if not file_ids_map:
            return None
        return {
            'elements': data_dict.get('elements', []),
            'appState': data_dict.get('appState', {}),
            'fileIds': file_ids_map,
        }

    def _split_excalidraw_files_standalone(self, data_dict, field_prefix, existing_file_ids=None):
        """
        Extract Excalidraw image files from any standalone Excalidraw field
        (excalidraw_data_standalone, garment_construction_data_standalone).
        Creates ir.attachment records linked to this MO.
        Returns a clean dict with fileIds, or None if nothing was extracted.
        """
        self.ensure_one()
        files = data_dict.get('files', {})
        if not files:
            return None
        file_ids_map = dict(existing_file_ids or {})
        # Preserve any fileIds already in the incoming data
        for fid, att_id in data_dict.get('fileIds', {}).items():
            if fid not in file_ids_map:
                file_ids_map[fid] = att_id
        extracted = False
        for file_id, file_data in files.items():
            if file_id in file_ids_map:
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
                    'name': f'{field_prefix}_{file_id[:8]}.{ext}',
                    'res_model': 'mrp.production',
                    'type': 'binary',
                    'datas': b64,
                    'mimetype': mime_type,
                })
                file_ids_map[file_id] = att.id
                extracted = True
                logging.info("[MO_%s] Extracted file %s → attachment %s", field_prefix.upper(), file_id[:8], att.id)
            except Exception as e:
                logging.error("[MO_%s] Failed to extract file %s: %s", field_prefix.upper(), file_id[:8], e)
        if not file_ids_map:
            return None
        return {
            'elements': data_dict.get('elements', []),
            'appState': data_dict.get('appState', {}),
            'fileIds': file_ids_map,
        }

    def _process_artwork_standalone(self, raw):
        """
        Extract base64 images from artwork_data_standalone items and store as ir.attachment.
        Returns the cleaned JSON string, or None if no changes needed.
        """
        self.ensure_one()
        if not raw:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict) or not data.get('items'):
            return None
        changed = False
        for item in data['items']:
            if not isinstance(item, dict):
                continue
            if item.get('attachment_id'):
                continue
            data_url = item.get('data', '')
            if not isinstance(data_url, str) or not data_url.startswith('data:image'):
                continue
            if ',' not in data_url:
                continue
            header, b64 = data_url.split(',', 1)
            mime_type = item.get('mimeType', '')
            if not mime_type:
                mime_type = 'image/jpeg' if ('jpeg' in header or 'jpg' in header) else ('image/gif' if 'gif' in header else 'image/png')
            ext = 'jpg' if 'jpeg' in mime_type else ('gif' if 'gif' in mime_type else 'png')
            try:
                att = self.env['ir.attachment'].create({
                    'name': item.get('filename') or f'artwork.{ext}',
                    'res_model': 'mrp.production',
                    'res_id': self.id,
                    'type': 'binary',
                    'datas': b64,
                    'mimetype': mime_type,
                })
                item['attachment_id'] = att.id
                item['data'] = f'/web/image/{att.id}'
                changed = True
                logging.info("[MO_ARTWORK] Extracted artwork file → attachment %s", att.id)
            except Exception as e:
                logging.error("[MO_ARTWORK] Failed to extract artwork: %s", e)
        if not changed:
            return None
        return json.dumps(data)

    def _extract_cad_json_image_standalone(self, cad_dict, field_label):
        """
        Extract a base64 data URL from a CAD JSON dict and store it as an
        ir.attachment linked to this MO (used when there is no bom_request_id).
        Returns the cleaned dict with image_attachment_id set, or None on failure.
        field_label is used only for the attachment name / log messages.
        """
        self.ensure_one()
        image_val = cad_dict.get('image', '')
        if not isinstance(image_val, str) or not image_val.startswith('data:image'):
            return None
        if ',' not in image_val:
            return None
        header, b64_data = image_val.split(',', 1)
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
                'name': f'{field_label}_image.{ext}',
                'res_model': 'mrp.production',
                'res_id': self.id,
                'type': 'binary',
                'datas': b64_data,
                'mimetype': mime_type,
            })
            cleaned = dict(cad_dict)
            cleaned['image_attachment_id'] = att.id
            cleaned.pop('image', None)
            logging.info("[MO_CAD_STANDALONE] Extracted %s image → attachment %s on MO %s", field_label, att.id, self.name)
            return cleaned
        except Exception as e:
            logging.error("[MO_CAD_STANDALONE] Failed to extract %s image: %s", field_label, e)
            return None

    def write(self, vals):
        # ------------------------------------------------------
        # 1. PER-RECORD WRITE (avoids Expected singleton errors)
        # ------------------------------------------------------
        results = True
        for rec in self:
            rec_vals = dict(vals)

            if rec_vals.get('measurement_widget_data'):
                if rec.bom_request_id:
                    processed_vals = rec.bom_request_id._process_measurement_panel_images({
                        'measurement_widget_data': rec_vals['measurement_widget_data']
                    })
                else:
                    processed_vals = rec._process_measurement_panel_images_for_mo({
                        'measurement_widget_data': rec_vals['measurement_widget_data']
                    })
                rec_vals['measurement_widget_data'] = processed_vals.get(
                    'measurement_widget_data',
                    rec_vals['measurement_widget_data']
                )

            # ------------------------------------------------------------------
            # PRE-WRITE: Extract base64 images from CAD JSON fields BEFORE saving
            # to DB so raw base64 is never stored.  For each field:
            #   - If linked BOM request exists → delegate (BOM request extracts
            #     image → ir.attachment and we read back the clean JSON).
            #   - Otherwise → extract directly on MO as ir.attachment.
            # ------------------------------------------------------------------
            whole_cad_pre_synced = False
            cad_pom_pre_synced = False
            structure_cad_pre_synced = False
            if not rec.env.context.get('skip_bom_request_cad_sync'):
                # --- whole_cad_data ---
                if 'whole_cad_data' in rec_vals:
                    cad_val = rec_vals['whole_cad_data']
                    raw_image = cad_val.get('image', '') if isinstance(cad_val, dict) else ''
                    if isinstance(raw_image, str) and raw_image.startswith('data:image'):
                        if rec.bom_request_id:
                            rec.bom_request_id.with_context(skip_mo_cad_sync=True).write(
                                {'whole_cad_data': cad_val}
                            )
                            rec.env.cr.flush()
                            rec.bom_request_id.invalidate_recordset(['whole_cad_data'])
                            cleaned = rec.bom_request_id.whole_cad_data
                            if cleaned and isinstance(cleaned, dict) and cleaned.get('image_attachment_id'):
                                rec_vals['whole_cad_data'] = cleaned
                                whole_cad_pre_synced = True
                                logging.info(
                                    "[MO_CAD_SYNC] Pre-extracted whole_cad base64 for MO %s → attachment %s",
                                    rec.name, cleaned.get('image_attachment_id')
                                )
                        else:
                            cleaned = rec._extract_cad_json_image_standalone(cad_val, 'whole_cad')
                            if cleaned:
                                rec_vals['whole_cad_data'] = cleaned
                                whole_cad_pre_synced = True

                # --- cad_pom_data ---
                if 'cad_pom_data' in rec_vals:
                    pom_val = rec_vals['cad_pom_data']
                    raw_image = pom_val.get('image', '') if isinstance(pom_val, dict) else ''
                    if isinstance(raw_image, str) and raw_image.startswith('data:image'):
                        if rec.bom_request_id:
                            rec.bom_request_id.with_context(skip_mo_cad_sync=True).write(
                                {'cad_pom_data': pom_val}
                            )
                            rec.env.cr.flush()
                            rec.bom_request_id.invalidate_recordset(['cad_pom_data'])
                            cleaned = rec.bom_request_id.cad_pom_data
                            if cleaned and isinstance(cleaned, dict) and cleaned.get('image_attachment_id'):
                                rec_vals['cad_pom_data'] = cleaned
                                cad_pom_pre_synced = True
                                logging.info(
                                    "[MO_CAD_SYNC] Pre-extracted cad_pom base64 for MO %s → attachment %s",
                                    rec.name, cleaned.get('image_attachment_id')
                                )
                        else:
                            cleaned = rec._extract_cad_json_image_standalone(pom_val, 'cad_pom')
                            if cleaned:
                                rec_vals['cad_pom_data'] = cleaned
                                cad_pom_pre_synced = True

                # --- structure_cad_data (Excalidraw format: files[hash].dataURL) ---
                if 'structure_cad_data' in rec_vals and rec_vals['structure_cad_data']:
                    struct_val = rec_vals['structure_cad_data']
                    try:
                        struct_dict = json.loads(struct_val) if isinstance(struct_val, str) else struct_val
                    except (ValueError, TypeError):
                        struct_dict = None
                    has_raw_files = (
                        isinstance(struct_dict, dict)
                        and struct_dict.get('files')
                        and any(
                            isinstance(f, dict) and isinstance(f.get('dataURL', ''), str)
                            and f.get('dataURL', '').startswith('data:image')
                            for f in struct_dict['files'].values()
                        )
                    )
                    if has_raw_files:
                        # Always extract directly on the MO — images are owned by the MO, not the BOM request
                        cleaned_struct = rec._split_structure_cad_standalone(struct_dict)
                        if cleaned_struct:
                            rec_vals['structure_cad_data'] = cleaned_struct
                            structure_cad_pre_synced = True

            # --- Standalone Excalidraw fields: extract raw base64 → ir.attachment ---
            for standalone_field in ('excalidraw_data_standalone', 'garment_construction_data_standalone'):
                if standalone_field in rec_vals and rec_vals[standalone_field]:
                    exc_val = rec_vals[standalone_field]
                    try:
                        exc_dict = exc_val if isinstance(exc_val, dict) else json.loads(exc_val)
                    except (ValueError, TypeError):
                        exc_dict = None
                    if isinstance(exc_dict, dict):
                        has_raw = (
                            isinstance(exc_dict.get('files'), dict)
                            and any(
                                isinstance(f, dict)
                                and isinstance(f.get('dataURL', ''), str)
                                and f.get('dataURL', '').startswith('data:image')
                                for f in exc_dict['files'].values()
                            )
                        )
                        if has_raw:
                            existing_data = getattr(rec, standalone_field, None) or {}
                            existing_file_ids = existing_data.get('fileIds', {}) if isinstance(existing_data, dict) else {}
                            cleaned = rec._split_excalidraw_files_standalone(
                                exc_dict, standalone_field, existing_file_ids
                            )
                            if cleaned:
                                rec_vals[standalone_field] = cleaned

            # --- artwork_data_standalone: extract raw base64 → ir.attachment ---
            if 'artwork_data_standalone' in rec_vals and rec_vals['artwork_data_standalone']:
                cleaned_artwork = rec._process_artwork_standalone(rec_vals['artwork_data_standalone'])
                if cleaned_artwork is not None:
                    rec_vals['artwork_data_standalone'] = cleaned_artwork

            # Normalize fields.Json fields that widgets may send as JSON strings
            # (Odoo double-encodes when a string is passed to fields.Json)
            for json_field in ('structure_cad_data', 'excalidraw_data_standalone',
                               'garment_construction_data_standalone', 'calibration_data'):
                if json_field in rec_vals and isinstance(rec_vals[json_field], str):
                    try:
                        rec_vals[json_field] = json.loads(rec_vals[json_field])
                    except (ValueError, TypeError):
                        pass

            # Perform write for this specific record (whole_cad_data is already clean)
            result = super(MrpProduction, rec).write(rec_vals)
            if results is True:
                results = result  # Keep first result reference

            # ------------------------------------------------------
            # 2. CAD SYNC (only if relevant fields in this write)
            # ------------------------------------------------------
            if not rec.env.context.get('skip_bom_request_cad_sync'):
                cad_fields_to_sync = {}

                # Skip fields already synced in the pre-write block above
                if 'whole_cad_data' in rec_vals and not whole_cad_pre_synced:
                    cad_fields_to_sync['whole_cad_data'] = rec_vals['whole_cad_data']
                if 'cad_pom_data' in rec_vals and not cad_pom_pre_synced:
                    cad_fields_to_sync['cad_pom_data'] = rec_vals['cad_pom_data']
                if 'measurement_widget_data' in rec_vals:
                    cad_fields_to_sync['measurement_widget_data'] = rec_vals['measurement_widget_data']
                # structure_cad_data is MO-owned — not synced to BOM request

                if cad_fields_to_sync and rec.bom_request_id:
                    rec.bom_request_id.with_context(skip_mo_cad_sync=True).write(cad_fields_to_sync)
                    rec.env.cr.flush()
                    rec.bom_request_id.invalidate_recordset(['whole_cad_data', 'cad_pom_data', 'measurement_widget_data'])
                    logging.info(
                        "[MO_CAD_SYNC] Synced CAD data from MO %s to BOM Request %s: %s",
                        rec.name,
                        rec.bom_request_id.name,
                        list(cad_fields_to_sync.keys())
                    )

            if not rec.env.context.get('skip_bom_request_calibration_sync'):
                if 'calibration_data' in rec_vals and rec.bom_request_id:
                    rec.bom_request_id.with_context(skip_mo_calibration_sync=True).write({
                        'calibration_data': rec_vals['calibration_data']
                    })
                    logging.info(
                        "[MO_CALIBRATION_SYNC] Synced calibration data from MO %s to BOM Request %s",
                        rec.name,
                        rec.bom_request_id.name
                    )

            # ------------------------------------------------------
            # 3. RENDER SYNC (style_3d_link and render_image_ids)
            # ------------------------------------------------------
            if not rec.env.context.get('skip_bom_request_render_sync'):
                render_fields_to_sync = {}

                if 'style_3d_link' in rec_vals:
                    render_fields_to_sync['style_3d_link'] = rec_vals['style_3d_link']

                if 'render_image_ids' in rec_vals and rec.bom_request_id:
                    # Sync render images from MO to BOM Request
                    # Delete existing render images on BOM Request
                    rec.bom_request_id.render_image_ids.unlink()

                    # Create new render images on BOM Request
                    for img in rec.render_image_ids:
                        rec.env['render.image.line'].create({
                            'name': img.name,
                            'sequence': img.sequence,
                            'image': img.image,
                            'image_filename': img.image_filename,
                            'bom_request_id': rec.bom_request_id.id,
                        })

                if render_fields_to_sync and rec.bom_request_id:
                    rec.bom_request_id.with_context(skip_mo_render_sync=True).write(render_fields_to_sync)
                    logging.info(
                        "[MO_RENDER_SYNC] Synced render data from MO %s to BOM Request %s: %s",
                        rec.name,
                        rec.bom_request_id.name,
                        list(render_fields_to_sync.keys())
                    )

        return results

    def action_add_render_image(self):
        """Add render image slots: 4 on first click, 1 on subsequent clicks."""
        self.ensure_one()
        existing = len(self.render_image_ids)
        count = 4 if existing == 0 else 1
        for i in range(count):
            self.env['render.image.line'].create({
                'name': f'Render Image {existing + i + 1}',
                'sequence': (existing + i + 1) * 10,
                'production_id': self.id,
            })
        return True

    def button_request_new_program(self):
        """
        Create a new workorder for the next Program version AND corresponding Knit version.
        Searches for existing Program workorders in the CURRENT manufacturing order,
        finds the highest version, and creates workorders for the next version.
        If the shopfloor operations don't exist, they are created automatically.
        The sequence will be: Program V1, Knit V1, Program V2, Knit V2, etc.
        Uses the same workcenters as the most recent Program/Knit workorders.
        """
        self.ensure_one()
        
        existing_program_workorders = self.workorder_ids.filtered(
            lambda wo: wo.name.startswith('Program V')
        )
        
        max_version = 0
        last_program_workorder = None
        for workorder in existing_program_workorders:
            try:
                version_str = workorder.name.split('V')[-1].strip()
                version_num = int(version_str)
                if version_num > max_version:
                    max_version = version_num
                    last_program_workorder = workorder
            except (ValueError, IndexError):
                logging.info(f" Custom Code: Could not parse version from workorder name: {workorder.name}")
                continue
        
        next_version = max_version + 1
        next_program_name = f"Program V{next_version}"
        
        existing_knit_workorders = self.workorder_ids.filtered(
            lambda wo: wo.name.startswith('Knit V')
        )
        max_knit_version = 0
        last_knit_workorder = None
        for workorder in existing_knit_workorders:
            try:
                version_str = workorder.name.split('V')[-1].strip()
                version_num = int(version_str)
                if version_num > max_knit_version:
                    max_knit_version = version_num
                    last_knit_workorder = workorder
            except (ValueError, IndexError):
                logging.info(f" Custom Code: Could not parse version from workorder name: {workorder.name}")
                continue
        
        next_knit_version = max_knit_version + 1
        next_knit_name = f"Knit V{max_knit_version + 1}"
        
        # Check if shopfloor operations exist for both Program and Knit
        next_program_operation = self.env['maeknit.shopfloor.operation'].search([
            ('name', '=', next_program_name)
        ], limit=1)
        
        next_knit_operation = self.env['maeknit.shopfloor.operation'].search([
            ('name', '=', next_knit_name)
        ], limit=1)
        
        # Create Program operation if it doesn't exist
        if not next_program_operation:
            existing_program_operation = self.env['maeknit.shopfloor.operation'].search([
                ('name', 'ilike', 'Program V%')
            ], limit=1)
            
            operation_vals = {'name': next_program_name}
            if existing_program_operation and existing_program_operation.workcenter_tag_ids:
                operation_vals['workcenter_tag_ids'] = [(6, 0, existing_program_operation.workcenter_tag_ids.ids)]
            
            next_program_operation = self.env['maeknit.shopfloor.operation'].create(operation_vals)
            logging.info(f" Custom Code: Created new shopfloor operation: {next_program_name}")
        
        # Create Knit operation if it doesn't exist
        if not next_knit_operation:
            existing_knit_operation = self.env['maeknit.shopfloor.operation'].search([
                ('name', 'ilike', 'Knit V%')
            ], limit=1)
            
            operation_vals = {'name': next_knit_name}
            if existing_knit_operation and existing_knit_operation.workcenter_tag_ids:
                operation_vals['workcenter_tag_ids'] = [(6, 0, existing_knit_operation.workcenter_tag_ids.ids)]
            
            next_knit_operation = self.env['maeknit.shopfloor.operation'].create(operation_vals)
            logging.info(f" Custom Code: Created new shopfloor operation: {next_knit_name}")
        
        # --------------------------------------------------
        # Workcenters: use the same as last existing Program/Knit
        # --------------------------------------------------
        program_workcenter = False
        if last_program_workorder and last_program_workorder.workcenter_id:
            program_workcenter = last_program_workorder.workcenter_id
        else:
            program_workcenter = self.env['mrp.workcenter'].search([], limit=1)
        
        last_knit_workorder = self.workorder_ids.filtered(
            lambda wo: wo.name == f"Knit V{max_knit_version}"
        )
        if last_knit_workorder and last_knit_workorder.workcenter_id:
            knit_workcenter = last_knit_workorder.workcenter_id
        else:
            knit_workcenter = self.env['mrp.workcenter'].search([], limit=1)
        
        if not program_workcenter or not knit_workcenter:
            self.message_post(
                body=_('Error: No workcenter found for operations %s or %s') % (next_program_name, next_knit_name),
                subject='Program/Knit Request Error'
            )
            return True
        
        # Calculate sequence positions - we need to insert TWO workorders
        if existing_program_workorders:
            last_knit_workorder = self.workorder_ids.filtered(
                lambda wo: wo.name == f"Knit V{max_knit_version}"
            )
            
            if last_knit_workorder:
                base_sequence = max(last_knit_workorder.mapped('sequence'))
            else:
                base_sequence = max(existing_program_workorders.mapped('sequence'))
            
            program_sequence = base_sequence + 1
            knit_sequence = base_sequence + 2
        else:
            program_sequence = 2
            knit_sequence = 3
        
        # Shift all workorders with sequence >= program_sequence down by 2
        workorders_to_shift = self.workorder_ids.filtered(lambda wo: wo.sequence >= program_sequence)
        for workorder in workorders_to_shift:
            workorder.sequence += 2
        
        # Create the new Program workorder
        program_workorder_vals = {
            'production_id': self.id,
            'name': next_program_name,
            'workcenter_id': program_workcenter.id,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom_id.id,
            'company_id': self.company_id.id,
            'sequence': program_sequence,
            'state': 'waiting',
        }
        
        if last_program_workorder and last_program_workorder.employee_assigned_ids:
            program_workorder_vals['employee_assigned_ids'] = [(6, 0, last_program_workorder.employee_assigned_ids.ids)]
            logging.info(f" Custom Code: Copied {len(last_program_workorder.employee_assigned_ids)} assigned employees to {next_program_name}")
        
        name_final = next_program_name
        ShopOp = self.env['maeknit.shopfloor.operation']
        shop_op = ShopOp.search([
                    ('name', '=ilike', name_final)
                ], limit=1)
        if shop_op:
            program_workorder_vals['shopfloor_operation_id'] = shop_op.id

        new_program_workorder = self.env['mrp.workorder'].create(program_workorder_vals)
        logging.info(f" Custom Code: Created workorder {new_program_workorder.name} at sequence {program_sequence}")
        
        # Create the new Knit workorder immediately after Program
        knit_workorder_vals = {
            'production_id': self.id,
            'name': next_knit_name,
            'workcenter_id': knit_workcenter.id,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom_id.id,
            'company_id': self.company_id.id,
            'sequence': knit_sequence,
            'state': 'waiting',
        }
        
        # Copy employees from the previous Knit workorder if it exists
        last_knit_for_employees = self.workorder_ids.filtered(
            lambda wo: wo.name == f"Knit V{max_knit_version}"
        )
        if last_knit_for_employees and last_knit_for_employees.employee_assigned_ids:
            knit_workorder_vals['employee_assigned_ids'] = [(6, 0, last_knit_for_employees.employee_assigned_ids.ids)]
            logging.info(f" Custom Code: Copied {len(last_knit_for_employees.employee_assigned_ids)} assigned employees to {next_knit_name}")
        
        name_final = next_knit_name
        ShopOp = self.env['maeknit.shopfloor.operation']
        shop_op = ShopOp.search([
                    ('name', '=ilike', name_final)
                ], limit=1)
        if shop_op:
            knit_workorder_vals['shopfloor_operation_id'] = shop_op.id
        new_knit_workorder = self.env['mrp.workorder'].create(knit_workorder_vals)
        logging.info(f" Custom Code: Created workorder {new_knit_workorder.name} at sequence {knit_sequence}")
        
        later_wos = self.workorder_ids.filtered(lambda w: w.sequence > knit_sequence)
        if later_wos:
            later_wos.write({'state': 'waiting'})
            logging.info(f" Custom Code: [REQUEST_NEW_PROGRAM] Set {len(later_wos)} later workorders to waiting after {new_knit_workorder.name}")

        user_names = ['Kadri', 'Sevan']
        mentions = []

        for name in user_names:
            user = self.env['res.users'].search([('name', 'ilike', name)], limit=1)
            if user:
                mention_html = (
                    f'<a href="#" data-oe-model="res.users" '
                    f'data-oe-id="{user.id}">@{user.name}</a>'
                )
                mentions.append(mention_html)

        # Combine mentions (space separated)
        mention_text = ' '.join(mentions) + ' ' if mentions else ''

        self.message_post(
            body=_('%s Program "%s" and Knit "%s" created.') %
                (mention_text, next_program_name, next_knit_name),
            subject='New Program and Knit Requested'
        )
        
        return True

    def action_request_new_program(self):
        """Open the Re-program wizard for the latest Knit work order."""
        self.ensure_one()
        knit_wos = self.workorder_ids.filtered(lambda wo: wo.is_knit_workorder)
        if not knit_wos:
            raise UserError(_("No Knit work order found for this Manufacturing Order."))
        latest_knit = knit_wos.sorted('sequence')[-1]
        return latest_knit.action_request_new_program()

    def action_remanufacture(self):
        """Open Re-manufacturing wizard showing all work orders to restart from."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Re-manufacturing',
            'res_model': 'workorder.restart.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('maeknit_mfg_customization.view_remanufacture_wizard_form').id,
            'target': 'new',
            'context': {
                'default_production_id': self.id,
            },
        }

    def button_request_new_knit_only(self):
        """
        Create ONLY the next Knit version (no Program).
        Follows the same sequencing, workcenter, employee copy rules.
        """
        self.ensure_one()

        # Find existing Knit workorders
        existing_knit_wos = self.workorder_ids.filtered(
            lambda wo: wo.name.startswith('Knit V')
        )

        max_version = 0
        last_knit_wo = None
        for wo in existing_knit_wos:
            try:
                v = int(wo.name.split('V')[-1].strip())
                if v > max_version:
                    max_version = v
                    last_knit_wo = wo
            except Exception:
                continue

        next_version = max_version + 1
        next_knit_name = f"Knit V{next_version}"

        # Shopfloor operation
        ShopOp = self.env['maeknit.shopfloor.operation']
        knit_op = ShopOp.search([('name', '=', next_knit_name)], limit=1)
        if not knit_op:
            existing_knit_op = ShopOp.search([('name', 'ilike', 'Knit V%')], limit=1)
            vals = {'name': next_knit_name}
            if existing_knit_op and existing_knit_op.workcenter_tag_ids:
                vals['workcenter_tag_ids'] = [(6, 0, existing_knit_op.workcenter_tag_ids.ids)]
            knit_op = ShopOp.create(vals)

        # Workcenter
        knit_wc = (
            last_knit_wo.workcenter_id
            if last_knit_wo and last_knit_wo.workcenter_id
            else self.env['mrp.workcenter'].search([], limit=1)
        )

        # Sequence
        base_seq = max(existing_knit_wos.mapped('sequence')) if existing_knit_wos else 1
        knit_sequence = base_seq + 1

        # Shift later workorders
        later_wos = self.workorder_ids.filtered(lambda w: w.sequence >= knit_sequence)
        for wo in later_wos:
            wo.sequence += 1

        # Create Knit WO
        vals = {
            'production_id': self.id,
            'name': next_knit_name,
            'workcenter_id': knit_wc.id,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom_id.id,
            'company_id': self.company_id.id,
            'sequence': knit_sequence,
            'state': 'waiting',
            'shopfloor_operation_id': knit_op.id,
        }

        if last_knit_wo and last_knit_wo.employee_assigned_ids:
            vals['employee_assigned_ids'] = [(6, 0, last_knit_wo.employee_assigned_ids.ids)]

        new_knit = self.env['mrp.workorder'].create(vals)

        # Set everything after to waiting
        self.workorder_ids.filtered(lambda w: w.sequence > knit_sequence)\
            .write({'state': 'waiting'})

        self.message_post(
            body=_('Knit "%s" upgraded.') % next_knit_name,
            subject='New Knit Requested'
        )

        return True

    @api.depends('workorder_ids', 'workorder_ids.has_instruction_files', 'workorder_ids.has_program_files')
    def _compute_has_files(self):
        """Check if any work orders have instruction or program files"""
        for production in self:
            production.has_instruction_files = any(production.workorder_ids.mapped('has_instruction_files'))
            production.has_program_files = any(production.workorder_ids.mapped('has_program_files'))

    @api.depends('workorder_ids', 'workorder_ids.has_program_files', 'workorder_ids.is_knit_workorder', 'workorder_ids.is_program_workorder')
    def _compute_latest_program_workorder_id(self):
        """Find the latest Knit/Program workorder that has program files attached"""
        for production in self:
            program_wos = production.workorder_ids.filtered(
                lambda wo: (wo.is_knit_workorder or wo.is_program_workorder) and wo.has_program_files
            )
            if program_wos:
                production.latest_program_workorder_id = program_wos.sorted('sequence', reverse=True)[0]
            else:
                production.latest_program_workorder_id = False

    def action_view_latest_program_files(self):
        """Open program files wizard for the latest Knit/Program workorder"""
        self.ensure_one()
        if not self.latest_program_workorder_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Program Files',
                    'message': 'No program files found on any Knit or Program work orders.',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        view = self.env.ref('maeknit_mfg_customization.view_workorder_attachment_wizard_form')
        return {
            'name': 'Program Files',
            'type': 'ir.actions.act_window',
            'res_model': 'workorder.attachment.wizard',
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
            'context': {
                'default_workorder_id': self.latest_program_workorder_id.id,
                'default_attachment_type': 'program',
            },
        }
    
    def action_manage_instruction_files(self):
        """Open a view to manage instruction files across all work orders"""
        self.ensure_one()
        
        # Get all work orders with instruction files
        workorders_with_instructions = self.workorder_ids.filtered(lambda wo: wo.has_instruction_files)
        
        if not workorders_with_instructions:
            # If no work orders have instructions yet, open the first work order's wizard
            if self.workorder_ids:
                return self.workorder_ids[0].action_upload_instruction_files()
            else:
                raise ValidationError(_("No work orders found for this Manufacturing Order."))
        
        # Open a tree view of work orders to select which one to manage
        return {
            'name': _('Manage Instruction Files'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.workorder',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.workorder_ids.ids)],
            'context': {
                'default_production_id': self.id,
            },
        }
    
    def action_manage_program_files(self):
        """Open a view to manage program files across all work orders"""
        self.ensure_one()
        
        # Get all work orders with program files
        workorders_with_programs = self.workorder_ids.filtered(lambda wo: wo.has_program_files)
        
        if not workorders_with_programs:
            # If no work orders have programs yet, open the first work order's wizard
            if self.workorder_ids:
                return self.workorder_ids[0].action_upload_program_files()
            else:
                raise ValidationError(_("No work orders found for this Manufacturing Order."))
        
        # Open a tree view of work orders to select which one to manage
        return {
            'name': _('Manage Program Files'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.workorder',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.workorder_ids.ids)],
            'context': {
                'default_production_id': self.id,
            },
        }

    def action_generate_calibration_swatch(self):
        """
        Generate a calibration swatch product and MO.
        Excludes components (swatch starts empty) and creates a BOM request in Swatch category.
        Sets rel_service = Swatch Service. Picks colorway from linked Dev MO if available.
        """
        self.ensure_one()
        swatch_name = f"{self.product_id.name} - Calibration Swatch"
        logging.info(f" Custom Code: Swatch name: {swatch_name}")
        swatch_category = self.env["product.category"].search([("name", "=", "Swatch")], limit=1)
        
        if not swatch_category:
            swatch_category = self.env["product.category"].create({"name": "Swatch"})
        logging.info(f" Custom Code: Swatch category: {swatch_category}")

        # Always set rel_service to Swatch Service (rel_service is product.product)
        swatch_service = self.env['product.product'].search(
            [('name', '=', 'Swatch Service'), ('type', '=', 'service')], limit=1)

        # Colorway: prefer Dev MO's colorway (for Toile MOs that may not have one set)
        dev_mo = getattr(self, 'dev_mo_id', False)
        colorway_id = (self.colorway_id.id if self.colorway_id
                       else (dev_mo.colorway_id.id if dev_mo and dev_mo.colorway_id else False))

        logging.info('self. partner id: %s', self.partner_id)
        try:
            swatch_product_tmpl = self.env["product.template"].create({
                "name": swatch_name,
                "type": "consu",
                "categ_id": swatch_category.id,
                "product_category": "swatch",
                "brand_id": self.partner_id.id
            })
        except Exception as e:
            logging.info('Error creating swatch product template: %s', e)
        logging.info(f" Custom Code: Swatch product template created: {swatch_product_tmpl}")
        swatch_product = swatch_product_tmpl.product_variant_id
    
        swatch_bom = self.env['mrp.bom'].create({
            'product_tmpl_id': swatch_product_tmpl.id,
            'product_id': swatch_product.id,
            'product_qty': 1.0,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'is_swatch_bom': True,
            'rel_service': swatch_service.id if swatch_service else self.rel_service.id,
        })
        logging.info(f" Custom Code: Created swatch BOM: {swatch_bom.id}")
        
        new_mo = self.env["mrp.production"].create({
            "product_id": swatch_product.id,
            "product_qty": 1,
            "product_uom_id": self.product_uom_id.id,
            "company_id": self.company_id.id,
            "bom_id": swatch_bom.id,
            "partner_id": self.partner_id.id,
            "rel_service": swatch_service.id if swatch_service else (self.rel_service.id if self.rel_service else False),
            "colorway_id": colorway_id,
            "yarn_variant": self.yarn_variant.id if self.yarn_variant else False,
            "gauge_id": self.gauge_id.id if self.gauge_id else False,
            "whole_cad_data": self.whole_cad_data,
            "measurement_widget_data": self.measurement_widget_data,
            "calibration_data": self.calibration_data,
            "style_3d_link": self.style_3d_link,
            "artwork_data_standalone": self.artwork_data,
            "excalidraw_data_standalone": self.excalidraw_data,
            "garment_construction_data_standalone": self.garment_construction_data,
            "structure_cad_data": self.structure_cad_data,
            "parent_garment_mo_id": self.id,
        })
        logging.info(f" Custom Code: New MO created: {new_mo}")
        
        bom_request_vals = {
            'product_tmpl_id': swatch_product_tmpl.id,
            'partner_id': self.partner_id.id,
            'product_id': swatch_product.id,
            'state': 'done',
            'rel_service': swatch_service.id if swatch_service else self.rel_service.id,
            'mo_id': new_mo.id,
            'bom_id': swatch_bom.id,
        }
        
        # Copy calibration data to BOM request if available
        if self.calibration_data:
            bom_request_vals['calibration_data'] = self.calibration_data
        
        bom_request = self.env['maeknit.bom.request'].create(bom_request_vals)
        logging.info(f" Custom Code: Created BOM request {bom_request.name} for calibration swatch, is_swatch_bom={bom_request.is_swatch_bom}")
        
        # Link BOM request to MO
        new_mo.write({'bom_request_id': bom_request.id})

        # Copy structure lines (suppress panel CAD sync — measurement_widget_data already copied)
        for sl in self.structure_ids:
            self.env['maeknit.structure.line'].with_context(skip_bom_request_cad_sync=True).create({
                'production_id': new_mo.id,
                'name': sl.name,
                'description': sl.description,
                'sequence': sl.sequence,
            })
        logging.info(f" Custom Code: Copied {len(self.structure_ids)} structure lines to {new_mo.name}")

        # Copy render images from parent MO
        for img in self.render_image_ids:
            self.env['render.image.line'].create({
                'production_id': new_mo.id,
                'name': img.name,
                'image': img.image,
                'image_filename': img.image_filename,
                'sequence': img.sequence,
            })
        logging.info(f" Custom Code: Copied {len(self.render_image_ids)} render images to {new_mo.name}")
        
        # Components intentionally not copied — swatch starts empty and syncs from the MO
        logging.info(f" Custom Code: Swatch MO components left empty (will sync from parent)")


        # Find swatch template from BOM Operation Templates (same company, service type = swatch)
        swatch_template = self.env['maeknit.bom.operation.template'].search([
            ('related_service', '=', 'swatch'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        logging.info(f" Custom Code: Swatch template found: {swatch_template.name if swatch_template else 'None'}")

        Workorder = self.env['mrp.workorder']
        if swatch_template:
            for line in swatch_template.line_ids:
                shop_op = line.operation_id
                new_vals = {
                    'production_id': new_mo.id,
                    'name': shop_op.name,
                    'product_id': new_mo.product_id.id,
                    'product_uom_id': new_mo.product_uom_id.id,
                    'company_id': new_mo.company_id.id,
                    'sequence': line.sequence,
                    'state': 'waiting',
                }
                if shop_op:
                    new_vals['shopfloor_operation_id'] = shop_op.id
                if line.user_ids:
                    new_vals['employee_assigned_ids'] = [(6, 0, line.user_ids.ids)]
                new_wo = Workorder.create(new_vals)
                logging.info(f" Custom Code: Created workorder from swatch template: {new_wo.name}")
        else:
            logging.info(f" Custom Code: No swatch template found, skipping workorder creation")

        # Force colorway / yarn_variant / gauge after all ORM computes have settled
        forced_vals = {}
        if colorway_id:
            forced_vals['colorway_id'] = colorway_id
        if self.yarn_variant:
            forced_vals['yarn_variant'] = self.yarn_variant.id
        if self.gauge_id:
            forced_vals['gauge_id'] = self.gauge_id.id
        if forced_vals:
            new_mo.write(forced_vals)
            logging.info(f" Custom Code: Forced colorway/yarn_variant/gauge on {new_mo.name}: {forced_vals}")

        calibration_data = self.calibration_data.copy() if isinstance(self.calibration_data, dict) else {}
        calibration_data.update({
            "calibrationSwatchId": swatch_product.id,
            "calibrationSwatchName": swatch_name,
            "hasPreExistingSwatch": True,
        })
        self.write({'calibration_data': calibration_data})
        logging.info(f" Custom Code: Calibration data updated: {self.calibration_data}")

        action = {
            'type': 'ir.actions.act_window',
            'name': _('Calibration Swatch MO'),
            'res_model': 'mrp.production',
            'res_id': new_mo.id,
            'view_mode': 'form',
            'target': 'current',
            'views': [(False, 'form')], 
        }
        
        return action

    def action_bump_whole_cad_version(self):
        bom_requests = self.env['maeknit.bom.request'].search([
                ('mo_id', '=', self.id)
            ])
            
        for bom_request in bom_requests:
            # Increment the Whole CAD version
            bom_request.increment_whole_cad_version()
            bom_request.action_ready_to_spec()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def button_mark_done(self):
        """Override to show stitch density wizard for calibration swatch MOs when using Produce All"""
        for production in self:
            if production.product_category == 'swatch' and production.parent_garment_mo_id and not self.env.context.get('skip_stitch_density_wizard'):
                # This is a calibration swatch MO, show stitch density wizard
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Enter Calibration Measurements'),
                    'res_model': 'stitch.density.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_calibration_mo_id': production.id,
                        'default_parent_garment_mo_id': production.parent_garment_mo_id.id,
                    },
                }
        
        # Call the original method first
        res = super(MrpProduction, self).button_mark_done()
        
        # Find related BOM requests and increment their Whole CAD versions
       
        for production in self:
            # Find BOM requests linked to this MO
            bom_requests = self.env['maeknit.bom.request'].search([
                ('mo_id', '=', production.id)
            ])

            
            for bom_request in bom_requests:
                bom_request.action_ready_to_ship()
        return res
    
    @api.depends('product_id', 'product_tmpl_id')
    def _compute_style_colorway_ids(self):
        """Compute available colorways for the product from style.colorway table - matches BOM Request logic"""
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

    @api.depends('product_id', 'product_tmpl_id')
    def _compute_style_size_ids(self):
        """Compute available sizes for the product from style.size table"""
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

    @api.depends('product_id', 'product_tmpl_id')
    def _compute_style_yarn_variant_ids(self):
        """Compute available yarn variants for the product from style.yarn.variant table"""
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

    @api.depends('company_id')
    def _compute_is_uk_company(self):
        for record in self:
            company = record.company_id
            record.is_uk_company = bool(company and 'uk' in (company.name or '').lower())

    @api.model
    def get_calibration_swatches_for_client(self, partner_id):
        """
        Get all swatch MOs for a client brand — both calibration swatches and normal
        swatches — regardless of whether the MO is linked to the parent brand or an
        individual contact under that brand.
        Returns MO IDs (not product IDs) so calibration data can be read directly.
        """
        if not partner_id:
            return []

        # Resolve to the commercial root (the brand), collect the full hierarchy.
        partner = self.env['res.partner'].browse(partner_id)
        commercial = partner.commercial_partner_id or partner
        all_partner_ids = self.env['res.partner'].search([
            ('commercial_partner_id', '=', commercial.id)
        ]).ids
        if commercial.id not in all_partner_ids:
            all_partner_ids.append(commercial.id)

        # Search all swatch MOs for this brand hierarchy (calibration + normal)
        swatch_mos = self.env['mrp.production'].search([
            ('product_id.product_tmpl_id.product_category', '=', 'swatch'),
            ('partner_id', 'in', all_partner_ids),
        ], order='name asc')

        result = []
        for mo in swatch_mos:
            product_name = mo.product_id.name or mo.name or ''
            attributes = []
            if mo.yarn_variant:
                attributes.append(f"Yarn: {mo.yarn_variant.name}")
            if mo.colorway_id:
                attributes.append(f"Colorway: {mo.colorway_id.name}")
            if attributes:
                product_name = f"{product_name} ({', '.join(attributes)})"
            result.append({
                'id': mo.id,
                'productName': product_name,
                'moRef': mo.name or '',
            })

        return result

    @api.model
    def get_calibration_data_for_swatch(self, swatch_mo_id):
        """
        Get the calibration data for a swatch MO (both calibration swatches and normal swatches).
        Reads directly from the MO record and resolves attachment IDs to /web/content/ URLs
        so the stitch density panel widget can display images inline.
        """
        if not swatch_mo_id:
            return {}

        mo = self.env['mrp.production'].browse(swatch_mo_id)
        if not mo.exists():
            logging.info(f" Custom Code: No MO found for swatch MO ID: {swatch_mo_id}")
            return {}

        raw = mo.calibration_data or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                raw = {}
        data = dict(raw)

        logging.info(
            f" Custom Code [get_calibration_data_for_swatch] MO {swatch_mo_id} ({mo.name}): "
            f"raw keys={list(data.keys())}, "
            f"widthAttId={data.get('widthImageAttachmentId')!r}, "
            f"heightAttId={data.get('heightImageAttachmentId')!r}"
        )

        # Resolve attachment IDs → image URLs so the widget can render them inline
        image_fields = [
            ('widthImageAttachmentId', 'widthImage'),
            ('heightImageAttachmentId', 'heightImage'),
            ('widthImage2AttachmentId', 'widthImage2'),
            ('heightImage2AttachmentId', 'heightImage2'),
        ]
        for id_key, url_key in image_fields:
            att_id = data.get(id_key)
            # Some records store attachment IDs as [id] lists instead of plain ints
            if isinstance(att_id, list):
                att_id = att_id[0] if att_id else None
            if att_id:
                try:
                    attachment = self.env['ir.attachment'].sudo().browse(int(att_id))
                    if attachment.exists() and attachment.datas:
                        mime = attachment.mimetype or 'image/png'
                        b64 = attachment.datas.decode('utf-8') if isinstance(attachment.datas, bytes) else attachment.datas
                        data[url_key] = f"data:{mime};base64,{b64}"
                        logging.info(f" Custom Code [get_calibration_data_for_swatch] MO {swatch_mo_id}: {id_key}={att_id} → image loaded ({mime})")
                    else:
                        logging.warning(f" Custom Code [get_calibration_data_for_swatch] MO {swatch_mo_id}: {id_key}={att_id} → attachment not found or no datas")
                        data[url_key] = None
                except Exception as e:
                    logging.error(f" Custom Code [get_calibration_data_for_swatch] MO {swatch_mo_id}: {id_key}={att_id!r} → error: {e}")
                    data[url_key] = None
            else:
                data[url_key] = None

        logging.info(f" Custom Code [get_calibration_data_for_swatch] MO {swatch_mo_id}: returning data with keys={list(data.keys())}")
        return data

    @api.depends('calibration_data', 'calibration_image_ids')
    def _compute_calibration_data_with_images(self):
        """Return calibration data as-is - widget loads images from attachments"""
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
            
            # The widget will load images from attachments using orm.read()
            record.calibration_data_with_images = data

    def _remove_structure_panel(self, panel_key):
        """Remove a structure-driven panel from measurement_widget_data (called on structure line unlink)."""
        import copy as _copy
        data = _copy.deepcopy(self.measurement_widget_data or {})
        data.pop(panel_key, None)
        data['structurePanels'] = [
            p for p in data.get('structurePanels', []) if p.get('id') != panel_key
        ]
        self.with_context(skip_bom_request_cad_sync=True).write({'measurement_widget_data': data})

    @api.depends('measurement_widget_data', 'bom_request_id')
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

            def _panel_image_url(panel_id, attachment_id):
                if record.bom_request_id:
                    return record.bom_request_id._measurement_panel_image_url(panel_id, attachment_id)
                if attachment_id:
                    return f"/web/content/{attachment_id}?download=false"
                return None

            def _restore_panel_images(panel_key, panel_data):
                """Restore image and image2 URLs from attachment IDs for a panel."""
                att_id = panel_data.get('image_attachment_id')
                panel_data['image'] = _panel_image_url(panel_key, att_id) if att_id else None
                att2_id = panel_data.get('image2_attachment_id')
                panel_data['image2'] = _panel_image_url(panel_key + '_2', att2_id) if att2_id else None

            # Restore image URLs for every panel body in the data (core, custom, structure)
            _meta_keys = {'structurePanels', 'customPanels', 'hiddenPanels', 'unit', 'status'}
            for key, value in data.items():
                if key not in _meta_keys and isinstance(value, dict):
                    _restore_panel_images(key, value)

            record.measurement_widget_data_with_images = data
    
    @api.depends('whole_cad_data', 'bom_request_id')
    def _compute_whole_cad_data_with_images(self):
        """Restore image URL for whole CAD widget display"""
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
            
            # Check if there's an image_attachment_id or if BOM Request has the image
            if data.get('image_attachment_id') or (record.bom_request_id and record.bom_request_id.whole_cad_image_id):
                # Set image URL for widget to fetch
                data['image'] = f"/maeknit/whole_cad/image/{record.id}"
                logging.info(f" Custom Code: Set whole CAD image URL for MRP Production {record.id}")
            else:
                data['image'] = None
            
            record.whole_cad_data_with_images = data

    def _compute_cad_pom_data_with_images(self):
        """Restore image URL for CAD & POM widget display"""
        for record in self:
            if not record.cad_pom_data:
                record.cad_pom_data_with_images = {
                    'max_version': 0, 'measurements': [], 'image': None, 'unit': 'inches'
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

            if data.get('image_attachment_id') or (record.bom_request_id and record.bom_request_id.cad_pom_image_id):
                data['image'] = f"/maeknit/cad_pom/image/{record.id}"
            else:
                data['image'] = None

            record.cad_pom_data_with_images = data