from odoo import models, fields, api
import base64
import logging
from markupsafe import Markup

class ClientAttachmentWizard(models.TransientModel):
    _name = 'client.attachment.wizard'
    _description = 'Client Files Viewer Wizard'

    bom_request_id = fields.Many2one('maeknit.bom.request', string='BOM Request', required=True)
    selected_attachment_id = fields.Many2one('ir.attachment', string='Select File', 
                                           domain="[('id', 'in', available_attachment_ids)]")
    available_attachment_ids = fields.Many2many('ir.attachment', compute='_compute_available_attachments')
    
    attachment_preview = fields.Html(
        string='Preview',
        compute='_compute_attachment_preview',
        sanitize=False
    )
    attachment_name = fields.Char(string='File Name', compute='_compute_attachment_details')
    attachment_size = fields.Char(string='File Size', compute='_compute_attachment_details')
    attachment_mimetype = fields.Char(string='File Type', compute='_compute_attachment_details')
    attachment_url = fields.Char(string='Download URL', compute='_compute_attachment_details')

    @api.depends('bom_request_id')
    def _compute_available_attachments(self):
        for record in self:
            if record.bom_request_id:
                # Get all client attachments for this BOM request
                attachments = self.env['ir.attachment'].search([
                    ('res_model', '=', 'maeknit.bom.request'),
                    ('res_id', '=', record.bom_request_id.id),
                    ('res_field', '=', False),
                ])
                attachment_ids = attachments.ids
                logging.info(f"Found {len(attachment_ids)} client attachments for BOM request {record.bom_request_id.id}")
                
                record.available_attachment_ids = [(6, 0, attachment_ids)]
                if attachment_ids and not record.selected_attachment_id:
                    record.selected_attachment_id = self.env['ir.attachment'].browse(attachment_ids[0])
                    logging.info(f"Auto-selected attachment {attachment_ids[0]}")
            else:
                record.available_attachment_ids = [(6, 0, [])]

    @api.depends('selected_attachment_id')
    def _compute_attachment_details(self):
        for record in self:
            if record.selected_attachment_id:
                attachment = record.selected_attachment_id
                record.attachment_name = attachment.name
                record.attachment_size = self._format_file_size(attachment.file_size)
                record.attachment_mimetype = attachment.mimetype or 'Unknown'
                record.attachment_url = f'/web/content/{attachment.id}?download=true'
            else:
                record.attachment_name = False
                record.attachment_size = False
                record.attachment_mimetype = False
                record.attachment_url = False

    @api.depends('selected_attachment_id')
    def _compute_attachment_preview(self):
        for record in self:
            if record.selected_attachment_id:
                html = record._generate_preview(record.selected_attachment_id)
                record.attachment_preview = Markup(html)
            else:
                record.attachment_preview = Markup('<p>Select a file to preview</p>')

    def _format_file_size(self, size_bytes):
        """Convert bytes to human readable format"""
        if not size_bytes:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def _generate_preview(self, attachment):
        """Generate HTML preview for different file types"""
        if not attachment:
            return '<p>Select a file to preview</p>'
        
        mimetype = attachment.mimetype or ''
        
        preview_html = f'''
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">{attachment.name}</h5>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>Type:</strong> {mimetype}</p>
                        <p><strong>Size:</strong> {self._format_file_size(attachment.file_size)}</p>
                    </div>
                    <div class="col-md-6 text-right">
                        <a href="/web/content/{attachment.id}" target="_blank" class="btn btn-primary btn-sm mr-2">
                            <i class="fa fa-eye"></i> View
                        </a>
                        <a href="/web/content/{attachment.id}?download=true" class="btn btn-secondary btn-sm">
                            <i class="fa fa-download"></i> Download
                        </a>
                    </div>
                </div>
        '''
        
        content_html = self._get_content_preview(attachment, mimetype)
        preview_html += content_html + '</div></div>'
        
        return preview_html

    def _get_content_preview(self, attachment, mimetype):
        """Generate content-specific preview"""
        try:
            if mimetype.startswith('image/'):
                return f'''
                <div class="mt-3 text-center">
                    <img src="/web/image/{attachment.id}" class="img-fluid" style="max-height: 300px;"/>
                </div>
                '''
            
            elif mimetype.startswith('text/') or mimetype == 'application/json':
                text_content = base64.b64decode(attachment.datas).decode('utf-8', errors='ignore')
                display_content = text_content[:1000] + ('...' if len(text_content) > 1000 else '')
                display_content = display_content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                return f'''
                <div class="mt-3">
                    <h6>Content Preview:</h6>
                    <pre style="max-height: 200px; overflow: auto; background: #f8f9fa; padding: 10px; border: 1px solid #dee2e6;">{display_content}</pre>
                </div>
                '''
            
            elif mimetype == 'application/pdf':
                return '''
                <div class="mt-3 alert alert-info">
                    <i class="fa fa-file-pdf-o mr-2"></i>
                    PDF document - use the View button to open in a new tab
                </div>
                '''
            
            else:
                return f'''
                <div class="mt-3 alert alert-warning">
                    <i class="fa fa-info-circle mr-2"></i>
                    Preview not available for {mimetype} files
                </div>
                '''
                
        except Exception as e:
            return f'''
            <div class="mt-3 alert alert-danger">
                <i class="fa fa-exclamation-triangle mr-2"></i>
                Error generating preview: {str(e)}
            </div>
            '''

    def action_download_file(self):
        """Download the selected file"""
        if self.selected_attachment_id:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{self.selected_attachment_id.id}?download=true',
                'target': 'new',
            }

    def action_open_file(self):
        """Open file in new tab"""
        if self.selected_attachment_id:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{self.selected_attachment_id.id}',
                'target': 'new',
            }
