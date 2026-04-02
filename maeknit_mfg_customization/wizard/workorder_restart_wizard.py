from odoo import models, fields, api, _
from odoo.tools import html_escape
import logging

class WorkorderRestartWizard(models.TransientModel):
    _name = 'workorder.restart.wizard'
    _description = 'Work Order Restart Wizard'

    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', required=False)
    restart_option = fields.Selection([
        ('knitting', 'Restart from Knitting'),
        ('current', 'Restart from Current Operation')
    ], string='Restart Option', required=False, default='current')

    # Fields for MO-level Re-manufacturing wizard
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order')
    restart_workorder_id = fields.Many2one(
        'mrp.workorder',
        string='Restart From',
        domain="[('production_id', '=', production_id), ('state', '!=', 'cancel')]",
    )
    is_program_selected = fields.Boolean(
        compute='_compute_is_program_selected',
        store=False,
    )

    # Extra fields shown when a Program WO is selected
    issue_type = fields.Selection([
        ('drop_stitch', 'Drop stitch'),
        ('takedown_measurements', 'Takedown measurements'),
        ('wrong_carrier', 'Wrong carrier'),
        ('other', 'Other'),
    ], string='Issue', default='drop_stitch')
    description = fields.Text(string='Description')
    sketch_data = fields.Text(string='Sketch')
    sketch_preview = fields.Binary(string='Sketch Preview', attachment=True)
    swatch_mo_id = fields.Many2one(
        'mrp.production',
        string='Swatch',
    )

    @api.depends('restart_workorder_id', 'restart_workorder_id.name')
    def _compute_is_program_selected(self):
        for rec in self:
            name = (rec.restart_workorder_id.name or '').lower()
            rec.is_program_selected = 'program' in name

    def action_restart_workorder(self):
        """Restart work order based on selected option"""
        self.ensure_one()
        wo = self.workorder_id
        mo = wo.production_id

        try:
            # Step 1: reopen MO if it was finished
            if mo.state == 'done':
                logging.info(" Custom Code:[RESTART] Unplanning MO %s before restarting WOs", mo.name)
                mo.button_unplan()
                mo.write({
                    'state': 'progress',
                    'is_locked': False,
                    'date_finished': False,
                })

            # Step 2: handle restart logic by option
            if self.restart_option == 'programming':
                # Create next Program + Knit version
                mo.button_request_new_program()

                # Identify the newest Program/Knit workorders just created
                latest_created = mo.workorder_ids.sorted('sequence')[-2:]
                if latest_created:
                    base_seq = min(latest_created.mapped('sequence'))
                else:
                    base_seq = max(mo.workorder_ids.mapped('sequence') or [0])

                # Set every workorder *after* them to waiting (including finished)
                later_wos = mo.workorder_ids.filtered(lambda w: w.sequence > base_seq)
                later_wos.write({'state': 'waiting'})
                wo.button_done()

            elif self.restart_option == 'knitting':
                mo.button_request_new_knit_only()

                latest_created = mo.workorder_ids.sorted('sequence')[-1:]
                if latest_created:
                    base_seq = min(latest_created.mapped('sequence'))
                else:
                    base_seq = max(mo.workorder_ids.mapped('sequence') or [0])

                # Set every workorder *after* them to waiting (including finished)
                later_wos = mo.workorder_ids.filtered(lambda w: w.sequence > base_seq)
                later_wos.write({'state': 'waiting'})
                wo.button_done()
            else:  # Restart current
                wo.write({'state': 'ready'})
                later_wos = mo.workorder_ids.filtered(lambda w: w.sequence > wo.sequence)
                later_wos.write({'state': 'waiting'})

        except Exception as e:
            logging.error("[RESTART] Failed to restart WO %s: %s", wo.name, e)

        return {'type': 'ir.actions.act_window_close'}

    def action_remanufacture(self):
        """Restart MO from the user-selected work order."""
        self.ensure_one()
        mo = self.production_id
        wo = self.restart_workorder_id

        if not wo:
            return {'type': 'ir.actions.act_window_close'}

        try:
            if mo.state == 'done':
                logging.info("[REMANUFACTURE] Unplanning MO %s before restarting", mo.name)
                mo.button_unplan()
                mo.write({
                    'state': 'progress',
                    'is_locked': False,
                    'date_finished': False,
                })

            wo.write({'state': 'ready'})
            later_wos = mo.workorder_ids.filtered(lambda w: w.sequence > wo.sequence)
            later_wos.write({'state': 'waiting'})
            logging.info("[REMANUFACTURE] Restarted MO %s from WO %s", mo.name, wo.name)

            if self.is_program_selected:
                self._handle_program_remanufacture()

        except Exception as e:
            logging.error("[REMANUFACTURE] Failed for MO %s: %s", mo.name, e)

        return {'type': 'ir.actions.act_window_close'}

    def _handle_program_remanufacture(self):
        """Create Quality Alert and log chatter when Program WO is selected in Re-manufacturing."""
        issue_labels = dict(self._fields['issue_type'].selection)
        issue_label = issue_labels.get(self.issue_type, self.issue_type or 'N/A')

        team = self.env['quality.alert.team'].search([('name', 'ilike', 'Machine Programmers')], limit=1)
        if not team:
            team = self.env['quality.alert.team'].search([], limit=1)
        new_stage = self.env['quality.alert.stage'].search([('name', 'ilike', 'New')], order='sequence', limit=1)

        alert_vals = {
            'title': f"Re-manufacturing Program Issue: {issue_label}",
            'description': (
                f"<p><strong>Issue:</strong> {issue_label}</p>"
                f"<p><strong>Description:</strong> {self.description or 'N/A'}</p>"
                + (f"<p><strong>Swatch:</strong> {self.swatch_mo_id.name}</p>" if self.swatch_mo_id else '')
            ),
            'team_id': team.id if team else False,
            'company_id': self.env.company.id,
            'user_id': self.env.user.id,
        }
        if new_stage:
            alert_vals['stage_id'] = new_stage.id
        QA = self.env['quality.alert']
        if 'production_id' in QA._fields:
            alert_vals['production_id'] = self.production_id.id
        try:
            QA.create(alert_vals)
        except Exception as e:
            logging.error("[REMANUFACTURE] Failed to create Quality Alert: %s", e)

        # Create sketch attachment first so its URL can be used in both notes and chatter
        sketch_attachment = None
        if self.sketch_preview:
            sketch_b64 = self.sketch_preview.decode('utf-8') if isinstance(self.sketch_preview, bytes) else self.sketch_preview
            sketch_attachment = self.env['ir.attachment'].create({
                'name': 'remanufacture_sketch.png',
                'datas': sketch_b64,
                'res_model': 'mrp.workorder',
                'res_id': self.restart_workorder_id.id,
                'mimetype': 'image/png',
            })

        # Add plain-text entry to text_program_notes (Notes History)
        note_text = f"[Re-manufacturing - {fields.Datetime.now()}]\nIssue: {issue_label}\n{self.description or ''}"
        existing_notes = self.restart_workorder_id.text_program_notes or ''
        new_notes = f"{note_text}\n\n---\n\n{existing_notes}" if existing_notes else note_text
        self.restart_workorder_id.write({'text_program_notes': new_notes})

        # Build note parts for chatter
        kadri_user = self.env['res.users'].search([('name', 'ilike', 'kadri')], limit=1)
        mention_html = (
            f'<a href="#" data-oe-model="res.users" data-oe-id="{kadri_user.id}">@{html_escape(kadri_user.name)}</a>'
            if kadri_user else '@kadri'
        )
        description_html = html_escape(self.description or '').replace('\n', '<br/>')
        swatch_html = f'<p><strong>Swatch:</strong> {html_escape(self.swatch_mo_id.name)}</p>' if self.swatch_mo_id else ''

        note_parts = [
            f'<p>{_("From")} <strong>{html_escape(self.env.user.name)}</strong> {_("to")} {mention_html}</p>',
            f'<p><strong>{_("Issue Type")}:</strong> {html_escape(issue_label)}</p>',
        ]
        if description_html:
            note_parts.append(f'<p>{description_html}</p>')
        if swatch_html:
            note_parts.append(swatch_html)
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
            'subject': 'Reprogram request note',
            'message_type': 'comment',
        }
        if mt_note:
            common_vals['subtype_id'] = mt_note.id

        # Post note on the Program WO chatter and store reference (shows info button)
        wo_msg_vals = {
            **common_vals,
            'model': 'mrp.workorder',
            'res_id': self.restart_workorder_id.id,
        }
        if sketch_attachment:
            wo_msg_vals['attachment_ids'] = [(4, sketch_attachment.id)]
        program_wo_msg = MailMessage.create(wo_msg_vals)
        self.restart_workorder_id.write({
            'has_reprogram_request': True,
            'latest_reprogram_message_id': program_wo_msg.id,
        })

        # Also post to MO chatter
        mo_msg_vals = {
            **common_vals,
            'model': 'mrp.production',
            'res_id': self.production_id.id,
        }
        if sketch_attachment:
            mo_msg_vals['attachment_ids'] = [(4, sketch_attachment.id)]
        MailMessage.create(mo_msg_vals)

