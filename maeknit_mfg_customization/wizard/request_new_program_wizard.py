from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import html_escape
import logging

REPROGRAM_NOTE_SUBJECT = 'Reprogram request note'

class RequestNewProgramWizard(models.TransientModel):
    _name = 'request.new.program.wizard'
    _description = 'Request New Program Wizard'

    workorder_id = fields.Many2one(
        'mrp.workorder',
        string='Knit Work Order',
        required=True,
        readonly=True,
    )
    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        related='workorder_id.production_id',
        readonly=True,
    )
    program_workorder_id = fields.Many2one(
        'mrp.workorder',
        string='Program Work Order',
        compute='_compute_program_workorder_id',
        store=False,
        readonly=True,
    )
    issue_type = fields.Selection([
        ('drop_stitch', 'Drop stitch'),
        ('takedown_measurements', 'Takedown measurements'),
        ('wrong_carrier', 'Wrong carrier'),
        ('other', 'Other'),
    ], string='Issue Type', required=True, default='drop_stitch')
    description = fields.Text(string='Description', help='Describe the issue for the programmer')
    sketch_data = fields.Text(string='Sketch', help='Optional Excalidraw sketch to illustrate the issue')
    sketch_preview = fields.Binary(string='Sketch Preview', attachment=True, help='PNG preview of the sketch')

    @api.depends('workorder_id')
    def _compute_program_workorder_id(self):
        """Find the Program workorder that corresponds to this Knit workorder."""
        for wizard in self:
            program_wo = False
            if wizard.workorder_id and wizard.workorder_id.name:
                # Extract version number from Knit workorder name (e.g., "Knit V1" -> 1)
                knit_name = wizard.workorder_id.name
                if 'knit' in knit_name.lower() and 'v' in knit_name.lower():
                    try:
                        version_str = knit_name.lower().split('v')[-1].strip()
                        version_num = int(version_str)
                        # Find corresponding Program workorder
                        program_wo = self.env['mrp.workorder'].search([
                            ('production_id', '=', wizard.workorder_id.production_id.id),
                            ('name', '=ilike', f'Program V{version_num}'),
                        ], limit=1)
                    except (ValueError, IndexError):
                        logging.warning("Could not parse version from Knit workorder name: %s", knit_name)

                # Fallback: find any Program workorder if no version match
                if not program_wo:
                    program_wo = self.env['mrp.workorder'].search([
                        ('production_id', '=', wizard.workorder_id.production_id.id),
                        ('name', '=ilike', 'Program%'),
                    ], order='sequence desc', limit=1)

            wizard.program_workorder_id = program_wo

    def action_submit(self):
        """Create a Quality Alert and reset the Program workorder to Ready."""
        self.ensure_one()

        if not self.program_workorder_id:
            raise UserError(_("No Program workorder found for this Manufacturing Order."))

        # Get the "Machine Programmers" quality alert team
        QualityAlertTeam = self.env['quality.alert.team']
        team = QualityAlertTeam.search([('name', 'ilike', 'Machine Programmers')], limit=1)
        if not team:
            # Fallback to any team
            team = QualityAlertTeam.search([], limit=1)
        if not team:
            raise UserError(_("No Quality Alert Team found. Please configure a Quality Alert Team first."))

        # Find the "New" stage explicitly by name
        QualityAlertStage = self.env['quality.alert.stage']
        new_stage = QualityAlertStage.search([('name', 'ilike', 'New')], order='sequence', limit=1)
        if not new_stage:
            # Fallback to first stage by sequence
            new_stage = QualityAlertStage.search([], order='sequence', limit=1)

        # Build the issue type label for display
        issue_type_labels = dict(self._fields['issue_type'].selection)
        issue_label = issue_type_labels.get(self.issue_type, self.issue_type)

        # Create the Quality Alert
        QualityAlert = self.env['quality.alert']
        description = (
            f"<p><strong>Issue Type:</strong> {issue_label}</p>"
            f"<p><strong>Description:</strong> {self.description or 'N/A'}</p>"
        )
        if self.sketch_data:
            description += "<p><strong>Sketch:</strong> (see attachment)</p>"
        alert_vals = {
            'title': f"Re-program Request: {issue_label}",
            'description': description,
            'team_id': team.id,
            'company_id': self.env.company.id,
            'user_id': self.env.user.id,
        }
        if new_stage:
            alert_vals['stage_id'] = new_stage.id

        # Add MRP-related fields only if they exist on the model (from mrp_workorder module)
        if 'production_id' in QualityAlert._fields:
            alert_vals['production_id'] = self.production_id.id
        else:
            logging.warning("[REPROGRAM] production_id field not found on quality.alert - is quality_mrp installed?")

        if 'workorder_id' in QualityAlert._fields:
            alert_vals['workorder_id'] = self.workorder_id.id
        else:
            logging.warning("[REPROGRAM] workorder_id field not found on quality.alert - is mrp_workorder installed?")

        if 'program_workorder_id' in QualityAlert._fields:
            alert_vals['program_workorder_id'] = self.program_workorder_id.id
        else:
            logging.warning("[REPROGRAM] program_workorder_id field not found on quality.alert - run module upgrade!")

        logging.info(" Custom Code:[REPROGRAM] Creating Quality Alert with values: %s", alert_vals)

        try:
            alert = QualityAlert.create(alert_vals)
            logging.info(
                "[REPROGRAM] Successfully created Quality Alert %s (ID: %s) for MO %s",
                alert.name, alert.id, self.production_id.name
            )
        except Exception as e:
            logging.error("[REPROGRAM] Failed to create Quality Alert: %s", str(e))
            raise UserError(_("Failed to create Quality Alert: %s") % str(e))

        # Attach sketch data to the Quality Alert if provided
        if self.sketch_data:
            import base64
            sketch_bytes = self.sketch_data.encode('utf-8')
            self.env['ir.attachment'].create({
                'name': 'issue_sketch.json',
                'datas': base64.b64encode(sketch_bytes).decode('utf-8'),
                'res_model': 'quality.alert',
                'res_id': alert.id,
                'mimetype': 'application/json',
            })
            logging.info("[REPROGRAM] Attached sketch data to Quality Alert %s", alert.id)

        # Stop the timer on the Knit workorder and set it to pending (blocked)
        knit_wo = self.workorder_id
        if knit_wo.state == 'progress':
            # Stop the timer by calling button_pending
            knit_wo.button_pending()
            logging.info(" Custom Code:[REPROGRAM] Stopped timer on Knit WO %s", knit_wo.name)

        # Set Knit workorder to 'pending' state (blocked by Program)
        knit_wo.write({'state': 'pending'})
        logging.info(" Custom Code:[REPROGRAM] Set Knit WO %s to Pending (blocked by Program)", knit_wo.name)

        # Reset the Program workorder to 'ready' state
        if self.program_workorder_id.state in ('done', 'cancel'):
            # Reopen the MO if needed
            mo = self.production_id
            if mo.state == 'done':
                logging.info(" Custom Code:[REPROGRAM] Reopening MO %s to reset Program workorder", mo.name)
                mo.button_unplan()
                mo.write({
                    'state': 'progress',
                    'is_locked': False,
                    'date_finished': False,
                })

            self.program_workorder_id.write({'state': 'ready'})
            logging.info(" Custom Code:[REPROGRAM] Reset Program WO %s to Ready state", self.program_workorder_id.name)
        elif self.program_workorder_id.state == 'waiting':
            self.program_workorder_id.write({'state': 'ready'})
            logging.info(" Custom Code:[REPROGRAM] Set Program WO %s to Ready state (was waiting)", self.program_workorder_id.name)

        # Create sketch attachment first so its URL can be used in both notes and chatter
        sketch_attachment = None
        if self.sketch_preview:
            sketch_b64 = self.sketch_preview.decode('utf-8') if isinstance(self.sketch_preview, bytes) else self.sketch_preview
            sketch_attachment = self.env['ir.attachment'].create({
                'name': 'issue_sketch.png',
                'datas': sketch_b64,
                'res_model': 'mrp.workorder',
                'res_id': self.program_workorder_id.id,
                'mimetype': 'image/png',
            })
            logging.info("[REPROGRAM] Created sketch attachment %s for Program WO", sketch_attachment.id)

        # Add plain-text entry to text_program_notes (Notes History)
        note_text = f"[Re-program Request - {fields.Datetime.now()}]\nIssue: {issue_label}\n{self.description or ''}"
        existing_notes = self.program_workorder_id.text_program_notes or ''
        new_notes = f"{note_text}\n\n---\n\n{existing_notes}" if existing_notes else note_text
        self.program_workorder_id.write({'text_program_notes': new_notes})

        # Log a reprogram note mentioning Kadri (chatter)
        kadri_user = self.env['res.users'].search([('name', 'ilike', 'kadri')], limit=1)
        if kadri_user:
            mention_html = (
                f'<a href="#" data-oe-model="res.users" data-oe-id="{kadri_user.id}">@{html_escape(kadri_user.name)}</a>'
            )
        else:
            mention_html = '@kadri'

        description_html = html_escape(self.description or '').replace('\n', '<br/>')
        note_parts = [
            f'<p>{_("From")} <strong>{html_escape(self.env.user.name)}</strong> {_("to")} {mention_html}</p>',
            f'<p><strong>{_("Issue Type")}:</strong> {html_escape(issue_label)}</p>',
        ]
        if description_html:
            note_parts.append(f'<p>{description_html}</p>')
        if sketch_attachment:
            note_parts.append(
                f'<p><strong>{_("Sketch")}:</strong><br/>'
                f'<img src="/web/content/{sketch_attachment.id}" '
                f'style="max-width:100%;border:1px solid #dee2e6;border-radius:4px;margin-top:4px;" /></p>'
            )

        MailMessage = self.env['mail.message']
        mt_note = self.env.ref('mail.mt_note', raise_if_not_found=False)
        common_vals = {
            'body': ''.join(note_parts),
            'subject': REPROGRAM_NOTE_SUBJECT,
            'message_type': 'comment',
        }
        if mt_note:
            common_vals['subtype_id'] = mt_note.id

        message_vals = {
            **common_vals,
            'model': 'mrp.workorder',
            'res_id': self.program_workorder_id.id,
        }
        if sketch_attachment:
            message_vals['attachment_ids'] = [(4, sketch_attachment.id)]
        reprogram_msg = MailMessage.create(message_vals)

        # Store the reprogram note reference on the program workorder
        self.program_workorder_id.write({
            'has_reprogram_request': True,
            'latest_reprogram_message_id': reprogram_msg.id,
        })

        if self.production_id:
            production_vals = {
                **common_vals,
                'model': 'mrp.production',
                'res_id': self.production_id.id,
            }
            if sketch_attachment:
                production_vals['attachment_ids'] = [(4, sketch_attachment.id)]
            MailMessage.create(production_vals)

        # Reset subsequent workorders to waiting if needed (except the Knit WO which is already pending)
        later_wos = self.env['mrp.workorder'].search([
            ('production_id', '=', self.production_id.id),
            ('sequence', '>', self.program_workorder_id.sequence),
            ('state', 'in', ('ready', 'progress')),
            ('id', '!=', self.workorder_id.id),  # Exclude the Knit WO (already set to pending)
        ])
        if later_wos:
            later_wos.write({'state': 'waiting'})
            logging.info(" Custom Code:[REPROGRAM] Reset %d subsequent workorders to waiting", len(later_wos))

        return {'type': 'ir.actions.act_window_close'}
