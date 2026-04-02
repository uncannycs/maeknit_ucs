from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import copy
import logging

class BomDuplicateWizard(models.TransientModel):
    """Wizard for duplicating BOM Requests with new colorway/size/yarn variants"""
    _name = 'bom.duplicate.wizard'
    _description = 'BOM Duplicate Wizard'

    source_bom_request_id = fields.Many2one(
        'maeknit.bom.request',
        string='Source BOM Request',
        required=True,
        readonly=True
    )

    source_mo_id = fields.Many2one(
        'mrp.production',
        string='Source Manufacturing Order',
        readonly=True,
        help='When set, always creates a new MO and copies WOs/components from this source MO.'
    )
    
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        related='source_bom_request_id.product_tmpl_id',
        readonly=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='source_bom_request_id.partner_id',
        readonly=True
    )
    
    rel_service = fields.Many2one(
        'product.product',
        string='Related Service',
        related='source_bom_request_id.rel_service',
        readonly=True
    )

    source_mo_rel_service = fields.Many2one(
        'product.product',
        related='source_mo_id.rel_service',
        string='Service (from MO)',
        readonly=True,
    )
    
    # Original values
    original_colorway_id = fields.Many2one(
        'product.attribute.value',
        string='Original Colorway',
        related='source_bom_request_id.colorway_id',
        readonly=True
    )
    
    original_size_id = fields.Many2one(
        'product.attribute.value',
        string='Original Size',
        related='source_bom_request_id.size_id',
        readonly=True
    )
    
    original_yarn_variant = fields.Many2one(
        'product.attribute.value',
        string='Original Yarn Variant',
        related='source_bom_request_id.yarn_variant',
        readonly=True
    )
    
    # BOM type flags
    is_garment_bom = fields.Boolean(
        related='source_bom_request_id.is_garment_bom',
        readonly=True
    )
    
    is_swatch_bom = fields.Boolean(
        related='source_bom_request_id.is_swatch_bom',
        readonly=True
    )
    
    is_development_bom = fields.Boolean(
        related='source_bom_request_id.is_development_bom',
        readonly=True
    )
    
    is_grading_bom = fields.Boolean(
        related='source_bom_request_id.is_grading_bom',
        readonly=True
    )
    
    is_production_bom = fields.Boolean(
        related='source_bom_request_id.is_production_bom',
        readonly=True
    )
    
    # New variant selections
    new_colorway_id = fields.Many2one(
        'product.attribute.value',
        string='New Colorway',
        domain="[('attribute_id.name', '=', 'Colorway')]",
        help='Select a new colorway for the duplicated BOM'
    )
    
    new_size_id = fields.Many2one(
        'product.attribute.value',
        string='New Size',
        domain="[('attribute_id.name', '=', 'Size')]",
        help='Select a new size for the duplicated BOM'
    )
    
    new_yarn_variant = fields.Many2one(
        'product.attribute.value',
        string='New Yarn Variant',
        domain="[('attribute_id.name', '=', 'Yarn Variant')]",
        help='Select a new yarn variant for the duplicated BOM'
    )
    
    # Available values computed from product template
    available_colorway_ids = fields.Many2many(
        'product.attribute.value',
        compute='_compute_available_colorways',
        string='Available Colorways'
    )
    
    available_size_ids = fields.Many2many(
        'product.attribute.value',
        compute='_compute_available_sizes',
        string='Available Sizes'
    )
    
    available_yarn_variant_ids = fields.Many2many(
        'product.attribute.value',
        compute='_compute_available_yarn_variants',
        string='Available Yarn Variants'
    )
    
    @api.depends('product_tmpl_id')
    def _compute_available_colorways(self):
        """Compute available colorways from style.colorway table"""
        for wizard in self:
            if wizard.product_tmpl_id:
                style_colorways = self.env['style.colorway'].search([
                    ('product_tmpl_id', '=', wizard.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                colorway_ids = style_colorways.mapped('colorway_id')
                wizard.available_colorway_ids = colorway_ids
            else:
                wizard.available_colorway_ids = [(6, 0, [])]
    
    @api.depends('product_tmpl_id')
    def _compute_available_sizes(self):
        """Compute available sizes from product.template.attribute.line"""
        for wizard in self:
            if wizard.product_tmpl_id:
                size_attr = self.env['product.attribute'].search([('name', '=', 'Size')], limit=1)
                if size_attr:
                    attr_lines = self.env['product.template.attribute.line'].search([
                        ('product_tmpl_id', '=', wizard.product_tmpl_id.id),
                        ('attribute_id', '=', size_attr.id)
                    ])
                    size_ids = attr_lines.mapped('value_ids')
                    wizard.available_size_ids = size_ids
                else:
                    wizard.available_size_ids = [(6, 0, [])]
            else:
                wizard.available_size_ids = [(6, 0, [])]
    
    @api.depends('product_tmpl_id')
    def _compute_available_yarn_variants(self):
        """Compute available yarn variants from style.yarn.variant table"""
        for wizard in self:
            if wizard.product_tmpl_id:
                style_yarns = self.env['style.yarn.variant'].search([
                    ('product_tmpl_id', '=', wizard.product_tmpl_id.id),
                    ('active', '=', True)
                ])
                yarn_ids = style_yarns.mapped('yarn_variant_id')
                wizard.available_yarn_variant_ids = yarn_ids
            else:
                wizard.available_yarn_variant_ids = [(6, 0, [])]
    
    @api.onchange('new_yarn_variant')
    def _onchange_new_yarn_variant(self):
        """When a new yarn variant is created on-the-go, ensure it's added to style.yarn.variant"""
        if self.new_yarn_variant and self.product_tmpl_id:
            # Ensure the yarn variant is linked to the style
            self.env['style.yarn.variant'].get_or_create(
                self.product_tmpl_id.id,
                self.new_yarn_variant.id
            )
            # Recompute available yarn variants to include the newly created one
            self._compute_available_yarn_variants()
    
    @api.model
    def default_get(self, fields_list):
        """Pre-populate wizard fields from context"""
        res = super().default_get(fields_list)
        
        bom_request_id = self.env.context.get('default_source_bom_request_id') or self.env.context.get('active_id')
        if bom_request_id:
            bom_request = self.env['maeknit.bom.request'].browse(bom_request_id)
            res['source_bom_request_id'] = bom_request.id

        source_mo_id = self.env.context.get('default_source_mo_id')
        if source_mo_id:
            res['source_mo_id'] = source_mo_id

        return res
    
    def action_duplicate(self):
        """Duplicate the BOM Request with new variant values"""
        self.ensure_one()
        
        source_bom_req = self.source_bom_request_id
        
        # Validate that at least one new value is provided
        if self.is_garment_bom or self.is_development_bom or self.is_grading_bom or self.is_production_bom:
            if not self.new_colorway_id and not self.new_size_id:
                raise ValidationError(_(
                    "Please select at least a new colorway or size for the duplicated BOM."
                ))
        
        if self.is_swatch_bom:
            if not self.new_colorway_id and not self.new_yarn_variant:
                raise ValidationError(_(
                    "Please select at least a new colorway or yarn variant for the duplicated swatch BOM."
                ))
            
            # Determine final colorway and yarn_variant
            final_colorway = self.new_colorway_id if self.new_colorway_id else source_bom_req.colorway_id
            final_yarn_variant = self.new_yarn_variant if self.new_yarn_variant else source_bom_req.yarn_variant
            
            # Check if they're the same as original
            if (final_colorway == source_bom_req.colorway_id and 
                final_yarn_variant == source_bom_req.yarn_variant):
                raise ValidationError(_(
                    "The selected variant values are the same as the original BOM. "
                    "Please select different colorway or yarn variant values."
                ))
        
        logging.info(f" Custom Code: Duplicating BOM Request {source_bom_req.name} with new variants")
        
        # Create new BOM with new variant values
        new_bom = self._create_new_bom(source_bom_req)
        
        # Create new BOM Request linked to the new BOM
        new_bom_request = self._create_new_bom_request(source_bom_req, new_bom)
        
        logging.info(f" Custom Code: Created duplicate BOM Request: {new_bom_request.name}")
        
        # Always create MO when invoked from an MO context
        should_create_mo = bool(self.source_mo_id) or self.env.context.get('duplicate_to_mfg')
        if not should_create_mo:
            source_so = source_bom_req.sale_order_id
            should_create_mo = bool(source_so and source_so.direct_mo_mode)

        if should_create_mo:
            logging.info(
                " Custom Code: Launching action_generate_mo after duplicating BOM Request %s",
                new_bom_request.name,
            )
            new_bom_request.with_context(skip_component_validation=True).action_generate_mo()
            if new_bom_request.mo_id:
                new_mo = new_bom_request.mo_id
                if self.source_mo_id:
                    self._copy_workorders_and_components(self.source_mo_id, new_mo)
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Manufacturing Order'),
                    'res_model': 'mrp.production',
                    'res_id': new_mo.id,
                    'view_mode': 'form',
                    'target': 'current',
                }

        # Return action to open the newly created BOM Request
        return {
            'type': 'ir.actions.act_window',
            'name': _('Duplicated BOM Request'),
            'res_model': 'maeknit.bom.request',
            'res_id': new_bom_request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _copy_workorders_and_components(self, source_mo, new_mo):
        """Copy work orders and components from source_mo to new_mo."""
        logging.info(
            " Custom Code: Copying WOs and components from MO %s to new MO %s",
            source_mo.name, new_mo.name,
        )

        # --- Copy Work Orders ---
        # Remove auto-generated WOs on the new MO (draft state only)
        existing_wos = new_mo.workorder_ids.filtered(lambda wo: wo.state not in ('done', 'cancel'))
        existing_wos.unlink()

        for src_wo in source_mo.workorder_ids.filtered(lambda wo: wo.state not in ('cancel',)):
            # Resolve name: shopfloor op name takes priority, then stored name, then fallback
            wo_name = (
                src_wo.shopfloor_operation_id.name
                if src_wo.shopfloor_operation_id
                else (src_wo.name or _('New'))
            )
            wo_vals = {
                'name': wo_name,
                'production_id': new_mo.id,
                'product_uom_id': src_wo.product_uom_id.id if src_wo.product_uom_id else new_mo.product_uom_id.id,
                'workcenter_id': src_wo.workcenter_id.id if src_wo.workcenter_id else False,
                'duration_expected': src_wo.duration_expected,
                'sequence': src_wo.sequence,
                'shopfloor_operation_id': src_wo.shopfloor_operation_id.id if src_wo.shopfloor_operation_id else False,
                'text_instruction_notes': src_wo.text_instruction_notes,
                'text_program_notes': src_wo.text_program_notes,
            }
            new_wo = self.env['mrp.workorder'].create(wo_vals)
            logging.info(" Custom Code: Created WO '%s' on new MO %s", new_wo.name, new_mo.name)

            # Copy program and instruction file attachments for this WO
            src_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'mrp.workorder'),
                ('res_id', '=', src_wo.id),
            ])
            for att in src_attachments:
                att_vals = {
                    'name': att.name,
                    'datas': att.datas,
                    'mimetype': att.mimetype,
                    'res_model': 'mrp.workorder',
                    'res_id': new_wo.id,
                }
                if hasattr(att, 'attachment_type') and att.attachment_type:
                    att_vals['attachment_type'] = att.attachment_type
                self.env['ir.attachment'].create(att_vals)

        # --- Copy Structure Lines ---
        # Remove any existing structure lines on the new MO, then recreate from source
        new_mo.structure_ids.unlink()

        structure_id_map = {}  # {old_structure_line_id: new_structure_line_id}
        for src_struct in source_mo.structure_ids:
            new_struct = self.env['maeknit.structure.line'].create({
                'name': src_struct.name,
                'description': src_struct.description,
                'sequence': src_struct.sequence,
                'production_id': new_mo.id,
                'bom_request_id': new_mo.bom_request_id.id if new_mo.bom_request_id else False,
            })
            structure_id_map[src_struct.id] = new_struct.id
            logging.info(" Custom Code: Created Structure Line '%s' on new MO %s", new_struct.name, new_mo.name)

        # --- Copy Structure CAD (measurement_widget_data) ---
        # _sync_to_panel_cad('add') already created empty panel shells for the new structure lines.
        # Now overwrite the new MO's widget data with the actual measurement values from the source,
        # remapping all panel keys (s_<old_id> → s_<new_id>) via structure_id_map.
        src_cad = source_mo.measurement_widget_data
        if src_cad and structure_id_map:
            new_cad = {}
            for key, value in src_cad.items():
                if key.startswith('s_'):
                    try:
                        old_id = int(key[2:])
                        new_id = structure_id_map.get(old_id)
                        if new_id:
                            new_cad[f's_{new_id}'] = copy.deepcopy(value)
                            if isinstance(new_cad[f's_{new_id}'], dict):
                                new_cad[f's_{new_id}']['name'] = value.get('name', '')
                    except (ValueError, TypeError):
                        pass
                elif key == 'structurePanels':
                    remapped_panels = []
                    for panel in (value or []):
                        old_panel_id = panel.get('id', '')
                        if old_panel_id.startswith('s_'):
                            try:
                                old_id = int(old_panel_id[2:])
                                new_id = structure_id_map.get(old_id)
                                if new_id:
                                    remapped_panels.append({'id': f's_{new_id}', 'name': panel.get('name', '')})
                            except (ValueError, TypeError):
                                pass
                        else:
                            remapped_panels.append(copy.deepcopy(panel))
                    new_cad['structurePanels'] = remapped_panels
                else:
                    new_cad[key] = copy.deepcopy(value)
            new_mo.with_context(skip_bom_request_cad_sync=True).write({'measurement_widget_data': new_cad})
            logging.info(" Custom Code: Copied measurement_widget_data to new MO %s", new_mo.name)

        # --- Copy Components (move_raw_ids) ---
        # Write directly to 'draft' to avoid _action_cancel() cascading and cancelling the MO
        new_mo.move_raw_ids.write({'state': 'draft'})
        new_mo.move_raw_ids.unlink()

        # Include done moves too — source MO may be completed; we copy product/qty, not state
        src_components = source_mo.move_raw_ids.filtered(lambda m: m.state != 'cancel')
        for src_move in src_components:
            move_vals = {
                'name': src_move.name,
                'product_id': src_move.product_id.id,
                'product_uom_qty': src_move.product_uom_qty,
                'product_uom': src_move.product_uom.id,
                'location_id': src_move.location_id.id,
                'location_dest_id': src_move.location_dest_id.id,
                'raw_material_production_id': new_mo.id,
                'company_id': new_mo.company_id.id,
                'warehouse_id': src_move.warehouse_id.id if src_move.warehouse_id else False,
                'origin': new_mo.name,
            }
            if hasattr(src_move, 'x_ply') and src_move.x_ply:
                move_vals['x_ply'] = src_move.x_ply
            if hasattr(src_move, 'left_carrier') and src_move.left_carrier:
                move_vals['left_carrier'] = src_move.left_carrier
            if hasattr(src_move, 'right_carrier') and src_move.right_carrier:
                move_vals['right_carrier'] = src_move.right_carrier
            if hasattr(src_move, 'structure_id') and src_move.structure_id:
                new_struct_id = structure_id_map.get(src_move.structure_id.id)
                if new_struct_id:
                    move_vals['structure_id'] = new_struct_id
            self.env['stock.move'].create(move_vals)

        # Reset MO to draft AND re-assert variant fields in one write.
        # action_generate_mo() may not set rel_service/yarn_variant, and writing state
        # can trigger recomputes that clear them — so we set them explicitly here.
        new_bom = new_mo.bom_id
        new_bom_req = new_mo.bom_request_id

        # rel_service: the new BOM was created before the BOM Request, so its rel_service
        # may be False. Read from the new BOM Request (populated by BOM handling logic),
        # then fall back to the source MO.
        rel_service = (
            source_mo.rel_service
            or new_bom_req.rel_service
            or (new_bom.rel_service if new_bom else False)
        )

        draft_vals = {'state': 'draft'}
        if rel_service:
            draft_vals['rel_service'] = rel_service.id
        if new_bom:
            if new_bom.colorway_id:
                draft_vals['colorway_id'] = new_bom.colorway_id.id
            if hasattr(new_bom, 'yarn_variant') and new_bom.yarn_variant:
                draft_vals['yarn_variant'] = new_bom.yarn_variant.id
            if hasattr(new_bom, 'size_id') and new_bom.size_id:
                draft_vals['size_id'] = new_bom.size_id.id
            if hasattr(new_bom, 'gauge_id') and new_bom.gauge_id:
                draft_vals['gauge_id'] = new_bom.gauge_id.id
        new_mo.write(draft_vals)

        logging.info(
            " Custom Code: Finished copying %d WOs and %d components to MO %s (state=draft, fields=%s)",
            len(source_mo.workorder_ids.filtered(lambda wo: wo.state != 'cancel')),
            len(src_components),
            new_mo.name,
            list(draft_vals.keys()),
        )
    
    def _create_new_bom(self, source_bom_req):
        """Create a new mrp.bom with new variant values"""
        source_bom = source_bom_req.bom_id
        
        if not source_bom:
            raise ValidationError(_("Source BOM Request must have a linked BOM."))
        
        # Determine new variant values (use new if provided, else keep original)
        new_colorway_id = self.new_colorway_id.id if self.new_colorway_id else source_bom_req.colorway_id.id
        new_size_id = self.new_size_id.id if self.new_size_id else source_bom_req.size_id.id if source_bom_req.size_id else False
        new_yarn_variant = self.new_yarn_variant.id if self.new_yarn_variant else (source_bom_req.yarn_variant.id if source_bom_req.yarn_variant else False)
        logging.info(f" Custom Code: Creating new BOM with Colorway ID: {new_colorway_id}, Size ID: {new_size_id}, Yarn Variant ID: {new_yarn_variant}")
        # Check if a BOM with these exact variants already exists
        if self.is_swatch_bom:
            # For Swatch BOMs, search based on colorway and yarn_variant (yarn_variant can be False)
            logging.info(" Custom Code:Searching for existing Swatch BOM with specified variants")
            if new_yarn_variant:
                existing_bom = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', self.product_tmpl_id.id),
                    ('colorway_id', '=', new_colorway_id),
                    ('yarn_variant', '=', new_yarn_variant),
                    ('rel_service', '=', self.rel_service.id),
                    ('gauge_id', '=', source_bom_req.gauge_id.id if source_bom_req.gauge_id else False),
                ], limit=1)
                logging.info(f" Custom Code: Existing BOM search with yarn variant returned: {existing_bom}")
            else:
                # No yarn variant specified, search without it
                logging.info(" Custom Code:No yarn variant specified, searching without it")
                existing_bom = self.env['mrp.bom'].search([
                    ('product_tmpl_id', '=', self.product_tmpl_id.id),
                    ('colorway_id', '=', new_colorway_id),
                    ('yarn_variant', '=', False),
                    ('rel_service', '=', self.rel_service.id),
                    ('gauge_id', '=', source_bom_req.gauge_id.id if source_bom_req.gauge_id else False),
                ], limit=1)
                logging.info(f" Custom Code: Existing BOM search without yarn variant returned: {existing_bom}")
        else:
            # For Garment/other BOMs, use the original search
            logging.info(" Custom Code:Searching for existing BOM with specified variants")
            existing_bom = self.env['mrp.bom'].search([
                ('product_tmpl_id', '=', self.product_tmpl_id.id),
                ('colorway_id', '=', new_colorway_id),
                ('size_id', '=', new_size_id),
                ('rel_service', '=', self.rel_service.id),
                ('gauge_id', '=', source_bom_req.gauge_id.id if source_bom_req.gauge_id else False),
            ], limit=1)
        
        if existing_bom:
            logging.info(" Custom Code:Duplicate BOM found, raising ValidationError %s" % existing_bom)
            raise ValidationError(_(
                "Duplicate Ssswatch BOM exists.\n"
                "Product: %s\n"
                "Colorway: %s\n"
                "Yarn Variant: %s\n"
                "Service: %s\n"
                "ID: %s"
            ) % (
                self.product_tmpl_id.name,
                self.env['product.attribute.value'].browse(new_colorway_id).name,
                self.env['product.attribute.value'].browse(new_yarn_variant).name if new_yarn_variant else "False",
                self.rel_service.name,
                existing_bom.id
            ))
        
        # Create new BOM with new variant values
        new_bom_vals = {
            'product_tmpl_id': self.product_tmpl_id.id,
            'product_qty': source_bom.product_qty,
            'product_uom_id': source_bom.product_uom_id.id,
            'type': source_bom.type,
            'rel_service': self.rel_service.id,
            'colorway_id': new_colorway_id,
            'size_id': new_size_id,
            'gauge_id': source_bom_req.gauge_id.id if source_bom_req.gauge_id else False,
            'company_id': source_bom.company_id.id,
            'partner_id': self.partner_id.id,
        }
        
        if self.is_swatch_bom:
            new_bom_vals['yarn_variant'] = new_yarn_variant if new_yarn_variant else False
        
        new_bom = self.env['mrp.bom'].create(new_bom_vals)
        
        # Copy BOM lines from source
        for line in source_bom.bom_line_ids:
            self.env['mrp.bom.line'].create({
                'bom_id': new_bom.id,
                'product_id': line.product_id.id,
                'product_qty': line.product_qty,
                'product_uom_id': line.product_uom_id.id,
                'sequence': line.sequence,
                'x_ply': line.x_ply if hasattr(line, 'x_ply') else False,
                'left_carrier': line.left_carrier if hasattr(line, 'left_carrier') else False,
                'right_carrier': line.right_carrier if hasattr(line, 'right_carrier') else False,
            })
        
        # Copy subcontractors if present
        if hasattr(source_bom, 'subcontractor_ids') and source_bom.subcontractor_ids:
            new_bom.subcontractor_ids = [(6, 0, source_bom.subcontractor_ids.ids)]
        
        # Ensure colorway is linked to style.colorway
        if new_colorway_id:
            self.env['style.colorway'].get_or_create_style_colorway(
                self.product_tmpl_id.id,
                new_colorway_id
            )

        # Ensure size is linked to style.size
        if new_size_id:
            self.env['style.size'].get_or_create_style_size(
                self.product_tmpl_id.id,
                new_size_id
            )

        if self.is_swatch_bom and new_yarn_variant:
            self.env['style.yarn.variant'].get_or_create(
                self.product_tmpl_id.id,
                new_yarn_variant
            )
        
        logging.info(f" Custom Code: Created new BOM: {new_bom.display_name}")
        return new_bom
    
    def _create_new_bom_request(self, source_bom_req, new_bom):
        """Create new BOM Request linked to the new BOM"""

        # Generate new name with version suffix
        new_name = source_bom_req._next_version_name(source_bom_req.name)

        # Determine new variant values
        new_colorway_id = self.new_colorway_id.id if self.new_colorway_id else source_bom_req.colorway_id.id if source_bom_req.colorway_id else False
        new_size_id = self.new_size_id.id if self.new_size_id else source_bom_req.size_id.id if source_bom_req.size_id else False
        new_yarn_variant = self.new_yarn_variant.id if self.new_yarn_variant else (source_bom_req.yarn_variant.id if source_bom_req.yarn_variant else False)

        # Create new BOM Request
        new_bom_req_vals = {
            'name': new_name,
            'partner_id': source_bom_req.partner_id.id,
            'product_tmpl_id': self.product_tmpl_id.id,
            'bom_id': new_bom.id,
            'rel_service': self.rel_service.id,
            'gauge_id': source_bom_req.gauge_id.id if source_bom_req.gauge_id else False,
            'type': source_bom_req.type,
            'colorway_id': new_colorway_id,
            'size_id': new_size_id,
            'mo_id': False,
            'state': 'draft',
            'sale_order_id': source_bom_req.sale_order_id.id if source_bom_req.sale_order_id else False,
            'operation_template_id': source_bom_req.operation_template_id.id if source_bom_req.operation_template_id else False,
            'rnd_task_template_id': source_bom_req.rnd_task_template_id.id if source_bom_req.rnd_task_template_id else False,
            'notes': source_bom_req.notes,
            'is_development_bom': source_bom_req.is_development_bom,
            'is_garment_bom': source_bom_req.is_garment_bom,
            'is_swatch_bom': source_bom_req.is_swatch_bom,
            'is_grading_bom': source_bom_req.is_grading_bom,
            'is_production_bom': source_bom_req.is_production_bom,
            # ── Tab data copied verbatim (variant-independent) ──
            'structure_cad_data': source_bom_req.structure_cad_data,
            'artwork_data': source_bom_req.artwork_data,
            'excalidraw_link': source_bom_req.excalidraw_link,
            'style_3d_link': source_bom_req.style_3d_link,
            'excalidraw_data': source_bom_req.excalidraw_data,
            'garment_construction_data': source_bom_req.garment_construction_data,
            'machine_file': source_bom_req.machine_file,
            'machine_filename': source_bom_req.machine_filename,
            'expected_machine_time': source_bom_req.expected_machine_time,
            'hs_code': source_bom_req.hs_code,
        }

        if self.is_swatch_bom:
            new_bom_req_vals['yarn_variant'] = new_yarn_variant if new_yarn_variant else False

        # Create with skip_bom_request_create_logic to prevent auto-creation of new BOM
        new_bom_req = self.env['maeknit.bom.request'].with_context(
            skip_bom_request_create_logic=True
        ).create(new_bom_req_vals)

        # Copy component lines from source
        for line in source_bom_req.bom_line_ids:
            self.env['maeknit.bom.request.line'].create({
                'bom_request_id': new_bom_req.id,
                'product_id': line.product_id.id,
                'product_qty': line.product_qty,
                'product_uom_id': line.product_uom_id.id,
                'sequence': line.sequence,
                'ply': line.ply,
                'left_carrier': line.left_carrier,
                'right_carrier': line.right_carrier,
                'carrier': line.carrier if hasattr(line, 'carrier') else False,
            })

        # Copy structure lines — build structure_id_map for measurement_widget_data remapping
        structure_id_map = {}  # {old_structure_line_id: new_structure_line_id}
        for struct in source_bom_req.structure_ids:
            new_struct = self.env['maeknit.structure.line'].create({
                'bom_request_id': new_bom_req.id,
                'name': struct.name,
                'description': struct.description,
                'sequence': struct.sequence,
            })
            structure_id_map[struct.id] = new_struct.id

        # Copy operations from source (including instruction/program file attachments)
        for operation in source_bom_req.operation_ids:
            new_op_vals = {
                'bom_request_id': new_bom_req.id,
                'operation_id': operation.operation_id.id,
                'workcenter_id': operation.workcenter_id.id if operation.workcenter_id else False,
                'time_cycle': operation.time_cycle,
                'sequence': operation.sequence,
                'instruction_text': operation.instruction_text,
                'program_text': operation.program_text,
                'knit_attempt': operation.knit_attempt,
                'program_version': operation.program_version,
            }
            if operation.employee_assigned_ids:
                new_op_vals['employee_assigned_ids'] = [(6, 0, operation.employee_assigned_ids.ids)]
            if operation.program_attachment_ids:
                new_op_vals['program_attachment_ids'] = [(6, 0, operation.program_attachment_ids.ids)]
            if operation.instruction_attachment_ids:
                new_op_vals['instruction_attachment_ids'] = [(6, 0, operation.instruction_attachment_ids.ids)]
            if operation.attachment_ids:
                new_op_vals['attachment_ids'] = [(6, 0, operation.attachment_ids.ids)]
            self.env['maeknit.bom.request.operation'].create(new_op_vals)

        # Copy subcontractors
        if hasattr(source_bom_req, 'subcontractor_ids') and source_bom_req.subcontractor_ids:
            new_bom_req.subcontractor_ids = [(6, 0, source_bom_req.subcontractor_ids.ids)]

        # ── Structure CAD (measurement_widget_data) with panel ID remapping ──
        src_cad = source_bom_req.measurement_widget_data
        if src_cad:
            new_cad = {}
            for key, value in src_cad.items():
                if key.startswith('s_'):
                    try:
                        old_id = int(key[2:])
                        new_id = structure_id_map.get(old_id)
                        if new_id:
                            panel_data = copy.deepcopy(value)
                            panel_data = self._copy_panel_image_attachments(panel_data, new_bom_req)
                            new_cad[f's_{new_id}'] = panel_data
                    except (ValueError, TypeError):
                        pass
                elif key == 'structurePanels':
                    remapped_panels = []
                    for panel in (value or []):
                        old_panel_id = panel.get('id', '')
                        if old_panel_id.startswith('s_'):
                            try:
                                old_id = int(old_panel_id[2:])
                                new_id = structure_id_map.get(old_id)
                                if new_id:
                                    remapped_panels.append({'id': f's_{new_id}', 'name': panel.get('name', '')})
                            except (ValueError, TypeError):
                                pass
                        else:
                            remapped_panels.append(copy.deepcopy(panel))
                    new_cad['structurePanels'] = remapped_panels
                else:
                    # For non-structure panels (custom/core panels), duplicate image attachments
                    if isinstance(value, dict) and ('image_attachment_id' in value or 'image2_attachment_id' in value):
                        panel_data = copy.deepcopy(value)
                        panel_data = self._copy_panel_image_attachments(panel_data, new_bom_req)
                        new_cad[key] = panel_data
                    else:
                        new_cad[key] = copy.deepcopy(value)
            new_bom_req.with_context(skip_bom_request_cad_sync=True).write({'measurement_widget_data': new_cad})
            logging.info(f" Custom Code: Copied measurement_widget_data to new BOM Request {new_bom_req.name}")

        # ── Calibration data with duplicated image attachments ──
        src_calib = source_bom_req.calibration_data
        if src_calib:
            new_calib = copy.deepcopy(src_calib) if isinstance(src_calib, dict) else src_calib
            if isinstance(new_calib, dict):
                new_calib = self._copy_calibration_image_attachments(new_calib, new_bom_req)
            new_bom_req.write({'calibration_data': new_calib})
            logging.info(f" Custom Code: Copied calibration_data to new BOM Request {new_bom_req.name}")

        # ── Whole CAD data with duplicated image attachment ──
        src_whole_cad = source_bom_req.whole_cad_data
        if src_whole_cad:
            new_whole_cad = copy.deepcopy(src_whole_cad) if isinstance(src_whole_cad, dict) else src_whole_cad
            new_whole_cad_image_id = False
            if source_bom_req.whole_cad_image_id:
                new_att = self._duplicate_attachment(source_bom_req.whole_cad_image_id, new_bom_req)
                if new_att:
                    new_whole_cad_image_id = new_att.id
                    if isinstance(new_whole_cad, dict):
                        new_whole_cad['image_attachment_id'] = new_att.id
            new_bom_req.write({'whole_cad_data': new_whole_cad, 'whole_cad_image_id': new_whole_cad_image_id or False})
            logging.info(f" Custom Code: Copied whole_cad_data to new BOM Request {new_bom_req.name}")

        # ── CAD & POM data with duplicated image attachment ──
        src_cad_pom = source_bom_req.cad_pom_data
        if src_cad_pom:
            new_cad_pom = copy.deepcopy(src_cad_pom) if isinstance(src_cad_pom, dict) else src_cad_pom
            new_cad_pom_image_id = False
            if source_bom_req.cad_pom_image_id:
                new_att = self._duplicate_attachment(source_bom_req.cad_pom_image_id, new_bom_req)
                if new_att:
                    new_cad_pom_image_id = new_att.id
                    if isinstance(new_cad_pom, dict):
                        new_cad_pom['image_attachment_id'] = new_att.id
            new_bom_req.write({'cad_pom_data': new_cad_pom, 'cad_pom_image_id': new_cad_pom_image_id or False})
            logging.info(f" Custom Code: Copied cad_pom_data to new BOM Request {new_bom_req.name}")

        # ── Sketch (Excalidraw) file attachments — share via Many2many ──
        if source_bom_req.excalidraw_file_ids:
            new_bom_req.write({'excalidraw_file_ids': [(6, 0, source_bom_req.excalidraw_file_ids.ids)]})
            logging.info(f" Custom Code: Linked {len(source_bom_req.excalidraw_file_ids)} excalidraw file(s) to {new_bom_req.name}")

        # ── Misc (Garment Construction) file attachments — share via Many2many ──
        if source_bom_req.garment_construction_file_ids:
            new_bom_req.write({'garment_construction_file_ids': [(6, 0, source_bom_req.garment_construction_file_ids.ids)]})
            logging.info(f" Custom Code: Linked {len(source_bom_req.garment_construction_file_ids)} garment construction file(s) to {new_bom_req.name}")

        # ── Render images — copy binary data ──
        for img in source_bom_req.render_image_ids:
            self.env['render.image.line'].create({
                'bom_request_id': new_bom_req.id,
                'name': img.name,
                'image': img.image,
                'image_filename': img.image_filename,
                'sequence': img.sequence,
            })
        if source_bom_req.render_image_ids:
            logging.info(f" Custom Code: Copied {len(source_bom_req.render_image_ids)} render image(s) to {new_bom_req.name}")

        logging.info(f" Custom Code: Created new BOM Request: {new_bom_req.name}")
        return new_bom_req

    def _duplicate_attachment(self, attachment, new_record):
        """Create a copy of an ir.attachment linked to new_record."""
        if not attachment or not attachment.exists():
            return False
        try:
            return self.env['ir.attachment'].create({
                'name': attachment.name,
                'datas': attachment.datas,
                'mimetype': attachment.mimetype,
                'res_model': 'maeknit.bom.request',
                'res_id': new_record.id,
                'res_field': attachment.res_field or False,
            })
        except Exception as e:
            logging.warning(f" Custom Code: Failed to duplicate attachment {attachment.id}: {e}")
            return False

    def _copy_panel_image_attachments(self, panel_data, new_bom_req):
        """Duplicate image attachments referenced in a measurement panel data dict."""
        result = dict(panel_data)
        for att_field in ('image_attachment_id', 'image2_attachment_id'):
            old_att_id = result.get(att_field)
            if old_att_id:
                old_att = self.env['ir.attachment'].browse(old_att_id)
                new_att = self._duplicate_attachment(old_att, new_bom_req)
                result[att_field] = new_att.id if new_att else None
        return result

    def _copy_calibration_image_attachments(self, calib_data, new_bom_req):
        """Duplicate calibration image attachments and update IDs in the data dict."""
        result = dict(calib_data)
        for key in ('widthImageAttachmentId', 'heightImageAttachmentId', 'widthImage2AttachmentId', 'heightImage2AttachmentId'):
            old_att_id = result.get(key)
            if old_att_id:
                old_att = self.env['ir.attachment'].browse(old_att_id)
                new_att = self._duplicate_attachment(old_att, new_bom_req)
                result[key] = new_att.id if new_att else None
        return result

    def action_cancel(self):
        """Close the wizard without doing anything"""
        return {'type': 'ir.actions.act_window_close'}
