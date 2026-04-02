from odoo import models, fields, api
import logging

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    attachment_type = fields.Selection([
        ('program', 'Program File'),
        ('instruction', 'Instruction File'),
        ('client', 'Client File'),
        ('general', 'General Attachment'),
        ('sketch', 'Sketch Image'),
    ], string='Attachment Type', default='general', help='Type of attachment for categorization')

    editable_name = fields.Char(string='File Name', related='name', readonly=False, store=False)

    display_name_with_date = fields.Char(
        string='File Name with Date',
        compute='_compute_display_name_with_date',
        store=False
    )

    @api.depends('name', 'write_date')
    def _compute_display_name_with_date(self):
        for attachment in self:
            if attachment.write_date:
                date_str = fields.Datetime.context_timestamp(
                    attachment, attachment.write_date
                ).strftime('%Y-%m-%d %H:%M:%S')
                attachment.display_name_with_date = f"{attachment.name} - Last updated: {date_str}"
            else:
                attachment.display_name_with_date = attachment.name

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to trigger workorder recomputation when attachments are added"""
        attachments = super().create(vals_list)
        self._trigger_workorder_recompute(attachments)
        return attachments

    def write(self, vals):
        """Override write to trigger workorder recomputation when attachment_type changes"""
        result = super().write(vals)
        if 'attachment_type' in vals:
            self._trigger_workorder_recompute(self)
        return result

    def unlink(self):
        """Override unlink to trigger workorder recomputation when attachments are deleted"""
        # Store workorder info before deletion
        workorders_to_update = self._get_related_workorders()
        result = super().unlink()
        # Trigger recomputation after deletion
        if workorders_to_update:
            workorders_to_update._compute_attachment_counts()
        return result

    def _get_related_workorders(self):
        """Get workorders related to these attachments"""
        workorders = self.env['mrp.workorder'].browse()
        for attachment in self:
            if attachment.res_model == 'mrp.workorder' and attachment.res_id:
                workorders |= self.env['mrp.workorder'].browse(attachment.res_id)
        return workorders

    def _trigger_workorder_recompute(self, attachments):
        """Trigger recomputation of attachment counts for related workorders"""
        workorders = attachments._get_related_workorders()
        logging.info(f" Custom Code: [IR.ATTACHMENT] Trigger recompute for {len(workorders)} workorders: {[wo.name for wo in workorders]}")
        if workorders:
            logging.info(f" Custom Code: [IR.ATTACHMENT] Computing attachment counts...")
            workorders._compute_attachment_counts()
            # Invalidate cache to force recomputation of dependent fields
            logging.info(f" Custom Code: [IR.ATTACHMENT] Invalidating cache for has_files fields...")
            workorders.invalidate_recordset(['program_attachment_count', 'instruction_attachment_count', 'has_program_files', 'has_instruction_files'])
            # Explicitly recompute the has_files fields
            logging.info(f" Custom Code: [IR.ATTACHMENT] Recomputing has_files fields...")
            workorders._compute_has_files()
            logging.info(f" Custom Code: [IR.ATTACHMENT] Recompute complete!")
