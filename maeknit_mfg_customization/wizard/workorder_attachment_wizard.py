from odoo import models, fields, api
from markupsafe import Markup
import logging
import base64

class WorkorderAttachmentWizard(models.TransientModel):
    _name = 'workorder.attachment.wizard'
    _description = 'Workorder Attachment Wizard'

    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', required=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    attachment_type = fields.Selection([
        ('instruction', 'Instruction Files'),
        ('program', 'Program Files')
    ], string='Attachment Type', required=True, default='instruction')

    # Note fields
    text_content = fields.Text(
        string='Notes',
        help='Enter or edit notes for this work order',
        default=lambda self: self._default_text_content()
    )

    reprogram_notes_html = fields.Html(
        string='Reprogram Notes',
        compute='_compute_reprogram_notes_html',
        store=False,
        sanitize=False,
    )

    issue_type = fields.Selection([
        ('reprogram', 'Re-program Request'),
        ('update', 'Update'),
        ('other', 'Other'),
    ], string='Issue Type', help='Select the type of issue or note')

    quick_note_text = fields.Text(string='Quick Note', help='Enter a new note to add with timestamp')

    has_notes = fields.Boolean(string='Has Notes', compute='_compute_has_notes', store=False)


    include_text = fields.Boolean(string='Include Text', default=False)

    wash_library_id = fields.Many2one(
        'wash.library',
        string='Wash',
        help='Select wash type from the Wash Library',
        default=lambda self: self._default_wash_library_id(),
    )

    def _default_wash_library_id(self):
        workorder_id = self.env.context.get('default_workorder_id')
        if workorder_id:
            workorder = self.env['mrp.workorder'].browse(workorder_id)
            return workorder.wash_library_id
        return False
    is_wash_workorder = fields.Boolean(
        compute='_compute_is_wash_workorder',
        store=False,
    )

    @api.depends('workorder_id')
    def _compute_is_wash_workorder(self):
        for wizard in self:
            wizard.is_wash_workorder = bool(
                wizard.workorder_id and wizard.workorder_id.is_wash_workorder
            )

    dry_library_id = fields.Many2one(
        'dry.library',
        string='Dry',
        help='Select dry type from the Dry Library',
        default=lambda self: self._default_dry_library_id(),
    )

    def _default_dry_library_id(self):
        workorder_id = self.env.context.get('default_workorder_id')
        if workorder_id:
            workorder = self.env['mrp.workorder'].browse(workorder_id)
            return workorder.dry_library_id
        return False

    is_dry_workorder = fields.Boolean(
        compute='_compute_is_dry_workorder',
        store=False,
    )

    @api.depends('workorder_id')
    def _compute_is_dry_workorder(self):
        for wizard in self:
            wizard.is_dry_workorder = bool(
                wizard.workorder_id and wizard.workorder_id.is_dry_workorder
            )

    existing_attachment_display_ids = fields.One2many(
        'ir.attachment',
        compute='_compute_existing_attachment_display',
        string='Existing Files'
    )
    
    existing_attachment_ids = fields.Many2many(
        'ir.attachment', 
        'ir_attachment_workorder_attachment_wizard_rel',
        'workorder_attachment_wizard_id', 
        'ir_attachment_id',
        string=' ',
        compute='_compute_existing_attachments',
        inverse='_inverse_existing_attachments',
        store=False
    )
    
    @api.depends('workorder_id', 'attachment_type')
    def _compute_existing_attachment_display(self):
        """Compute existing attachments for display with timestamps"""
        for wizard in self:
            if wizard.workorder_id and wizard.attachment_type:
                domain = [
                    ('res_model', '=', 'mrp.workorder'),
                    ('res_id', '=', wizard.workorder_id.id),
                    ('attachment_type', '=', wizard.attachment_type)
                ]
                wizard.existing_attachment_display_ids = self.env['ir.attachment'].search(domain)
            else:
                wizard.existing_attachment_display_ids = False
    
    instruction_notes_last_updated = fields.Datetime(string='Instruction Notes Last Updated', compute='_compute_last_updated')
    program_notes_last_updated = fields.Datetime(string='Program Notes Last Updated', compute='_compute_last_updated')

    def _compute_last_updated(self):
        for wiz in self:
            if wiz.workorder_id:
                wiz.instruction_notes_last_updated = wiz.workorder_id.instruction_notes_last_updated
                wiz.program_notes_last_updated = wiz.workorder_id.program_notes_last_updated

    
    def _default_text_content(self):
        """Pre-fill based on attachment type"""
        workorder_id = self.env.context.get('default_workorder_id')
        attachment_type = self.env.context.get('default_attachment_type')
        if not workorder_id:
            return ''
        workorder = self.env['mrp.workorder'].browse(workorder_id)
        if attachment_type == 'program':
            return workorder.text_program_notes or ''
        return workorder.text_instruction_notes or ''

    @api.depends('text_content')
    def _compute_has_notes(self):
        """Check if notes exist to show badge on Notes tab"""
        for wizard in self:
            wizard.has_notes = bool(wizard.text_content and wizard.text_content.strip())

    @api.depends('workorder_id')
    def _compute_reprogram_notes_html(self):
        """Build HTML from reprogram mail.message bodies linked to this work order."""
        for wizard in self:
            if not wizard.workorder_id:
                wizard.reprogram_notes_html = False
                continue
            messages = self.env['mail.message'].search([
                ('model', '=', 'mrp.workorder'),
                ('res_id', '=', wizard.workorder_id.id),
                ('subject', '=', 'Reprogram request note'),
            ], order='date desc')
            if not messages:
                wizard.reprogram_notes_html = False
                continue
            parts = []
            for msg in messages:
                body = Markup(msg.body or '')
                date_str = str(msg.date)[:16]
                parts.append(
                    Markup('<div style="border-bottom:1px solid #dee2e6;padding-bottom:12px;margin-bottom:12px;">')
                    + body
                    + Markup(f'<p style="color:#888;font-size:11px;margin-top:6px;">{date_str}</p></div>')
                )
            wizard.reprogram_notes_html = Markup('').join(parts)

    @api.depends('workorder_id', 'attachment_type')
    def _compute_existing_attachments(self):
        """Compute existing attachments for this workorder and type"""
        for wizard in self:
            if wizard.workorder_id and wizard.attachment_type:
                domain = [
                    ('res_model', '=', 'mrp.workorder'),
                    ('res_id', '=', wizard.workorder_id.id),
                    ('attachment_type', '=', wizard.attachment_type)
                ]
                wizard.existing_attachment_ids = self.env['ir.attachment'].search(domain)
            else:
                wizard.existing_attachment_ids = False
    
    def _inverse_existing_attachments(self):
        """Handle deletion of attachments when removed from the many2many field"""
        for wizard in self:
            if wizard.workorder_id and wizard.attachment_type:
                # Get current attachments in database
                domain = [
                    ('res_model', '=', 'mrp.workorder'),
                    ('res_id', '=', wizard.workorder_id.id),
                    ('attachment_type', '=', wizard.attachment_type)
                ]
                current_attachments = self.env['ir.attachment'].search(domain)
                
                # Find attachments that were removed (in current but not in wizard field)
                removed_attachments = current_attachments - wizard.existing_attachment_ids
                
                # Delete removed attachments
                if removed_attachments:
                    logging.info(f"[WO_ATTACH] Deleting {len(removed_attachments)} attachment(s) from workorder {wizard.workorder_id.id}")
                    removed_attachments.unlink()

    def _reload_wizard(self):
        """Reload the wizard by creating a fresh instance to force chatter refresh"""
        # Create a new wizard instance to force the chatter widget to reload
        vals = {
            'workorder_id': self.workorder_id.id,
            'attachment_type': self.attachment_type,
        }
        if self.workorder_id.wash_library_id:
            vals['wash_library_id'] = self.workorder_id.wash_library_id.id
        if self.workorder_id.dry_library_id:
            vals['dry_library_id'] = self.workorder_id.dry_library_id.id
        new_wizard = self.env['workorder.attachment.wizard'].create(vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': new_wizard.id,
            'target': 'new',
            'context': self.env.context,
        }
    def action_add_attachments(self):
        """Add attachments and save notes directly to workorder"""
        self.ensure_one()

        # Flush any draft quick note so it isn't lost when the user clicks Save
        # without first clicking "Add Note".
        self._flush_quick_note()

        # Handle attachments
        file_names = []
        for attachment in self.attachment_ids:
            attachment.write({
                'res_model': 'mrp.workorder',
                'res_id': self.workorder_id.id,
                'name': attachment.name,
                'attachment_type': self.attachment_type,
            })
            file_names.append(attachment.name)

        # Store text in the correct field
        if self.attachment_type == 'program':
            self.workorder_id.text_program_notes = self.text_content
        else:
            self.workorder_id.text_instruction_notes = self.text_content

        # Save wash library selection if set
        if self.wash_library_id:
            self.workorder_id.wash_library_id = self.wash_library_id

        # Save dry library selection if set
        if self.dry_library_id:
            self.workorder_id.dry_library_id = self.dry_library_id

        # Post chatter message if files were uploaded
        if file_names:
            file_type = 'Program' if self.attachment_type == 'program' else 'Instruction'
            file_list = '<ul>' + ''.join(f'<li>{name}</li>' for name in file_names) + '</ul>'

            # Find users to notify: Kadri, Sevan, Mallory
            users_to_notify = self.env['res.users'].search([
                '|', '|',
                ('name', 'ilike', 'Kadri'),
                ('name', 'ilike', 'Sevan'),
                ('name', 'ilike', 'Mallory')
            ])
            partner_ids = users_to_notify.mapped('partner_id').ids
            logging.info(f"[WO_ATTACH] Found {len(users_to_notify)} users to notify: {users_to_notify.mapped('name')}")

            # Build message with @mentions
            mentions_html = ' '.join([
                f'<a href="#" data-oe-model="res.partner" data-oe-id="{partner.id}">@{partner.name}</a>'
                for partner in users_to_notify.mapped('partner_id')
            ])

            message_body = f"""
                <p><strong>{file_type} files uploaded by {self.env.user.name}</strong></p>
                {file_list}
                <p>{mentions_html}</p>
            """

            self.workorder_id.message_post(
                body=message_body,
                subject=f'{file_type} Files Uploaded',
                message_type='notification',
                subtype_xmlid='mail.mt_note',
                partner_ids=partner_ids,  # This triggers email notifications
            )
            logging.info(f"[WO_ATTACH] Posted chatter message for {len(file_names)} {file_type} file(s), notified {len(partner_ids)} users")

        # Sync attachments
        self.workorder_id._sync_attachments_to_knit_workorder()

        self.workorder_id._compute_attachment_counts()
        self.workorder_id._compute_has_files()

        return self._reload_wizard()

    def action_download_all_separate(self):
        """Download all files separately (one by one) - triggers sequential browser downloads"""
        self.ensure_one()

        # Get attachments for this workorder filtered by type
        domain = [
            ('res_model', '=', 'mrp.workorder'),
            ('res_id', '=', self.workorder_id.id),
            ('attachment_type', '=', self.attachment_type)
        ]

        attachments = self.env['ir.attachment'].search(domain)

        if not attachments:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Files',
                    'message': f'No {self.attachment_type} files found for this work order.',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        logging.info(f"[WO_ATTACH] Triggering sequential download for {len(attachments)} files")

        # Filter out attachments with no data (orphaned files)
        valid_attachments = attachments.filtered(lambda att: att.datas)

        if not valid_attachments:
            logging.warning(f"[WO_ATTACH] All attachments are orphaned (no data)")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Valid Files',
                    'message': f'All {self.attachment_type} files are missing data. Please delete and re-upload them.',
                    'type': 'warning',
                    'sticky': True,
                }
            }

        logging.info(f"[WO_ATTACH] Returning {len(valid_attachments)} files for sequential download")

        # Use existing download_attachments client action to trigger sequential downloads
        return {
            'type': 'ir.actions.client',
            'tag': 'download_attachments',
            'params': {
                'attachment_ids': valid_attachments.ids,
                'attachment_names': valid_attachments.mapped('name'),
            }
        }

    def action_download_all_zip(self):
        """Download all files as a ZIP archive"""
        self.ensure_one()
        import zipfile
        import io
        import base64

        logging.info(f"[WO_ATTACH] Starting ZIP download for workorder {self.workorder_id.name}")

        # Get attachments for this workorder filtered by type
        domain = [
            ('res_model', '=', 'mrp.workorder'),
            ('res_id', '=', self.workorder_id.id),
            ('attachment_type', '=', self.attachment_type)
        ]

        attachments = self.env['ir.attachment'].search(domain)
        logging.info(f"[WO_ATTACH] Found {len(attachments)} attachments to zip")

        if not attachments:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Files',
                    'message': f'No {self.attachment_type} files found for this work order.',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        try:
            # Create ZIP file in memory
            zip_buffer = io.BytesIO()
            files_added = 0

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for attachment in attachments:
                    logging.info(f"[WO_ATTACH] Processing attachment {attachment.id}: {attachment.name}")

                    # Check if attachment has data
                    if not attachment.datas:
                        logging.warning(f"[WO_ATTACH] Attachment {attachment.id} ({attachment.name}) has no data, skipping")
                        continue

                    try:
                        # Decode the base64 data
                        file_data = base64.b64decode(attachment.datas)
                        logging.info(f"[WO_ATTACH] Decoded {len(file_data)} bytes for {attachment.name}")

                        # Add to ZIP
                        zip_file.writestr(attachment.name or f'file_{attachment.id}', file_data)
                        files_added += 1
                        logging.info(f"[WO_ATTACH] Added {attachment.name} to ZIP")

                    except Exception as e:
                        logging.error(f"[WO_ATTACH] Failed to add {attachment.name} to ZIP: {e}", exc_info=True)
                        continue

            if files_added == 0:
                logging.error("[WO_ATTACH] No files were added to ZIP")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': 'No files could be added to the ZIP archive. Please check the log for details.',
                        'type': 'danger',
                        'sticky': True,
                    }
                }

            # Get ZIP data
            zip_buffer.seek(0)
            zip_data = zip_buffer.getvalue()
            logging.info(f"[WO_ATTACH] Created ZIP file with {len(zip_data)} bytes")

            # Encode to base64 for storage
            zip_b64 = base64.b64encode(zip_data)

            # Create temporary attachment
            zip_name = f"{self.workorder_id.name.replace('/', '-')}_{self.attachment_type}_files.zip"
            logging.info(f"[WO_ATTACH] Creating temporary attachment: {zip_name}")

            zip_attachment = self.env['ir.attachment'].create({
                'name': zip_name,
                'datas': zip_b64,
                'type': 'binary',
                'mimetype': 'application/zip',
                'public': False,
                'res_model': 'workorder.attachment.wizard',
                'res_id': 0,  # Temporary, not linked to specific record
            })

            logging.info(f"[WO_ATTACH] Created ZIP attachment with ID {zip_attachment.id}")

            # Return download URL
            download_url = f'/web/content/{zip_attachment.id}?download=true'
            logging.info(f"[WO_ATTACH] Returning download URL: {download_url}")

            return {
                'type': 'ir.actions.act_url',
                'url': download_url,
                'target': 'self',
            }

        except Exception as e:
            logging.error(f"[WO_ATTACH] Error creating ZIP: {e}", exc_info=True)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Failed to create ZIP archive: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_delete_attachment(self, attachment_id):
        """Delete a specific attachment"""
        self.ensure_one()
        attachment = self.env['ir.attachment'].browse(attachment_id)
        if attachment.exists():
            attachment_name = attachment.name
            attachment.unlink()
            self.workorder_id._compute_attachment_counts()
            self.workorder_id._compute_has_files()
        return self._reload_wizard()

    def _flush_quick_note(self):
        """If a draft quick note exists, format and commit it to text_content.

        Returns True if a note was flushed, False otherwise.  Callers are
        responsible for persisting text_content to the workorder afterwards.
        """
        self.ensure_one()
        if not self.quick_note_text or not self.quick_note_text.strip():
            return False

        timestamp = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user_name = self.env.user.name
        note_text = self.quick_note_text.strip()
        current_issue_type = self.issue_type

        if current_issue_type:
            issue_label = dict(self._fields['issue_type'].selection).get(current_issue_type, 'Note')
            note_header = f"[{issue_label} - {timestamp}]"
        else:
            issue_label = 'Note'
            note_header = f"[Note - {timestamp}]"

        new_note = f"{note_header}\nBy: {user_name}\n{note_text}\n\n"
        updated_notes = new_note + (self.text_content or '')

        self.write({
            'text_content': updated_notes,
            'quick_note_text': False,
            'issue_type': False,
        })

        # Post to chatter
        users_to_notify = self.env['res.users'].search([
            '|', '|',
            ('name', 'ilike', 'Kadri'),
            ('name', 'ilike', 'Sevan'),
            ('name', 'ilike', 'Mallory')
        ])
        partner_ids = users_to_notify.mapped('partner_id').ids
        mentions_html = ' '.join([
            f'<a href="#" data-oe-model="res.partner" data-oe-id="{partner.id}">@{partner.name}</a>'
            for partner in users_to_notify.mapped('partner_id')
        ])
        attachment_label = 'Program' if self.attachment_type == 'program' else 'Instruction'
        message_body = f"""
            <p>{note_text}</p>
            <p><em>From: {user_name} — {timestamp}</em></p>
            <p>{mentions_html}</p>
        """
        self.workorder_id.message_post(
            body=message_body,
            subject=f'{attachment_label} Note: {issue_label}',
            message_type='notification',
            subtype_xmlid='mail.mt_note',
            partner_ids=partner_ids,
        )
        logging.info(f"[WO_ATTACH] Flushed draft note to chatter for WO {self.workorder_id.name}, notified {len(partner_ids)} users")
        return True

    def action_add_quick_note(self):
        """Add a timestamped note to the existing notes"""
        self.ensure_one()

        if not self._flush_quick_note():
            return False

        # Persist to the workorder so notes survive when the dialog is reopened
        if self.attachment_type == 'program':
            self.workorder_id.text_program_notes = self.text_content
        else:
            self.workorder_id.text_instruction_notes = self.text_content

        # Reload the wizard so the dialog refreshes with the updated notes.
        return self._reload_wizard()

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def action_download_file(self):
        """Download this specific file"""
        self.ensure_one()

        logging.info(f"[WO_ATTACH] Download request for attachment {self.id}: {self.name}")

        # Check if attachment has data
        if not self.datas:
            logging.warning(f"[WO_ATTACH] Attachment {self.id} has no data")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'File "{self.name}" has no data to download.',
                    'type': 'warning',
                }
            }

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        download_url = f'/web/content/{self.id}?download=true'
        logging.info(f"[WO_ATTACH] Download URL: {base_url}{download_url}")

        return {
            'type': 'ir.actions.act_url',
            'url': download_url,
            'target': 'self',
        }

    def action_rename_file(self):
        """Open wizard to rename this file"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Rename File',
            'res_model': 'ir.attachment',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('maeknit_mfg_customization.view_attachment_rename_form').id,
            'target': 'new',
            'context': {
                'default_editable_name': self.name,
                'from_workorder_wizard': True,
            }
        }

    def action_delete_file(self):
        """Delete this attachment and reload the wizard view"""
        self.ensure_one()
        attachment_name = self.name
        workorder = self.env['mrp.workorder'].browse(self.res_id) if self.res_model == 'mrp.workorder' else None
        attachment_type = self.attachment_type if hasattr(self, 'attachment_type') else None
        
        # Store context before deletion
        wizard_context = dict(self.env.context)
        if workorder:
            wizard_context.update({
                'default_workorder_id': workorder.id,
                'default_attachment_type': attachment_type or 'instruction',
            })
        
        self.unlink()
        
        if workorder and workorder.exists():
            workorder._compute_attachment_counts()
            workorder._compute_has_files()
            wizard = self.env['workorder.attachment.wizard'].create({
                'workorder_id': workorder.id,
                'attachment_type': attachment_type or 'instruction',
            })

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'workorder.attachment.wizard',
                'view_mode': 'form',
                'res_id': wizard.id,
                'target': 'new',
                'context': wizard_context,
            }

        return {'type': 'ir.actions.act_window_close'}
