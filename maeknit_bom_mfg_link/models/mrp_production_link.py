import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    bom_request_id = fields.Many2one('maeknit.bom.request', string='BOM Request', store=True)
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='bom_request_id.partner_id',
        store=True,
        readonly=False,
    )
    size_id = fields.Many2one('product.attribute.value', string='Size', related='bom_request_id.size_id',
                             domain="[('attribute_id.name', '=', 'Size')]")
    colorway_id = fields.Many2one('product.attribute.value', string='Colorway', related='bom_request_id.colorway_id',
                                 domain="[('attribute_id.name', '=', 'Colorway')]")
    machine_id_selection = fields.Selection(
        related='bom_request_id.machine_id_selection',
        default=lambda self: 'shima' if 'uk' in (self.env.company.name or '').lower() else 'stoll',
        string='Machine',
        store=True,
        readonly=False,
    )
    gauge_id = fields.Many2one(
        'gauge.library',
        string='Gauge',
        related='bom_request_id.gauge_id',
        store=True,
        readonly=False,
    )
    
    is_uk_company = fields.Boolean(
        compute='_compute_is_uk_company',
        store=False,
    )

    sample = fields.Char(
        related='bom_request_id.bom_id.sample',
        store=True,
        readonly=False,
    )
    
    excalidraw_data = fields.Json(
        string='Excalidraw Sketch Data',
        compute='_compute_excalidraw_data',
        inverse='_inverse_excalidraw_data',
        store=False,
        compute_sudo=True,
        help='Lightweight sketch data from BOM Request (images stored as attachment IDs)'
    )

    excalidraw_data_standalone = fields.Json(
        string='Excalidraw Sketch Data (Standalone)',
        store=True,
        help='Excalidraw sketch data stored directly on MO when no BOM Request is linked'
    )

    excalidraw_file_ids = fields.Many2many(
        'ir.attachment',
        string='Excalidraw Files',
        related='bom_request_id.excalidraw_file_ids',
        help='Image attachments referenced by the sketch'
    )

    excalidraw_data_with_images = fields.Json(
        string='Excalidraw Data (Full)',
        compute='_compute_excalidraw_data_with_images',
        help='Full data with images restored from attachments for widget display'
    )

    garment_construction_data = fields.Json(
        string='Garment Construction Data',
        compute='_compute_garment_construction_data',
        inverse='_inverse_garment_construction_data',
        store=False,
        compute_sudo=True,
        help='Garment Construction sketch data from BOM Request (images stored as attachment IDs)'
    )

    garment_construction_data_standalone = fields.Json(
        string='Garment Construction Data (Standalone)',
        store=True,
        help='Garment construction data stored directly on MO when no BOM Request is linked'
    )

    garment_construction_file_ids = fields.Many2many(
        'ir.attachment',
        string='Garment Construction Files',
        related='bom_request_id.garment_construction_file_ids',
        help='Image attachments referenced by the Garment Construction sketch'
    )

    garment_construction_data_with_images = fields.Json(
        string='Garment Construction Data (Full)',
        compute='_compute_garment_construction_data_with_images',
        help='Full garment construction data with images restored from attachments for widget display'
    )

    structure_cad_data = fields.Json(
        string='Structure CAD Data',
        store=True,
        help='Structure CAD sketch data stored per Manufacturing Order'
    )

    artwork_data = fields.Text(
        string='Artwork Data',
        compute='_compute_artwork_data',
        inverse='_inverse_artwork_data',
        store=False,
        compute_sudo=True,
        help='Artwork data from BOM Request'
    )

    artwork_data_standalone = fields.Text(
        string='Artwork Data (Standalone)',
        store=True,
        help='Artwork data stored directly on MO when no BOM Request is linked'
    )

    type = fields.Selection(
        related='bom_request_id.type', string='BoM Type', default='normal', required=True, store=True,
        readonly=False)
    subcontractor_ids = fields.Many2many(
        'res.partner',
        'bom_request_subcontractor_rel',
        'bom_request_id',
        'partner_id',
        string='Subcontractors',
        related='bom_request_id.subcontractor_ids',
        store=True,
        readonly=False,
        domain=[('supplier_rank', '>', 0)]
    )
    order_date = fields.Date(string='Order Date', related='bom_request_id.order_date', store=True,
        readonly=False)
    due_date = fields.Date(string='Due Date', related='bom_request_id.due_date', store=True,
        readonly=False)
    structure_ids = fields.One2many(
        'maeknit.structure.line',
        'production_id',
        string='Structure',
    )

    # ── Toile MO fields ──────────────────────────────────────────────────────
    toile_swatch_mo_id = fields.Many2one(
        'mrp.production',
        string='Swatch',
        help='Pick a Swatch MO to pre-populate this Toile with its data',
        domain="[('rel_service.name', '=', 'Swatch Service')]",
        ondelete='set null',
    )

    dev_mo_id = fields.Many2one(
        'mrp.production',
        string='Development MO',
        help='Link this Toile to its parent Development MO',
        domain="[('rel_service.name', '=', 'Development Service')]",
        ondelete='set null',
    )

    # ── Development MO fields ────────────────────────────────────────────────
    toile_mo_ids = fields.One2many(
        'mrp.production',
        'dev_mo_id',
        string='Toile MOs',
        help='All Toile Manufacturing Orders linked to this Development MO',
    )

    dev_swatch_mo_id = fields.Many2one(
        'mrp.production',
        string='Calibration Swatch',
        help='Pick a Swatch MO to pre-populate this Development MO (when no Toile is used)',
        domain="[('rel_service.name', '=', 'Swatch Service')]",
        ondelete='set null',
    )

    swatch_sd_data = fields.Json(
        string='Swatch Stitch Density',
        compute='_compute_swatch_sd_data',
        store=False,
        help='Read-only stitch density from the linked Swatch MO, shown on Dev MO',
    )

    toile_sd_data = fields.Json(
        string='Toile Stitch Density',
        compute='_compute_toile_sd_data',
        store=False,
        help='Read-only stitch density from the first linked Toile MO, shown on Dev MO',
    )

    # ── All Swatch MOs linked to this Dev MO ─────────────────────────────────
    dev_swatch_mo_ids = fields.One2many(
        'mrp.production',
        'parent_garment_mo_id',
        domain=[('product_category', '=', 'swatch')],
        string='Swatch MOs',
    )

    # ── Service product helpers (used as context defaults in views) ───────────
    swatch_service_id = fields.Many2one(
        'product.product',
        compute='_compute_swatch_toile_service_ids',
        store=False,
        string='Swatch Service',
    )

    toile_service_id = fields.Many2one(
        'product.product',
        compute='_compute_swatch_toile_service_ids',
        store=False,
        string='Toile Service',
    )

    def _compute_display_name(self):
        """Show 'Product Name (MO Ref)' when context has show_product_name=True (e.g. swatch picker)."""
        if not self.env.context.get('show_product_name'):
            return super()._compute_display_name()
        for record in self:
            if record.product_id:
                record.display_name = f"{record.product_id.name} ({record.name})"
            else:
                record.display_name = record.name

    @api.depends('company_id')
    def _compute_swatch_toile_service_ids(self):
        swatch_svc = self.env['product.product'].search(
            [('name', '=', 'Swatch Service'), ('type', '=', 'service')], limit=1)
        toile_svc = self.env['product.product'].search(
            [('name', '=', 'Toile Service'), ('type', '=', 'service')], limit=1)
        for rec in self:
            rec.swatch_service_id = swatch_svc
            rec.toile_service_id = toile_svc

    # ── Display helpers (product name + first toile) ─────────────────────────
    toile_swatch_product_name = fields.Char(
        compute='_compute_toile_swatch_product_name',
        store=False,
        string='Calibration Swatch',
    )

    dev_swatch_product_name = fields.Char(
        compute='_compute_dev_swatch_product_name',
        store=False,
        string='Calibration Swatch',
    )

    first_toile_mo_id = fields.Many2one(
        'mrp.production',
        compute='_compute_first_toile_data',
        store=False,
        string='First Toile MO',
    )

    first_toile_product_name = fields.Char(
        compute='_compute_first_toile_data',
        store=False,
        string='Toile',
    )

    toile_swatch_mo_name = fields.Char(
        related='toile_swatch_mo_id.name',
        store=False,
        string='Swatch MO Ref',
    )

    dev_swatch_mo_name = fields.Char(
        related='dev_swatch_mo_id.name',
        store=False,
        string='Swatch MO Ref',
    )

    @api.depends('toile_swatch_mo_id', 'toile_swatch_mo_id.product_id')
    def _compute_toile_swatch_product_name(self):
        for record in self:
            record.toile_swatch_product_name = record.toile_swatch_mo_id.product_id.name or False

    @api.depends('dev_swatch_mo_id', 'dev_swatch_mo_id.product_id')
    def _compute_dev_swatch_product_name(self):
        for record in self:
            record.dev_swatch_product_name = record.dev_swatch_mo_id.product_id.name or False

    @api.depends('toile_mo_ids', 'toile_mo_ids.product_id')
    def _compute_first_toile_data(self):
        for record in self:
            first = record.toile_mo_ids[:1]
            record.first_toile_mo_id = first
            record.first_toile_product_name = first.product_id.name if first else False

    def action_open_sync_wizard(self):
        """Open the Sync wizard for this Dev MO."""
        self.ensure_one()
        wizard = self.env['maeknit.sync.from.mo.wizard'].create({
            'target_mo_id': self.id,
            'source_type': 'swatch',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sync to Dev MO',
            'res_model': 'maeknit.sync.from.mo.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_toile_swatch_mo(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'res_id': self.toile_swatch_mo_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_dev_swatch_mo(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'res_id': self.dev_swatch_mo_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_first_toile_mo(self):
        self.ensure_one()
        first = self.toile_mo_ids[:1]
        if first:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production',
                'res_id': first.id,
                'view_mode': 'form',
                'target': 'current',
            }

    @api.depends('dev_swatch_mo_id', 'dev_swatch_mo_id.calibration_data_with_images')
    def _compute_swatch_sd_data(self):
        for record in self:
            if record.dev_swatch_mo_id:
                record.swatch_sd_data = record.dev_swatch_mo_id.calibration_data_with_images
            else:
                record.swatch_sd_data = {}

    @api.depends('toile_mo_ids', 'toile_mo_ids.calibration_data_with_images')
    def _compute_toile_sd_data(self):
        for record in self:
            first_toile = record.toile_mo_ids[:1]
            if first_toile:
                record.toile_sd_data = first_toile.calibration_data_with_images
            else:
                record.toile_sd_data = {}

    def _derive_toile_product_name(self, swatch_product):
        """Derive a Toile product name from a Swatch product.
        - If the swatch name contains 'Swatch' (any case), replace it with 'Toile'.
        - Otherwise append ' Toile' to the name.
        """
        name = swatch_product.name or ''
        import re
        if re.search(r'swatch', name, re.IGNORECASE):
            return re.sub(r'(?i)swatch', 'Toile', name)
        return name.strip() + ' Toile'

    @api.onchange('toile_swatch_mo_id')
    def _onchange_toile_swatch_mo_id(self):
        """When a Swatch MO is picked on a Toile MO:
        - Derive a Toile product name from the swatch (find or create as consu).
        - Pre-populate Structure, Structure CAD, Artwork, Sketch, Stitch Density.
        - Work orders loaded from the service template are preserved.
        """
        if not self.is_toile_mo or not self.toile_swatch_mo_id:
            return

        # Snapshot current work orders BEFORE setting product_id.
        # Changing product_id can trigger Odoo's BOM-based workorder regeneration
        # which would wipe the operations already loaded from the service template.
        uom_id = (self.product_uom_id.id if self.product_uom_id
                  else self.env.ref('uom.product_uom_unit').id)
        saved_wos = []
        for wo in self.workorder_ids:
            saved_wos.append({
                'name': wo.name,
                'shopfloor_operation_id': wo.shopfloor_operation_id.id if wo.shopfloor_operation_id else False,
                'workcenter_id': wo.workcenter_id.id if wo.workcenter_id else False,
                'sequence': wo.sequence,
                'product_uom_id': wo.product_uom_id.id if wo.product_uom_id else uom_id,
                'employee_assigned_ids': [(6, 0, wo.employee_assigned_ids.ids)],
                'duration_expected': wo.duration_expected,
            })

        swatch_product = self.toile_swatch_mo_id.product_id
        if swatch_product:
            toile_name = self._derive_toile_product_name(swatch_product)
            # Find existing product with this name, or create a new consu one
            ProductTemplate = self.env['product.template']
            tmpl = ProductTemplate.search([('name', '=', toile_name)], limit=1)
            if not tmpl:
                tmpl = ProductTemplate.create({
                    'name': toile_name,
                    'type': 'consu',
                })
            self.product_id = tmpl.product_variant_ids[:1]

        # Restore saved work orders — overwrite whatever product_id change may have reset
        if saved_wos:
            self.workorder_ids = [(5,)] + [(0, 0, v) for v in saved_wos]

        self._copy_swatch_data(self.toile_swatch_mo_id)

    @api.onchange('dev_swatch_mo_id')
    def _onchange_dev_swatch_mo_id(self):
        """When a Swatch MO is picked on a Dev MO (no-Toile path), pre-populate:
        Structure, Structure CAD, Artwork, Sketch, Stitch Density from the Swatch."""
        if not self.is_dev_mo or not self.dev_swatch_mo_id:
            return
        self._copy_swatch_data(self.dev_swatch_mo_id)

    def _copy_swatch_data(self, swatch_mo):
        """Copy all relevant data from a Swatch MO into this Toile/Dev MO when a swatch is picked.
        Called ONLY from onchange handlers — not from action_generate_toile."""
        _log = logging.getLogger(__name__)
        mo_ref = self.name or '(unsaved)'
        sw_ref = swatch_mo.name
        results = {}

        # ── 1. Structure lines ───────────────────────────────────────────────
        swatch_structs = swatch_mo.structure_ids
        structure_commands = [(5, 0, 0)]
        for sl in swatch_structs:
            structure_commands.append((0, 0, {
                'name': sl.name,
                'sequence': sl.sequence,
                'description': sl.description if hasattr(sl, 'description') else '',
            }))
        self.structure_ids = structure_commands
        # Build name → new virtual structure line mapping for component assignment
        struct_by_name = {sl.name: sl for sl in self.structure_ids}
        results['structure_lines'] = f"{'OK' if swatch_structs else 'EMPTY'} — {len(swatch_structs)} line(s) from swatch"

        # ── 2. Structure CAD ─────────────────────────────────────────────────
        self.structure_cad_data = swatch_mo.structure_cad_data
        results['structure_cad'] = 'OK' if swatch_mo.structure_cad_data else 'EMPTY (swatch has none)'

        # ── 3. Artwork ───────────────────────────────────────────────────────
        # Set via computed field so the inverse fires and the widget updates in the onchange
        artwork = swatch_mo.artwork_data_standalone or swatch_mo.artwork_data
        self.artwork_data = artwork
        results['artwork'] = 'OK' if artwork else 'EMPTY (swatch has none)'

        # ── 4. Sketch (Excalidraw) ───────────────────────────────────────────
        # Set via computed field so the inverse fires and the widget updates in the onchange
        sketch = swatch_mo.excalidraw_data_standalone or swatch_mo.excalidraw_data
        self.excalidraw_data = sketch
        results['sketch'] = 'OK' if sketch else 'EMPTY (swatch has none)'

        # ── 5. Development — Whole CAD ───────────────────────────────────────
        self.whole_cad_data = swatch_mo.whole_cad_data
        results['whole_cad'] = 'OK' if swatch_mo.whole_cad_data else 'EMPTY (swatch has none)'

        # ── 6. Development — Garment Construction ────────────────────────────
        dev_data = swatch_mo.garment_construction_data_standalone or swatch_mo.garment_construction_data
        self.garment_construction_data_standalone = dev_data
        results['garment_construction'] = 'OK' if dev_data else 'EMPTY (swatch has none)'

        # ── 7. Stitch Density (calibration data) ─────────────────────────────
        self.calibration_data = swatch_mo.calibration_data
        results['stitch_density'] = 'OK' if swatch_mo.calibration_data else 'EMPTY (swatch has none)'

        # ── 8. Components ────────────────────────────────────────────────────
        # Copy all moves from swatch regardless of their state — user wants
        # line items visible in their draft so they can review and adjust.
        if self.state == 'draft':
            picking_type = self.picking_type_id
            company = self.company_id or self.env.company

            if picking_type and picking_type.default_location_src_id:
                location_id = picking_type.default_location_src_id.id
            else:
                loc = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
                location_id = loc.id if loc else False

            production_location = self.env['stock.location'].search(
                [('usage', '=', 'production'), ('company_id', '=', company.id)], limit=1
            )
            location_dest_id = production_location.id if production_location else False

            # All moves (no state filter) except scrap
            all_moves = swatch_mo.move_raw_ids.filtered(lambda m: not m.scrap_id)

            if not all_moves:
                results['components'] = 'EMPTY (swatch has no component moves)'
            elif not location_id or not location_dest_id:
                results['components'] = (
                    f'SKIPPED — could not resolve locations '
                    f'(location_id={location_id}, dest={location_dest_id})'
                )
            else:
                component_commands = [(5, 0, 0)]
                for move in all_moves:
                    vals = {
                        'name': move.product_id.display_name,
                        'product_id': move.product_id.id,
                        'product_uom_qty': move.product_uom_qty,
                        'product_uom': move.product_uom.id,
                        'picking_type_id': picking_type.id if picking_type else False,
                        'location_id': location_id,
                        'location_dest_id': location_dest_id,
                        'company_id': company.id,
                        'sequence': move.sequence,
                    }
                    for fld in ('x_ply', 'left_carrier', 'right_carrier'):
                        if hasattr(move, fld):
                            vals[fld] = getattr(move, fld)
                    # Map old swatch structure line → new virtual structure line by name
                    if hasattr(move, 'structure_id') and move.structure_id:
                        matched = struct_by_name.get(move.structure_id.name)
                        if matched:
                            vals['structure_id'] = matched.id
                    component_commands.append((0, 0, vals))
                self.move_raw_ids = component_commands
                results['components'] = (
                    f'OK — {len(all_moves)} move(s) copied '
                    f'(includes cancel/done — user will review)'
                )
        else:
            results['components'] = f'SKIPPED — MO state is "{self.state}" (only copies in draft)'

        # ── Summary log ─────────────────────────────────────────────────────
        summary = '\n'.join(f'    {k:<22}: {v}' for k, v in results.items())
        _log.info(
            '[_copy_swatch_data] %s ← swatch %s\n%s',
            mo_ref, sw_ref, summary
        )

    def _sync_from_mo(self, source_mo):
        """Sync all data from source_mo into self (Dev MO). Writes directly to DB.
        Called from the Sync wizard — not from onchange handlers."""
        self.ensure_one()
        _log = logging.getLogger(__name__)
        mo_ref = self.name
        src_ref = source_mo.name
        results = {}

        # ── Scalar / JSON fields — single write ──────────────────────────────
        artwork   = source_mo.artwork_data_standalone or source_mo.artwork_data
        sketch    = source_mo.excalidraw_data_standalone or source_mo.excalidraw_data
        dev_data  = source_mo.garment_construction_data_standalone or source_mo.garment_construction_data
        vals = {
            'structure_cad_data':                  source_mo.structure_cad_data,
            'artwork_data_standalone':             artwork,
            'excalidraw_data_standalone':          sketch,
            'whole_cad_data':                      source_mo.whole_cad_data,
            'garment_construction_data_standalone': dev_data,
            'calibration_data':                    source_mo.calibration_data,
        }
        self.with_context(skip_bom_request_cad_sync=True).write(vals)
        results['structure_cad']       = 'OK' if source_mo.structure_cad_data else 'EMPTY'
        results['artwork']             = 'OK' if artwork else 'EMPTY'
        results['sketch']              = 'OK' if sketch else 'EMPTY'
        results['whole_cad']           = 'OK' if source_mo.whole_cad_data else 'EMPTY'
        results['garment_construction'] = 'OK' if dev_data else 'EMPTY'
        results['stitch_density']      = 'OK' if source_mo.calibration_data else 'EMPTY'

        # ── Structure lines ───────────────────────────────────────────────────
        src_structs = source_mo.structure_ids
        self.with_context(skip_bom_request_cad_sync=True).write({
            'structure_ids': [(5, 0, 0)] + [(0, 0, {
                'name': sl.name,
                'sequence': sl.sequence,
                'description': sl.description if hasattr(sl, 'description') else '',
            }) for sl in src_structs]
        })
        results['structure_lines'] = f"{'OK' if src_structs else 'EMPTY'} ({len(src_structs)} lines)"

        # ── Components (draft only, all moves regardless of state) ────────────
        if self.state == 'draft':
            all_moves = source_mo.move_raw_ids.filtered(lambda m: not m.scrap_id)
            if not all_moves:
                results['components'] = 'EMPTY (source has no moves)'
            else:
                picking_type = self.picking_type_id
                company = self.company_id or self.env.company
                if picking_type and picking_type.default_location_src_id:
                    location_id = picking_type.default_location_src_id.id
                else:
                    loc = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
                    location_id = loc.id if loc else False
                prod_loc = self.env['stock.location'].search(
                    [('usage', '=', 'production'), ('company_id', '=', company.id)], limit=1
                )
                location_dest_id = prod_loc.id if prod_loc else False

                if not location_id or not location_dest_id:
                    results['components'] = f'SKIPPED — locations not resolved'
                else:
                    move_vals_list = []
                    for move in all_moves:
                        v = {
                            'name': move.product_id.display_name,
                            'product_id': move.product_id.id,
                            'product_uom_qty': move.product_uom_qty,
                            'product_uom': move.product_uom.id,
                            'picking_type_id': picking_type.id if picking_type else False,
                            'location_id': location_id,
                            'location_dest_id': location_dest_id,
                            'company_id': company.id,
                            'sequence': move.sequence,
                        }
                        for fld in ('x_ply', 'left_carrier', 'right_carrier'):
                            if hasattr(move, fld):
                                v[fld] = getattr(move, fld)
                        move_vals_list.append(v)
                    self.write({'move_raw_ids': [(5, 0, 0)] + [(0, 0, v) for v in move_vals_list]})
                    results['components'] = f'OK — {len(all_moves)} moves copied'
        else:
            results['components'] = f'SKIPPED — state is "{self.state}" (draft only)'

        # ── Summary log ───────────────────────────────────────────────────────
        summary = '\n'.join(f'    {k:<22}: {v}' for k, v in results.items())
        _log.info('[_sync_from_mo] %s ← %s\n%s', mo_ref, src_ref, summary)
        return results

    garment_doc_data = fields.Json(
        string="Garment Documentation",
        default=lambda self: {
            'unit': 'inches',
            'machine_settings': [],        
            'takedown_measurements': {},
            'notes': ''
        },
        store=True,
    )

    linking_dial_measurements = fields.Json(
        string='Linking Dial Measurements',
        default=lambda self: {
            'unit': 'inches',
            'measurements': [
                {'label': 'Shoulder', 'value': ''},
                {'label': 'Neck hole', 'value': ''},
                {'label': 'Sleeve cuff', 'value': ''},
                {'label': 'Arm hole', 'value': ''},
                {'label': 'Side seam', 'value': ''},
                {'label': 'Bottom cuff', 'value': ''}
            ]
        },
        store=True,
    )
    
    @api.depends('company_id')
    def _compute_is_uk_company(self):
        for record in self:
            record.is_uk_company = 'uk' in (record.company_id.name or '').lower()

    def _compute_excalidraw_data(self):
        """Get excalidraw data: always from the MO's own standalone field"""
        for record in self:
            record.excalidraw_data = record.excalidraw_data_standalone or False

    def _inverse_excalidraw_data(self):
        """Write excalidraw data to the MO's own standalone field (never through BOM Request)"""
        for record in self:
            record.excalidraw_data_standalone = record.excalidraw_data

    def _compute_excalidraw_data_with_images(self):
        """Get full excalidraw data with images restored from attachments"""
        for record in self:
            record.excalidraw_data_with_images = record.excalidraw_data_standalone or {'elements': [], 'appState': {}, 'files': {}}

    def _compute_garment_construction_data(self):
        """Get garment construction data: always from the MO's own standalone field"""
        for record in self:
            record.garment_construction_data = record.garment_construction_data_standalone or False

    def _inverse_garment_construction_data(self):
        """Write garment construction data to the MO's own standalone field (never through BOM Request)"""
        for record in self:
            record.garment_construction_data_standalone = record.garment_construction_data

    def _compute_garment_construction_data_with_images(self):
        """Get full garment construction data with images restored from attachments"""
        for record in self:
            record.garment_construction_data_with_images = record.garment_construction_data_standalone or {'elements': [], 'appState': {}, 'files': {}}

    def _compute_artwork_data(self):
        for record in self:
            if record.bom_request_id and record.bom_request_id.artwork_data:
                record.artwork_data = record.bom_request_id.artwork_data
            elif record.artwork_data_standalone:
                record.artwork_data = record.artwork_data_standalone
            else:
                record.artwork_data = False

    def _inverse_artwork_data(self):
        for record in self:
            if record.bom_request_id:
                record.bom_request_id.artwork_data = record.artwork_data
            else:
                record.artwork_data_standalone = record.artwork_data

    def button_confirm(self):
        for production in self:
            if not production.workorder_ids:
                raise ValidationError(
                    "Please add at least one Work Order before confirming the Manufacturing Order."
                )
            if not production.move_raw_ids:
                raise ValidationError(
                    "Please add at least one Component before confirming the Manufacturing Order."
                )
        result = super().button_confirm()
        # Auto-attach MFG Sheet PDF as an instruction on the Program WO after confirming
        for production in self:
            program_wo = production.workorder_ids.filtered(
                lambda wo: wo.is_program_workorder
            )[:1]
            if program_wo:
                try:
                    program_wo._attach_mfg_sheet_pdf()
                except Exception:
                    pass  # Don't block confirm if PDF generation fails
        return result

    def _generate_raw_moves(self):
        moves = super()._generate_raw_moves()
        for move in moves:
            if move.bom_line_id and move.bom_line_id.operation_id:
                move.consumed_in_operation_id = move.bom_line_id.operation_id.id
                move.operation_id = move.bom_line_id.operation_id.id
        return moves

    # ── Calibration swatch generation — link back to Toile/Dev MO ────────────
    def action_generate_calibration_swatch(self):
        result = super().action_generate_calibration_swatch()
        new_mo_id = result.get('res_id') if isinstance(result, dict) else None
        if new_mo_id:
            if self.is_toile_mo:
                self.toile_swatch_mo_id = new_mo_id
            elif self.is_dev_mo:
                self.dev_swatch_mo_id = new_mo_id
        return result

    # ── Sync dev_swatch_mo_id / toile_swatch_mo_id when calibration widget picks a swatch ──
    def write(self, vals):
        result = super().write(vals)
        if 'calibration_data' in vals:
            cal_data = vals['calibration_data']
            if isinstance(cal_data, str):
                import json
                try:
                    cal_data = json.loads(cal_data)
                except Exception:
                    cal_data = {}
            swatch_product_id = cal_data.get('calibrationSwatchId') if isinstance(cal_data, dict) else None
            if swatch_product_id:
                swatch_mo = self.env['mrp.production'].search([
                    ('product_id', '=', swatch_product_id),
                    ('rel_service.name', '=', 'Swatch Service'),
                ], limit=1)
                if swatch_mo:
                    for record in self:
                        if record.is_dev_mo and record.dev_swatch_mo_id != swatch_mo:
                            record.dev_swatch_mo_id = swatch_mo
                            record._sync_data_from_swatch_mo(swatch_mo)
                        elif record.is_toile_mo and record.toile_swatch_mo_id != swatch_mo:
                            record.toile_swatch_mo_id = swatch_mo
                            record._sync_data_from_swatch_mo(swatch_mo)
        return result

    def _sync_data_from_swatch_mo(self, swatch_mo):
        """Sync all data from swatch_mo into self (Dev/Toile MO) when user picks a pre-existing swatch."""
        import logging
        self.ensure_one()
        logging.info("[SWATCH SYNC] Syncing from %s → %s", swatch_mo.name, self.name)

        # --- JSON fields stored directly on MO ---
        json_vals = {}
        for fname in ['whole_cad_data', 'measurement_widget_data', 'structure_cad_data']:
            val = getattr(swatch_mo, fname, None)
            if val:
                json_vals[fname] = val
        if json_vals:
            self.with_context(skip_bom_request_cad_sync=True).write(json_vals)

        # --- Artwork, sketch, garment construction (computed — proxy through bom_request) ---
        if swatch_mo.artwork_data:
            self.artwork_data = swatch_mo.artwork_data
        if swatch_mo.excalidraw_data:
            self.excalidraw_data = swatch_mo.excalidraw_data
        if swatch_mo.garment_construction_data:
            self.garment_construction_data = swatch_mo.garment_construction_data

        # --- Structure lines — build remap swatch_sl_id → new parent_sl_id ---
        structure_id_remap = {}
        swatch_structure = swatch_mo.structure_ids
        if swatch_structure:
            self.structure_ids.unlink()
            for sl in swatch_structure:
                new_sl = self.env['maeknit.structure.line'].with_context(skip_bom_request_cad_sync=True).create({
                    'production_id': self.id,
                    'name': sl.name,
                    'description': sl.description,
                    'sequence': sl.sequence,
                })
                structure_id_remap[sl.id] = new_sl.id
            logging.info("[SWATCH SYNC] Synced %d structure lines (remap: %s)", len(swatch_structure), structure_id_remap)

        # --- Components ---
        swatch_moves = swatch_mo.move_raw_ids.filtered(lambda m: m.state not in ('done', 'cancel') and not m.scrap_id)
        if swatch_moves:
            try:
                self.do_unreserve()
            except Exception as e:
                logging.warning("[SWATCH SYNC] do_unreserve failed: %s", e)

            not_done = self.move_raw_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
            move_commands = [(2, m.id, 0) for m in not_done]
            for move in swatch_moves:
                old_sid = move.structure_id.id if move.structure_id else False
                new_sid = structure_id_remap.get(old_sid, False) if old_sid else False
                move_commands.append((0, 0, {
                    'name': move.product_id.display_name,
                    'product_id': move.product_id.id,
                    'product_uom_qty': move.product_uom_qty,
                    'product_uom': move.product_uom.id,
                    'picking_type_id': self.picking_type_id.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': self.company_id.id,
                    'sequence': move.sequence,
                    'x_ply': move.x_ply,
                    'left_carrier': move.left_carrier,
                    'right_carrier': move.right_carrier,
                    'structure_id': new_sid,
                }))
            self.write({'move_raw_ids': move_commands})
            self.action_assign()
            logging.info("[SWATCH SYNC] Synced %d components to %s", len(swatch_moves), self.name)

            # Sync components to BOM request (structure-safe — no (5,0,0) on structure_ids)
            if self.bom_request_id:
                bom_cmds = [(5, 0, 0)]
                for move in swatch_moves:
                    old_sid = move.structure_id.id if move.structure_id else False
                    new_sid = structure_id_remap.get(old_sid, False) if old_sid else False
                    bom_cmds.append((0, 0, {
                        'product_id': move.product_id.id,
                        'product_qty': move.product_uom_qty,
                        'product_uom_id': move.product_uom.id,
                        'sequence': move.sequence,
                        'ply': move.x_ply,
                        'left_carrier': move.left_carrier,
                        'right_carrier': move.right_carrier,
                        'structure_id': new_sid,
                    }))
                self.bom_request_id.write({'bom_line_ids': bom_cmds})

        logging.info("[SWATCH SYNC] Done — %s synced from %s", self.name, swatch_mo.name)

    # ── Resolve parent Dev MO for a Swatch MO (for smart button) ─────────────
    linked_dev_mo_id = fields.Many2one(
        'mrp.production',
        compute='_compute_linked_dev_mo_id',
        store=False,
        string='Linked Dev MO',
    )

    @api.depends('parent_garment_mo_id', 'parent_garment_mo_id.is_dev_mo',
                 'parent_garment_mo_id.dev_mo_id')
    def _compute_linked_dev_mo_id(self):
        for record in self:
            parent = record.parent_garment_mo_id
            if not parent:
                record.linked_dev_mo_id = False
            elif parent.is_dev_mo:
                record.linked_dev_mo_id = parent
            elif parent.is_toile_mo and parent.dev_mo_id:
                record.linked_dev_mo_id = parent.dev_mo_id
            else:
                record.linked_dev_mo_id = False

    def action_open_linked_dev_mo(self):
        self.ensure_one()
        if self.linked_dev_mo_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production',
                'res_id': self.linked_dev_mo_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_open_dev_mo_from_toile(self):
        """Navigate from a Toile MO back to its parent Development MO."""
        self.ensure_one()
        if self.dev_mo_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.production',
                'res_id': self.dev_mo_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_generate_toile(self, swatch_mo_id=None):
        """
        Generate a Toile MO linked to this Development MO.
        Copies all data from the linked Swatch MO (excluding Panel CAD / measurement_widget_data,
        which the Toile builds fresh). Components and structure are copied from the Swatch MO.
        Work orders are copied from the Dev MO.

        swatch_mo_id: optional int — if provided, use this swatch instead of dev_swatch_mo_id.
        """
        self.ensure_one()
        if swatch_mo_id:
            source_mo = self.env['mrp.production'].browse(int(swatch_mo_id))
            if not source_mo.exists():
                raise UserError(_("Selected swatch MO not found."))
        else:
            source_mo = self.dev_swatch_mo_id
        if not source_mo:
            raise UserError(_(
                "Please select a Calibration Swatch on this Development MO before generating a Toile."
            ))

        toile_name = f"{self.product_id.name} - Toile"
        logging.info("[GEN TOILE] Creating Toile: %s from swatch %s", toile_name, source_mo.name)

        # Product category — 'garment' so is_swatch_mo stays False; is_toile_mo=True from rel_service
        toile_category = self.env['product.category'].search([('name', '=', 'Toile')], limit=1)
        if not toile_category:
            toile_category = self.env['product.category'].create({'name': 'Toile'})

        toile_service = self.env['product.product'].search(
            [('name', '=', 'Toile Service'), ('type', '=', 'service')], limit=1)

        # ── Product + BOM ─────────────────────────────────────────────────────
        toile_product_tmpl = self.env['product.template'].create({
            'name': toile_name,
            'type': 'consu',
            'categ_id': toile_category.id,
            'product_category': 'garment',
            'brand_id': self.partner_id.id,
        })
        toile_product = toile_product_tmpl.product_variant_id

        toile_bom = self.env['mrp.bom'].create({
            'product_tmpl_id': toile_product_tmpl.id,
            'product_id': toile_product.id,
            'product_qty': 1.0,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'rel_service': toile_service.id if toile_service else self.rel_service.id,
        })

        colorway_id = self.colorway_id.id if self.colorway_id else False

        # ── Manufacturing Order ───────────────────────────────────────────────
        # Copies data from Swatch MO — intentionally excludes measurement_widget_data
        # so the Toile can build its own Panel CAD from scratch.
        new_mo = self.env['mrp.production'].create({
            'product_id': toile_product.id,
            'product_qty': 1,
            'product_uom_id': self.product_uom_id.id,
            'company_id': self.company_id.id,
            'bom_id': toile_bom.id,
            'partner_id': self.partner_id.id,
            'rel_service': toile_service.id if toile_service else self.rel_service.id,
            'colorway_id': colorway_id,
            'yarn_variant': source_mo.yarn_variant.id if source_mo.yarn_variant else False,
            'gauge_id': self.gauge_id.id if self.gauge_id else False,
            'whole_cad_data': source_mo.whole_cad_data,
            # measurement_widget_data intentionally NOT copied — Toile builds its own Panel CAD
            'calibration_data': source_mo.calibration_data,
            'artwork_data_standalone': source_mo.artwork_data,
            'excalidraw_data_standalone': source_mo.excalidraw_data,
            'garment_construction_data_standalone': source_mo.garment_construction_data,
            'structure_cad_data': source_mo.structure_cad_data,
            'parent_garment_mo_id': self.id,
            'dev_mo_id': self.id,
            'toile_swatch_mo_id': source_mo.id,
        })
        logging.info("[GEN TOILE] Created MO: %s", new_mo.name)

        # ── BOM Request ───────────────────────────────────────────────────────
        bom_request_vals = {
            'product_tmpl_id': toile_product_tmpl.id,
            'partner_id': self.partner_id.id,
            'product_id': toile_product.id,
            'state': 'done',
            'rel_service': toile_service.id if toile_service else self.rel_service.id,
            'mo_id': new_mo.id,
            'bom_id': toile_bom.id,
        }
        if source_mo.calibration_data:
            bom_request_vals['calibration_data'] = source_mo.calibration_data
        bom_request = self.env['maeknit.bom.request'].create(bom_request_vals)
        new_mo.write({'bom_request_id': bom_request.id})
        logging.info("[GEN TOILE] BOM request: %s", bom_request.name)

        # ── Structure lines from Swatch MO (build remap for component structure_id) ──
        structure_id_remap = {}
        for sl in source_mo.structure_ids:
            new_sl = self.env['maeknit.structure.line'].with_context(
                skip_bom_request_cad_sync=True
            ).create({
                'production_id': new_mo.id,
                'name': sl.name,
                'description': sl.description,
                'sequence': sl.sequence,
            })
            structure_id_remap[sl.id] = new_sl.id
        logging.info("[GEN TOILE] Copied %d structure lines (remap: %s)",
                     len(source_mo.structure_ids), structure_id_remap)

        # ── Components from Swatch MO (with structure remap) ─────────────────
        swatch_moves = source_mo.move_raw_ids.filtered(
            lambda m: m.state not in ('done', 'cancel') and not m.scrap_id
        )
        if swatch_moves:
            move_commands = []
            bom_cmds = [(5, 0, 0)]
            for move in swatch_moves:
                old_sid = move.structure_id.id if move.structure_id else False
                new_sid = structure_id_remap.get(old_sid, False) if old_sid else False
                move_commands.append((0, 0, {
                    'name': move.product_id.display_name,
                    'product_id': move.product_id.id,
                    'product_uom_qty': move.product_uom_qty,
                    'product_uom': move.product_uom.id,
                    'picking_type_id': new_mo.picking_type_id.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': new_mo.company_id.id,
                    'sequence': move.sequence,
                    'x_ply': move.x_ply,
                    'left_carrier': move.left_carrier,
                    'right_carrier': move.right_carrier,
                    'structure_id': new_sid,
                }))
                bom_cmds.append((0, 0, {
                    'product_id': move.product_id.id,
                    'product_qty': move.product_uom_qty,
                    'product_uom_id': move.product_uom.id,
                    'sequence': move.sequence,
                    'ply': move.x_ply,
                    'left_carrier': move.left_carrier,
                    'right_carrier': move.right_carrier,
                    'structure_id': new_sid,
                }))
            new_mo.write({'move_raw_ids': move_commands})
            bom_request.write({'bom_line_ids': bom_cmds})
            logging.info("[GEN TOILE] Copied %d components", len(swatch_moves))

        # ── Work orders from Dev MO (self), skipping linking operations ───────
        Workorder = self.env['mrp.workorder']
        for wo in self.workorder_ids:
            if 'link' in wo.name.lower():
                logging.info("[GEN TOILE] Skipping linking WO: %s", wo.name)
                continue
            shop_op = self.env['maeknit.shopfloor.operation'].search(
                [('name', '=ilike', wo.name)], limit=1)
            new_vals = {
                'production_id': new_mo.id,
                'name': wo.name,
                'workcenter_id': wo.workcenter_id.id,
                'product_id': new_mo.product_id.id,
                'product_uom_id': wo.product_uom_id.id,
                'company_id': wo.company_id.id,
                'duration_expected': wo.duration_expected,
                'sequence': wo.sequence,
                'state': 'waiting',
            }
            if shop_op:
                new_vals['shopfloor_operation_id'] = shop_op.id
            if wo.employee_assigned_ids:
                new_vals['employee_assigned_ids'] = [(6, 0, wo.employee_assigned_ids.ids)]
            new_wo = Workorder.create(new_vals)
            if hasattr(self, '_copy_all_attachments'):
                try:
                    self._copy_all_attachments(wo, new_wo)
                except Exception as e:
                    logging.info("[GEN TOILE] Attachment copy failed for %s: %s", wo.name, e)

        # ── Render images from Dev MO ─────────────────────────────────────────
        for img in self.render_image_ids:
            self.env['render.image.line'].create({
                'production_id': new_mo.id,
                'name': img.name,
                'image': img.image,
                'image_filename': img.image_filename,
                'sequence': img.sequence,
            })

        # ── Force colorway/yarn_variant/gauge after ORM computes settle ───────
        forced_vals = {}
        if colorway_id:
            forced_vals['colorway_id'] = colorway_id
        if source_mo.yarn_variant:
            forced_vals['yarn_variant'] = source_mo.yarn_variant.id
        if self.gauge_id:
            forced_vals['gauge_id'] = self.gauge_id.id
        if forced_vals:
            new_mo.write(forced_vals)
            logging.info("[GEN TOILE] Forced attrs: %s", forced_vals)

        logging.info("[GEN TOILE] Done — navigating to %s", new_mo.name)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Toile MO'),
            'res_model': 'mrp.production',
            'res_id': new_mo.id,
            'view_mode': 'form',
            'target': 'current',
            'views': [(False, 'form')],
        }
