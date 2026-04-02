from odoo import models, fields, api

class MrpBomOperation(models.Model):
    _name = 'mrp.bom.operation'
    _description = 'BOM Operation with Attachments'
    _order = 'sequence, id'

    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char('Operation Name', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center')
    time_cycle = fields.Float('Duration (minutes)', default=0)
    bom_request_id = fields.Many2one('maeknit.bom.request', 'BOM Request', ondelete='cascade')
    
    # Attachment fields
    attachment_ids = fields.One2many('ir.attachment', 'res_id', 
                                   domain=[('res_model', '=', 'mrp.bom.operation')], 
                                   string='Attachments')
    attachment_count = fields.Integer('Attachment Count', compute='_compute_attachment_count')
    
    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for record in self:
            record.attachment_count = len(record.attachment_ids)
    
    def action_view_attachments(self):
        """Open attachment view for this operation"""
        return {
            'name': f'Attachments - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'kanban,list,form',
            'domain': [('res_model', '=', 'mrp.bom.operation'), ('res_id', '=', self.id)],
            'context': {
                'default_res_model': 'mrp.bom.operation',
                'default_res_id': self.id,
            }
        }
