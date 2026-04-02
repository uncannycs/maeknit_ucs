from odoo import models, fields, api, _
from markupsafe import Markup
import logging

class MrpWorkorder(models.Model):
    _name = 'mrp.workorder'
    _inherit = ["mrp.workorder", "mail.thread", "mail.activity.mixin"]
    _description = 'Work Order'
    # In Progress → Ready → Waiting → Pending → Done → Cancelled
    _order = 'state_sort_order asc, name asc'

    _STATE_SORT = {
        'progress': 1,
        'ready': 2,
        'waiting': 3,
        'pending': 4,
        'done': 5,
        'cancel': 6,
    }

    SPEC_GARMENT_KEYWORDS = ('spec garment', 'documentation')

    def _compute_display_name(self):
        for wo in self:
            wo.display_name = wo.name

    workcenter_id = fields.Many2one(
        'mrp.workcenter', 
        'Work Center', 
        required=False,  # Changed from required=True in base model
        group_expand='_read_group_workcenter_id', 
        check_company=True,
        domain="[('id', 'in', workcenter_domain_ids if workcenter_domain_ids else [])]"
    )
    
    workcenter_domain_ids = fields.Many2many(
        'mrp.workcenter', 
        compute='_compute_workcenter_domain', 
        string='Available Workcenters',
        compute_sudo=True,
        store=False
    )

    knit_attempt = fields.Integer(
        string='Knit Attempt',
        help='Current knit attempt number for this operation'
    )
    program_version = fields.Integer(
        string='Program Count',
        help='Number of times this operation has been reprogrammed'
    )
    
    name = fields.Char(
        compute="_compute_workorder_name",
        store=True,
        readonly=False,
    )
    
    program_attachment_count = fields.Integer(
        string='Program Files', 
        compute='_compute_attachment_counts', 
        store=True
    )
    instruction_attachment_count = fields.Integer(
        string='Instruction Files', 
        compute='_compute_attachment_counts', 
        store=True
    )
    program_display = fields.Html(string='Program Display', compute='_compute_attachment_display', store=False)
    instruction_display = fields.Html(string='Instruction Display', compute='_compute_attachment_display', store=False)
    has_instruction_files = fields.Boolean(
        compute='_compute_has_files', 
        string='Has Instructions', 
        store=True
    )
    has_program_files = fields.Boolean(
        compute='_compute_has_files', 
        string='Has Programs', 
        store=True
    )
    
    is_last_finished_wo = fields.Boolean(
        compute='_compute_is_last_finished_wo',
        string='Is Last Finished Work Order',
        store=False
    )
    text_instruction_notes = fields.Text(string="Instruction Notes")
    text_program_notes = fields.Text(string="Program Notes")

    instruction_notes_last_updated = fields.Datetime(string="Instruction Notes Last Updated")
    program_notes_last_updated = fields.Datetime(string="Program Notes Last Updated")

    mfg_sheet_last_updated = fields.Datetime(string="MFG Sheet Last Updated", store=True)
    
    shopfloor_operation_id = fields.Many2one('maeknit.shopfloor.operation', string='Shopfloor Operations')
    
    wizard_measurements_submitted = fields.Boolean(
        string='Wizard Measurements Submitted',
        default=False,
        help='Flag to track if measurement wizard was completed'
    )

    # Reprogram alert tracking
    pending_reprogram_alert_ids = fields.One2many(
        'quality.alert',
        'program_workorder_id',
        string='Pending Reprogram Alerts',
        help='Quality alerts requesting this Program workorder to be re-done',
    )
    has_pending_reprogram_alert = fields.Boolean(
        compute='_compute_has_pending_reprogram_alert',
        string='Has Pending Reprogram Alert',
        store=False,
    )
    is_knit_workorder = fields.Boolean(
        compute='_compute_is_knit_workorder',
        string='Is Knit Work Order',
        store=False,
    )
    is_program_workorder = fields.Boolean(
        compute='_compute_is_program_workorder',
        string='Is Program Work Order',
        store=False,
    )
    is_wash_workorder = fields.Boolean(
        compute='_compute_is_wash_workorder',
        string='Is Wash Work Order',
        store=False,
    )
    wash_library_id = fields.Many2one(
        'wash.library',
        string='Wash',
        store=True,
    )
    is_dry_workorder = fields.Boolean(
        compute='_compute_is_dry_workorder',
        string='Is Dry Work Order',
        store=False,
    )
    dry_library_id = fields.Many2one(
        'dry.library',
        string='Dry',
        store=True,
    )
    has_reprogram_request = fields.Boolean(
        string='Has Reprogram Request',
        default=False,
    )
    latest_reprogram_message_id = fields.Many2one(
        'mail.message',
        string='Latest Reprogram Note',
    )
    state_sort_order = fields.Integer(
        string='State Sort Order',
        compute='_compute_state_sort_order',
        store=True,
    )

    @api.depends('state', 'production_id.state')
    def _compute_state_sort_order(self):
        for wo in self:
            if wo.production_id.state == 'draft':
                wo.state_sort_order = 99
            else:
                wo.state_sort_order = self._STATE_SORT.get(wo.state, 98)

    @api.depends('name')
    def _compute_is_knit_workorder(self):
        """Check if this is a Knit workorder based on name."""
        for wo in self:
            wo.is_knit_workorder = wo.name and 'knit' in wo.name.lower()

    @api.depends('name')
    def _compute_is_program_workorder(self):
        """Check if this is a Program workorder based on name."""
        for wo in self:
            wo.is_program_workorder = wo.name and 'program' in wo.name.lower()

    @api.depends('name')
    def _compute_is_wash_workorder(self):
        """Check if this is a Wash workorder based on name."""
        for wo in self:
            wo.is_wash_workorder = bool(wo.name and 'wash' in wo.name.lower())

    @api.depends('name')
    def _compute_is_dry_workorder(self):
        """Check if this is a Dry workorder based on name."""
        for wo in self:
            wo.is_dry_workorder = bool(wo.name and 'dry' in wo.name.lower())

    @api.depends('pending_reprogram_alert_ids', 'pending_reprogram_alert_ids.stage_id', 'pending_reprogram_alert_ids.stage_id.done')
    def _compute_has_pending_reprogram_alert(self):
        """Check if there are any pending (not done) reprogram alerts for this workorder."""
        for wo in self:
            wo.has_pending_reprogram_alert = any(
                not alert.stage_id.done for alert in wo.pending_reprogram_alert_ids
            )

    def action_request_new_program(self):
        """Open the Request New Program wizard for Knit workorders."""
        self.ensure_one()
        view = self.env.ref('maeknit_mfg_customization.view_request_new_program_wizard_form')
        return {
            'name': _('Request New Program'),
            'type': 'ir.actions.act_window',
            'res_model': 'request.new.program.wizard',
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
            'context': {
                'default_workorder_id': self.id,
            },
        }

    def action_show_latest_reprogram_note(self):
        """Open the form of the most recent reprogram log note."""
        self.ensure_one()
        msg = self.latest_reprogram_message_id
        if not msg:
            return {'type': 'ir.actions.act_window_close'}
        view = self.env.ref('maeknit_mfg_customization.view_reprogram_note_body_form', raise_if_not_found=False)
        views = [(view.id, 'form')] if view else [(False, 'form')]
        return {
            'name': _('Latest reprogram note'),
            'type': 'ir.actions.act_window',
            'res_model': 'mail.message',
            'res_id': msg.id,
            'view_mode': 'form',
            'views': views,
            'target': 'new',
        }

    def _move_reprogram_alerts_to_in_progress(self):
        """Move pending reprogram alerts to 'In Progress' stage when Program workorder starts."""
        QualityAlertStage = self.env['quality.alert.stage']
        for wo in self:
            pending_alerts = wo.pending_reprogram_alert_ids.filtered(
                lambda a: a.stage_id and not a.stage_id.done
            )
            if not pending_alerts:
                continue

            # Find the "In Progress" stage (second stage by sequence, not done)
            in_progress_stage = QualityAlertStage.search([
                ('done', '=', False),
            ], order='sequence', offset=1, limit=1)

            # Fallback: find any stage with 'progress' in name
            if not in_progress_stage:
                in_progress_stage = QualityAlertStage.search([
                    ('name', 'ilike', 'progress'),
                    ('done', '=', False),
                ], limit=1)

            if in_progress_stage:
                pending_alerts.write({'stage_id': in_progress_stage.id})
                logging.info(
                    "Custom Code: [REPROGRAM] Moved %d alerts to 'In Progress' for Program WO %s",
                    len(pending_alerts), wo.name
                )

    def _move_reprogram_alerts_to_done(self):
        """Move pending reprogram alerts to 'Done' stage when Program workorder finishes.
        Also set the linked Knit workorder back to 'ready' state."""
        QualityAlertStage = self.env['quality.alert.stage']
        for wo in self:
            pending_alerts = wo.pending_reprogram_alert_ids.filtered(
                lambda a: a.stage_id and not a.stage_id.done
            )
            if not pending_alerts:
                continue

            # Find the "Done" stage (stage with done=True)
            done_stage = QualityAlertStage.search([
                ('done', '=', True),
            ], order='sequence', limit=1)

            if done_stage:
                pending_alerts.write({'stage_id': done_stage.id})
                wo.write({
                    'has_reprogram_request': False,
                    'latest_reprogram_message_id': False,
                })
                logging.info(
                    "Custom Code: [REPROGRAM] Moved %d alerts to 'Done' for Program WO %s",
                    len(pending_alerts), wo.name
                )

            # Set the linked Knit workorder back to 'ready' state
            for alert in pending_alerts:
                knit_wo = alert.workorder_id
                if knit_wo and knit_wo.state == 'pending':
                    knit_wo.write({'state': 'ready'})
                    logging.info(
                        "[REPROGRAM] Set Knit WO %s back to Ready (Program completed)",
                        knit_wo.name
                    )

    @api.depends('shopfloor_operation_id')
    def _compute_workorder_name(self):
        for wo in self:
            if wo.shopfloor_operation_id:
                wo.name = wo.shopfloor_operation_id.name
            elif not wo.name:
                wo.name = _('New')

    def _compute_attachment_counts(self):
        """Compute the count of program and instruction attachments"""
        Attachment = self.env['ir.attachment']

        # Initialize all counts to 0
        for wo in self:
            wo.program_attachment_count = 0
            wo.instruction_attachment_count = 0

        # Filter out records without IDs
        workorders_with_id = self.filtered(lambda w: w.id)
        if not workorders_with_id:
            logging.info(" Custom Code: [ATTACH COUNT] No workorders with IDs to compute")
            return

        logging.info(f" Custom Code: [ATTACH COUNT] Computing attachment counts for {len(workorders_with_id)} workorders: {[wo.name for wo in workorders_with_id]}")

        # Use read_group to get counts in a single query
        domain = [
            ('res_model', '=', 'mrp.workorder'),
            ('res_id', 'in', workorders_with_id.ids),
            ('attachment_type', 'in', ['program', 'instruction'])
        ]

        groups = Attachment.read_group(
            domain,
            ['res_id', 'attachment_type'],
            ['res_id', 'attachment_type'],
            lazy=False
        )

        logging.info(f" Custom Code: [ATTACH COUNT] Found {len(groups)} attachment groups")

        # Build a mapping: {res_id: {'program': count, 'instruction': count}}
        counts_map = {}
        for group in groups:
            res_id = group['res_id']
            att_type = group['attachment_type']
            count = group['__count']

            if res_id not in counts_map:
                counts_map[res_id] = {'program': 0, 'instruction': 0}
            counts_map[res_id][att_type] = count
            logging.info(f" Custom Code: [ATTACH COUNT]   WO ID {res_id}: {att_type} = {count}")

        # Assign counts to records
        for wo in workorders_with_id:
            if wo.id in counts_map:
                wo.program_attachment_count = counts_map[wo.id]['program']
                wo.instruction_attachment_count = counts_map[wo.id]['instruction']
                logging.info(f" Custom Code: [ATTACH COUNT] {wo.name} (ID {wo.id}): program={wo.program_attachment_count}, instruction={wo.instruction_attachment_count}")
            else:
                logging.info(f" Custom Code: [ATTACH COUNT] {wo.name} (ID {wo.id}): No attachments found")

    def _compute_attachment_display(self):
        """Compute HTML display for attachments"""
        for wo in self:
            wo.program_display = ''
            wo.instruction_display = ''
            
            if wo.id:
                program_attachments = self.env['ir.attachment'].search([
                    ('res_model', '=', 'mrp.workorder'),
                    ('res_id', '=', wo.id),
                    ('attachment_type', '=', 'program')
                ])
                instruction_attachments = self.env['ir.attachment'].search([
                    ('res_model', '=', 'mrp.workorder'),
                    ('res_id', '=', wo.id),
                    ('attachment_type', '=', 'instruction')
                ])
                
                if program_attachments:
                    links = ['<a href="/web/content/%s?download=true">%s</a>' % (att.id, att.name) 
                            for att in program_attachments]
                    wo.program_display = Markup('<br/>'.join(links))
                
                if instruction_attachments:
                    links = ['<a href="/web/content/%s?download=true">%s</a>' % (att.id, att.name) 
                            for att in instruction_attachments]
                    wo.instruction_display = Markup('<br/>'.join(links))

    @api.depends(
        "instruction_attachment_count",
        "program_attachment_count",
        "text_instruction_notes",
        "text_program_notes",
        "wash_library_id",
        "dry_library_id",
    )
    def _compute_has_files(self):
        """True if either attachments OR notes OR wash/dry library selection exist."""
        for wo in self:
            wo.has_instruction_files = bool(
                wo.instruction_attachment_count
                or (wo.text_instruction_notes and wo.text_instruction_notes.strip())
                or wo.wash_library_id
                or wo.dry_library_id
            )
            wo.has_program_files = bool(
                wo.program_attachment_count or (wo.text_program_notes and wo.text_program_notes.strip())
            )
            if wo.program_attachment_count > 0 or wo.instruction_attachment_count > 0:
                logging.info(
                    f" Custom Code: [HAS FILES] {wo.name} (ID {wo.id}): "
                    f"program_count={wo.program_attachment_count}, has_program_files={wo.has_program_files}, "
                    f"instruction_count={wo.instruction_attachment_count}, has_instruction_files={wo.has_instruction_files}"
                )

    def _compute_is_last_finished_wo(self):
        """Check if this work order is the last finished one in the manufacturing order"""
        for wo in self:
            if not wo.id or isinstance(wo.id, models.NewId):
                wo.is_last_finished_wo = False
                continue
            
            wo.is_last_finished_wo = False
            
            if wo.state == 'done' and wo.production_id:
                # Find all finished work orders in this MO
                finished_wos = self.env['mrp.workorder'].search([
                    ('production_id', '=', wo.production_id.id),
                    ('state', '=', 'done')
                ], order='sequence desc', limit=1)
                
                # Check if this is the last one (highest sequence)
                if finished_wos and finished_wos.id == wo.id:
                    wo.is_last_finished_wo = True
                    logging.info(" Custom Code:[RESTART] WO %s (seq %s) is the last finished work order", wo.name, wo.sequence)

    def action_upload_program_files(self):
        """Open wizard to upload program files"""
        self.ensure_one()
        view = self.env.ref('maeknit_mfg_customization.view_workorder_attachment_wizard_form')
        return {
            'name': 'Upload Program Files',
            'type': 'ir.actions.act_window',
            'res_model': 'workorder.attachment.wizard',
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
            'context': {
                'default_workorder_id': self.id,
                'default_attachment_type': 'program',
            },
        }

    def action_upload_instruction_files(self):
        """Open wizard to upload instruction files"""
        self.ensure_one()
        view = self.env.ref('maeknit_mfg_customization.view_workorder_attachment_wizard_form')
        return {
            'name': 'Upload Instruction Files',
            'type': 'ir.actions.act_window',
            'res_model': 'workorder.attachment.wizard',
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
            'context': {
                'default_workorder_id': self.id,
                'default_attachment_type': 'instruction',
            },
        }

    def _attach_mfg_sheet_pdf(self):
        """Generate the MFG Sheet PDF and save it silently as an instruction
        attachment on this Program WO. Safe to call without returning an action."""
        import base64
        self.ensure_one()
        if not self.production_id:
            return
        report = self.env.ref('maeknit_mfg_customization.action_report_mfg_sheet').sudo()
        pdf_bytes, _ = report._render_qweb_pdf(
            report.report_name, [self.production_id.id]
        )
        self.env['ir.attachment'].search([
            ('res_model', '=', 'mrp.workorder'),
            ('res_id', '=', self.id),
            ('attachment_type', '=', 'instruction'),
            ('name', '=like', 'MFG Sheet -%'),
        ]).unlink()
        self.env['ir.attachment'].create({
            'name': f'MFG Sheet - {self.production_id.name}.pdf',
            'datas': base64.b64encode(pdf_bytes),
            'res_model': 'mrp.workorder',
            'res_id': self.id,
            'attachment_type': 'instruction',
            'mimetype': 'application/pdf',
        })
        self.write({'mfg_sheet_last_updated': fields.Datetime.now()})

    def action_update_mfg_sheet(self):
        """Generate the MFG Sheet PDF and save it as an instruction attachment
        on this Program WO (called from the Update Now button)."""
        self.ensure_one()
        if not self.production_id:
            raise UserError(_("No production order is linked to this work order."))
        self._attach_mfg_sheet_pdf()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'MFG Sheet updated successfully.',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_download_mfg_sheet(self):
        """Download the stored MFG Sheet PDF from instructions, generating it first if needed."""
        self.ensure_one()
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', 'mrp.workorder'),
            ('res_id', '=', self.id),
            ('attachment_type', '=', 'instruction'),
            ('name', '=like', 'MFG Sheet -%'),
        ], order='id desc', limit=1)

        if not attachment:
            self.action_update_mfg_sheet()
            attachment = self.env['ir.attachment'].search([
                ('res_model', '=', 'mrp.workorder'),
                ('res_id', '=', self.id),
                ('attachment_type', '=', 'instruction'),
                ('name', '=like', 'MFG Sheet -%'),
            ], order='id desc', limit=1)

        if not attachment:
            raise UserError(_("Could not generate the MFG Sheet. Please try again."))

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    def web_read(self, specification):
        """Ensure knit_attempt and program_version fields always load safely."""

        # 3. Perform read safely
        try:
            result = super().web_read(specification)
        except Exception as e:
            
            if isinstance(specification, dict):
                for field_name in specification.keys():
                    try:
                        logging.info(" Custom Code: DEBUG] Testing field: %s", field_name)
                        self.read([field_name])
                        logging.info(" Custom Code: DEBUG] Field %s read successfully", field_name)
                    except Exception as fe:
                        logging.error(" DEBUG] Field %s failed: %s", field_name, str(fe))
                        logging.error("Field %s failed individually: %s", field_name, fe)
            raise

        # 4. Debug confirmation
        if result:
            sample = result[0] if isinstance(result, list) else result

        return result

    def _get_fields_for_shopfloor_display(self):
        """Override to add custom fields to shopfloor display"""
        fields = super()._get_fields_for_shopfloor_display() if hasattr(super(), '_get_fields_for_shopfloor_display') else []
        # Add our custom fields to the list
        custom_fields = ['knit_attempt', 'program_version', 'is_last_finished_wo']  # Added 'is_last_finished_wo'
        return list(set(fields + custom_fields))

    def _is_spec_garment_workorder(self):
        """Normalize detection for Spec Garment (formerly Documentation) workorders."""
        name = (self.name or '').lower()
        return any(keyword in name for keyword in self.SPEC_GARMENT_KEYWORDS)

    def button_start(self):
        """Override to show measurement wizard when starting Spec Garment workorder
        and to move reprogram alerts to 'In Progress' when starting Program workorder."""
        for wo in self:
            # Handle reprogram alerts for Program workorders
            if wo.name and 'program' in wo.name.lower():
                wo._move_reprogram_alerts_to_in_progress()

            # Existing logic for Spec Garment workorder (formerly Documentation)
            if wo._is_spec_garment_workorder():
                logging.info(f" Custom Code: Spec Garment workorder {wo.name} check for MO {wo.production_id.name}")

                # Toile MOs: open the panel-based actual measurements wizard
                # Check rel_service directly (is_toile_mo is non-stored so can miss on some records)
                prod = wo.production_id
                is_toile = bool(prod.rel_service) and 'toile' in (prod.rel_service.name or '').lower()
                logging.info(
                    "[ToileDoc] WO %s: is_toile_mo=%s rel_service=%s is_toile=%s",
                    wo.name, prod.is_toile_mo, prod.rel_service.name if prod.rel_service else None, is_toile
                )
                if is_toile:
                    super(MrpWorkorder, wo).button_start()
                    return {
                        'type': 'ir.actions.act_window',
                        'name': _('Record Actual Measurements'),
                        'res_model': 'toile.doc.wizard',
                        'view_mode': 'form',
                        'target': 'new',
                        'context': {
                            'default_workorder_id': wo.id,
                            'default_production_id': wo.production_id.id,
                        },
                    }

                whole_cad_data = wo.production_id.whole_cad_data if isinstance(wo.production_id.whole_cad_data, dict) else {}
                measurements = whole_cad_data.get('measurements', [])
                
                valid_measurements = [m for m in measurements if isinstance(m, dict) and (m.get('name') or m.get('request'))]
                
                logging.info(f" Custom Code: [WIZARD CHECK] Found {len(valid_measurements)} valid measurements to display")
                
                if valid_measurements:
                    super(MrpWorkorder, wo).button_start()
                    
                    logging.info(f" Custom Code: [WIZARD] Opening measurement wizard for workorder {wo.id}")
                    return {
                        'type': 'ir.actions.act_window',
                        'name': _('Enter Actual CAD Measurements'),
                        'res_model': 'whole.cad.measurement.wizard',
                        'view_mode': 'form',
                        'target': 'new',
                        'context': {
                            'default_workorder_id': wo.id,
                            'default_production_id': wo.production_id.id,
                        },
                    }
            if 'stitch density' in wo.name.lower() and wo.production_id.product_category == 'swatch':
                logging.info(f" Custom Code: Stitch Density workorder {wo.name} check for MO {wo.production_id.name}")
                super(MrpWorkorder, wo).button_start()
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Enter Swatch Measurements'),
                    'res_model': 'stitch.density.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_mode': 'swatch_measurement',
                        'default_measurement_unit': 'inches',
                        'default_calibration_mo_id': wo.production_id.id,
                        'default_parent_garment_mo_id': wo.production_id.parent_garment_mo_id.id,
                    },
                }
        
        res = super().button_start()
        
        for wo in self:
            next_wos = self.env['mrp.workorder'].search([
                ('production_id', '=', wo.production_id.id),
                ('sequence', '>', wo.sequence),
                ('state', '=', 'waiting')
            ])
            for nxt in next_wos:
                nxt._compute_state()
        return res

    def button_finish(self):
        res = super().button_finish()
        for wo in self:
            # Handle reprogram alerts for Program workorders
            if wo.name and 'program' in wo.name.lower() and wo.state == 'done':
                wo._move_reprogram_alerts_to_done()

            if wo._is_spec_garment_workorder() and wo.state == 'done':
                # Skip version bump if wizard already handled it
                if not wo.wizard_measurements_submitted:
                    logging.info(f" Custom Code: [VERSION BUMP] Spec Garment workorder {wo.name} completed - triggering CAD version bump for MO {wo.production_id.name}")
                    # wo.production_id.action_bump_whole_cad_version()
                else:
                    logging.info(f" Custom Code: [VERSION BUMP] Skipping automatic version bump for {wo.name} - measurements were already submitted via wizard")
                    # Reset the flag after checking
                    wo.wizard_measurements_submitted = False
            
            # unlock and recompute next waiting WOs in same MO
            next_wos = self.env['mrp.workorder'].search([
                ('production_id', '=', wo.production_id.id),
                ('sequence', '>', wo.sequence),
                ('state', '=', 'waiting')
            ])
            for nxt in next_wos:
                nxt._compute_state()
        return res
    
    def open_production_order(self):
        """Open the related Manufacturing Order from a Work Order."""
        self.ensure_one()
        if not self.production_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Manufacturing Order',
            'res_model': 'mrp.production',
            'view_mode': 'form',
            'res_id': self.production_id.id,
            'target': 'current',
        }

    
    @api.depends('production_availability', 'blocked_by_workorder_ids.state')
    def _compute_state(self):
        """
        Override: Enforce strict sequential flow across workorders.
        A WO cannot become 'ready' unless all lower-sequence WOs
        in the same MO are 'done' or 'cancelled'.
        """
        for workorder in self:
            # Keep Odoo's base logic first
            if workorder.state not in ('pending', 'waiting', 'ready'):
                continue

            no_recursion_blocked_by_workorder_ids = workorder.blocked_by_workorder_ids.with_context(no_recursion=True)

            if workorder.production_availability == 'assigned':
                if all(wo.state in ('done', 'cancel') for wo in no_recursion_blocked_by_workorder_ids):
                    workorder.state = 'ready'
                else:
                    workorder.state = 'pending'
                # continue after base logic

            elif self._context.get('no_recursion'):
                continue

            elif no_recursion_blocked_by_workorder_ids and not all(
                wo.state in ('done', 'cancel') for wo in no_recursion_blocked_by_workorder_ids
            ):
                workorder.state = 'pending'
            else:
                workorder.state = 'waiting'

            # --- Strict Sequence Enforcement ---
            if workorder.production_id and not isinstance(workorder.production_id.id, models.NewId):
                all_wos = self.env['mrp.workorder'].search([
                    ('production_id', '=', workorder.production_id.id)
                ], order='sequence asc')
                previous_wos = all_wos.filtered(lambda w: w.sequence < workorder.sequence)

                if any(w.state not in ('done', 'cancel') for w in previous_wos):
                    if workorder.state == 'ready':
                        workorder.state = 'waiting'
                        logging.info(
                            "[SEQ ENFORCE] %s reverted to WAITING (earlier WO not done)",
                            workorder.name
                        )

    def button_restart(self):
        """Open wizard to select restart option"""
        self.ensure_one()
        
        view = self.env.ref('maeknit_mfg_customization.view_workorder_restart_wizard_form')
        return {
            'name': 'Restart Work Order',
            'type': 'ir.actions.act_window',
            'res_model': 'workorder.restart.wizard',
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
            'context': {
                'default_workorder_id': self.id,
            },
        }

        
    @api.model
    def get_program_attachments(self, workorder_id):
        """Get program file attachments for the work order"""
        workorder = self.browse(workorder_id)
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'mrp.workorder'),
            ('res_id', '=', workorder_id),
            ('attachment_type', '=', 'program')
        ])
        logging.info(f" Custom Code:  Found {len(attachments)} program attachments for workorder {workorder_id}")
        return attachments.ids
    
    def get_program_attachments_list(self):
        """Get program file attachments as a list with id and name"""
        self.ensure_one()
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'mrp.workorder'),
            ('res_id', '=', self.id),
            ('attachment_type', '=', 'program')
        ])
        logging.info(f" Custom Code:  Found {len(attachments)} program attachments for workorder {self.id}: {[a.name for a in attachments]}")
        return [
            {"id": att.id, "name": att.name or f"attachment_{att.id}"}
            for att in attachments
        ]

    def get_instruction_attachments(self, workorder_id):
        """Get instruction file attachments for the work order"""
        workorder = self.browse(workorder_id)
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'mrp.workorder'),
            ('res_id', '=', workorder_id),
            ('attachment_type', '=', 'instruction')
        ])
        logging.info(f" Custom Code:  Found {len(attachments)} instruction attachments for workorder {workorder_id}")
        return attachments.ids
    
    def get_instruction_attachments_list(self):
        """Get instruction file attachments as a list with id and name"""
        self.ensure_one()
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'mrp.workorder'),
            ('res_id', '=', self.id),
            ('attachment_type', '=', 'instruction')
        ])
        logging.info(f" Custom Code:  Found {len(attachments)} instruction attachments for workorder {self.id}: {[a.name for a in attachments]}")
        return [
            {"id": att.id, "name": att.name or f"attachment_{att.id}"}
            for att in attachments
        ]

    def write(self, vals):
        """Override write to sync changes back to BOM Request Operation"""
        if "text_instruction_notes" in vals:
            vals["instruction_notes_last_updated"] = fields.Datetime.now()
        if "text_program_notes" in vals:
            vals["program_notes_last_updated"] = fields.Datetime.now()

        res = super(MrpWorkorder, self).write(vals)
        logging.info('[WRITE] ids=%s keys=%s', list(self.ids), list(vals.keys()))
        
        if 'employee_assigned_ids' in vals:
            for wo in self:
                # Find the BOM Request Operation linked to this workorder
                bom_req_op = self.env['maeknit.bom.request.operation'].search([
                    ('mo_workorder_id', '=', wo.id)
                ], limit=1)
                
                if bom_req_op:
                    # Only update if different to avoid infinite loops
                    if set(bom_req_op.employee_assigned_ids.ids) != set(wo.employee_assigned_ids.ids):
                        bom_req_op.with_context(skip_mo_sync=True).write({
                            'employee_assigned_ids': [(6, 0, wo.employee_assigned_ids.ids)]
                        })
                        logging.info(
                            "Synced employees from MO Workorder %s to BOM Request Operation %s",
                            wo.id, bom_req_op.id
                        )
            self.invalidate_recordset(['has_instruction_files', 'has_program_files'])
        
        if 'text_instruction_notes' in vals or 'text_program_notes' in vals:
            for wo in self:
                wo._sync_attachments_to_knit_workorder()
                        
        return res

    def _sync_attachments_to_knit_workorder(self):
        """
        Sync attachments and notes from Program workorder to Knit workorder.
        Works with or without version numbers (Program V1 → Knit V1, or Program → Knit).
        """
        for wo in self:
            # Only sync if this is a Program workorder
            if not wo.name or 'program' not in wo.name.lower():
                continue

            # Try to find matching Knit workorder
            knit_wo = None

            # Method 1: If name has version number (e.g., "Program V1"), match to "Knit V1"
            if 'V' in wo.name:
                try:
                    version_str = wo.name.split('V')[-1].strip()
                    version_num = int(version_str)
                    knit_wo_name = f"Knit V{version_num}"
                    knit_wo = self.env['mrp.workorder'].search([
                        ('production_id', '=', wo.production_id.id),
                        ('name', '=', knit_wo_name)
                    ], limit=1)
                    logging.info(f" Custom Code: [SYNC] Trying versioned match: {wo.name} → {knit_wo_name}")
                except (ValueError, IndexError):
                    pass

            # Method 2: If no version or not found, look for any workorder with "knit" in the name
            if not knit_wo:
                knit_wo = self.env['mrp.workorder'].search([
                    ('production_id', '=', wo.production_id.id),
                    ('name', 'ilike', 'knit')
                ], limit=1)
                if knit_wo:
                    logging.info(f" Custom Code: [SYNC] Trying non-versioned match: {wo.name} → {knit_wo.name}")

            if not knit_wo:
                logging.info(f" Custom Code: [SYNC] No corresponding Knit workorder found for {wo.name}")
                continue

            logging.info(f" Custom Code: [SYNC] Syncing attachments and notes from {wo.name} (ID: {wo.id}) to {knit_wo.name} (ID: {knit_wo.id})")
            
            # Sync program attachments
            program_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'mrp.workorder'),
                ('res_id', '=', wo.id),
                ('attachment_type', '=', 'program')
            ])
            
            # Get existing program attachments on Knit workorder
            existing_knit_program_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'mrp.workorder'),
                ('res_id', '=', knit_wo.id),
                ('attachment_type', '=', 'program')
            ])
            
            # Delete existing attachments on Knit workorder to avoid duplicates
            if existing_knit_program_attachments:
                existing_knit_program_attachments.unlink()
                logging.info(f" Custom Code: [SYNC] Deleted {len(existing_knit_program_attachments)} existing program attachments from {knit_wo.name}")
            
            # Copy program attachments to Knit workorder
            for attachment in program_attachments:
                self.env['ir.attachment'].create({
                    'name': attachment.name,
                    'datas': attachment.datas,
                    'res_model': 'mrp.workorder',
                    'res_id': knit_wo.id,
                    'attachment_type': 'program',
                    'mimetype': attachment.mimetype,
                })
            logging.info(f" Custom Code: [SYNC] Copied {len(program_attachments)} program attachments from {wo.name} to {knit_wo.name}")
            
            # Sync instruction attachments
            instruction_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'mrp.workorder'),
                ('res_id', '=', wo.id),
                ('attachment_type', '=', 'instruction')
            ])
            
            # Get existing instruction attachments on Knit workorder
            existing_knit_instruction_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'mrp.workorder'),
                ('res_id', '=', knit_wo.id),
                ('attachment_type', '=', 'instruction')
            ])
            
            # Delete existing attachments on Knit workorder to avoid duplicates
            if existing_knit_instruction_attachments:
                existing_knit_instruction_attachments.unlink()
                logging.info(f" Custom Code: [SYNC] Deleted {len(existing_knit_instruction_attachments)} existing instruction attachments from {knit_wo.name}")
            
            # Copy instruction attachments to Knit workorder
            for attachment in instruction_attachments:
                self.env['ir.attachment'].create({
                    'name': attachment.name,
                    'datas': attachment.datas,
                    'res_model': 'mrp.workorder',
                    'res_id': knit_wo.id,
                    'attachment_type': 'instruction',
                    'mimetype': attachment.mimetype,
                })
            logging.info(f" Custom Code: [SYNC] Copied {len(instruction_attachments)} instruction attachments from {wo.name} to {knit_wo.name}")
            
            # Sync text notes
            update_vals = {}
            if wo.text_program_notes:
                update_vals['text_program_notes'] = wo.text_program_notes
            if wo.text_instruction_notes:
                update_vals['text_instruction_notes'] = wo.text_instruction_notes
            
            if update_vals:
                knit_wo.write(update_vals)
                logging.info(f" Custom Code: [SYNC] Synced text notes from {wo.name} to {knit_wo.name}: {list(update_vals.keys())}")

    @api.depends('shopfloor_operation_id', 'shopfloor_operation_id.workcenter_tag_ids', 'production_id.company_id')
    def _compute_workcenter_domain(self):
        """
        Compute available workcenters based on the operation's workcenter tags.
        Filters workcenters that share at least one tag with the shopfloor operation.
        """
        Workcenter = self.env['mrp.workcenter']
        cache = {
            'filtered': {},
            'all_wcs': {},
        }
        try:
            for wo in self:
                company_id = wo.production_id.company_id.id or self.env.company.id
                tag_ids = wo.shopfloor_operation_id.workcenter_tag_ids.ids if wo.shopfloor_operation_id else []

                if tag_ids:
                    workcenters = wo._filter_workcenters_by_tags_and_gauge(
                        tag_ids,
                        wo.production_id.gauge_id,
                        company_id,
                        cache
                    )
                    if workcenters:
                        wo.workcenter_domain_ids = workcenters
                        continue
                # Fallback: show all workcenters for this company
                all_wcs = cache['all_wcs'].setdefault(
                    company_id,
                    Workcenter.search([('company_id', '=', company_id)], order='sequence,id')
                )
                wo.workcenter_domain_ids = all_wcs
        except Exception as e:
            logging.error("[WORKCENTER_DOMAIN] Error computing workcenter domain: %s", e)
            all_wcs_cache = cache['all_wcs']
            for wo in self:
                company_id = wo.production_id.company_id.id or self.env.company.id
                all_wcs = all_wcs_cache.setdefault(
                    company_id,
                    Workcenter.search([('company_id', '=', company_id)], order='sequence,id')
                )
                wo.workcenter_domain_ids = all_wcs

    def _filter_workcenters_by_tags_and_gauge(self, tag_ids, gauge_id, company_id, cache):
        """Return workcenters that share at least one tag with the operation, with optional gauge filter for Knit/Link ops."""
        Workcenter = self.env['mrp.workcenter']

        cache_key_base = (company_id, tuple(sorted(tag_ids)))
        filtered_cache = cache.setdefault('filtered', {})

        domain = [('company_id', '=', company_id), ('tag_ids', 'in', tag_ids)]

        # Apply gauge filter when any of the operation's tags relate to knitting or linking
        knit_link_tag_names = {'knitting machine', 'linking machine'}
        op_tags = self.env['mrp.workcenter.tag'].browse(tag_ids)
        use_gauge_filter = any(t.name.lower() in knit_link_tag_names for t in op_tags)

        if use_gauge_filter and gauge_id:
            gauge_key = ('gauge',) + cache_key_base + (gauge_id.id,)
            workcenters = filtered_cache.get(gauge_key)
            if workcenters is None:
                workcenters = Workcenter.search(domain + [('gauge_ids', 'in', [gauge_id.id])], order='sequence,id')
                filtered_cache[gauge_key] = workcenters
            if workcenters:
                return workcenters

        tag_key = ('tag',) + cache_key_base
        workcenters = filtered_cache.get(tag_key)
        if workcenters is None:
            workcenters = Workcenter.search(domain, order='sequence,id')
            filtered_cache[tag_key] = workcenters
        return workcenters
