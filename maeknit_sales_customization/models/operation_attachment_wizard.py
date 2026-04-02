from odoo import models, fields, api

class OperationAttachmentWizard(models.TransientModel):
    _name = 'operation.attachment.wizard'
    _description = 'Operation Attachment Wizard'

    bom_request_id = fields.Many2one('maeknit.bom.request', string='BOM Request', required=True)
    operation_id = fields.Many2one('maeknit.bom.request.operation', string='Operation')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    attachment_type = fields.Selection([
        ('instruction', 'Instruction Files'),
        ('program', 'Program Files')
    ], string='Attachment Type', required=True, default='instruction')
    
    text_content = fields.Text(string='Text Content', help='Enter text instructions or program notes')
    include_text = fields.Boolean(string='Include Text', default=False)

    def action_add_attachments(self):
        """Add attachments and text to the operation using original filenames"""
        # Handle file attachments
        for attachment in self.attachment_ids:
            attachment.write({
                'res_model': 'maeknit.bom.request.operation',
                'res_id': self.operation_id.id if self.operation_id else False,
                'name': attachment.name,  # Use original filename
            })
            
            if self.attachment_type == 'instruction':
                self.operation_id.instruction_attachment_ids = [(4, attachment.id)]
            else:
                self.operation_id.program_attachment_ids = [(4, attachment.id)]
        
        if self.include_text and self.text_content:
            if self.attachment_type == 'instruction':
                existing_text = self.operation_id.instruction_text or ''
                new_text = f"{existing_text}\n{self.text_content}".strip()
                self.operation_id.instruction_text = new_text
            else:
                existing_text = self.operation_id.program_text or ''
                new_text = f"{existing_text}\n{self.text_content}".strip()
                self.operation_id.program_text = new_text
        
        return {'type': 'ir.actions.act_window_close'}

    def action_view_attachments(self):
        """View all attachments for this operation"""
        domain = [
            ('res_model', '=', 'maeknit.bom.request.operation'),
            ('res_id', '=', self.operation_id.id if self.operation_id else False)
        ]
        
        return {
            'name': 'Operation Attachments',
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'default_res_model': 'maeknit.bom.request.operation',
                'default_res_id': self.operation_id.id if self.operation_id else False,
            }
        }
