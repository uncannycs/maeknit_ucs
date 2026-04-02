from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from markupsafe import Markup, escape
import logging


class BOMRequestOperation(models.Model):
    """BOM Request Operations - Syncs with mrp.bom.operation"""
    _name = 'maeknit.bom.request.operation'
    _description = 'BOM Request Operation'
    _order = 'sequence, id'
    
    bom_request_id = fields.Many2one('maeknit.bom.request', string='BOM Request', required=True, ondelete='cascade')
    operation_id = fields.Many2one('maeknit.shopfloor.operation', string='Operation', required=True, ondelete='restrict')
    workcenter_tag_ids = fields.Many2many(related="operation_id.workcenter_tag_ids", readonly=True, string="Workcenter Tags")
    name = fields.Char(string="Operation Name", related="operation_id.name", store=True, readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center')
    workcenter_domain_ids = fields.Many2many('mrp.workcenter', compute='_compute_workcenter_domain', string='Available Workcenters')
    mo_workorder_id = fields.Many2one('mrp.workorder', string='MO Workorder', help='Link to the Manufacturing Order workorder', ondelete='set null', copy=False)
    employee_assigned_ids = fields.Many2many('hr.employee','bom_request_operation_employee_rel','operation_id','employee_id',string='Assigned Employees',help='Employees assigned to this operation')
    time_cycle = fields.Float(string='Default Duration', default=60)
    sequence = fields.Integer(string='Sequence')
    instruction_text = fields.Text(string='Instruction Text', help='Text instructions for this operation')
    program_text = fields.Text(string='Program Text', help='Program notes for this operation')
    program_attachment_ids = fields.Many2many('ir.attachment','operation_program_attachment_rel','operation_id','attachment_id',string='Program Files',help='Upload program files for this operation')
    instruction_attachment_ids = fields.Many2many('ir.attachment','operation_instruction_attachment_rel','operation_id','attachment_id',string='Instruction Files',help='Upload instruction files for this operation')
    attachment_ids = fields.Many2many('ir.attachment','operation_attachment_rel','operation_id','attachment_id',string='Attachments',help='Upload files directly for this operation')
    program_count = fields.Integer(string='Program Count', compute='_compute_attachment_counts')
    instruction_count = fields.Integer(string='Instruction Count', compute='_compute_attachment_counts')
    program_display = fields.Html(string='Program Display', compute='_compute_attachment_display')
    instruction_display = fields.Html(string='Instruction Display', compute='_compute_attachment_display')
    attachment_count = fields.Integer(string='Attachment Count', compute='_compute_attachment_counts')
    attachment_icons = fields.Html(string='Attachment Icons', compute='_compute_attachment_display')
    knit_attempt = fields.Integer(
        string='Knit Attempt',
        help='Current knit attempt number for this operation'
    )
    program_version = fields.Integer(
        string='Program Count',
        help='Number of times this operation has been reprogrammed'
    )
    
    has_instruction_files = fields.Boolean(
    compute='_compute_has_files', string='Has Instructions', store=False)
    has_program_files = fields.Boolean(
        compute='_compute_has_files', string='Has Programs', store=False)

    def _compute_has_files(self):
        for wo in self:
            wo.has_instruction_files = bool(wo.instruction_count)
            wo.has_program_files = bool(wo.program_count)
    
    
    @api.model_create_multi
    def create(self, vals_list):
        logging.info(" Custom Code:[BOM_OP][CREATE] Creating %s ops", len(vals_list))
        bom_request_operations = super().create(vals_list)
        for op in bom_request_operations:
            logging.info(" Custom Code:[BOM_OP][CREATE] op=%s req=%s state=%s wc=%s name=%s",
                         op.id, op.bom_request_id.id, op.bom_request_id.state, op.workcenter_id.id if op.workcenter_id else None, op.name)
        return bom_request_operations

    def write(self, vals):
        logging.info(" Custom Code:[BOM_OP][WRITE] ids=%s keys=%s", list(self.ids), list(vals.keys()))
        if self.env.context.get('skip_mo_sync'):
            return super().write(vals)
        
        res = super().write(vals)
        
        if 'operation_id' in vals and not self.env.context.get('skip_mo_sync'):
            for op in self:
                if op.mo_workorder_id:
                    op.mo_workorder_id.with_context(skip_bom_sync=True).write({
                        'shopfloor_operation_id': op.operation_id.id,
                        'name': op.operation_id.name
                    })
                    logging.info(" Custom Code:[BOM_OP][WRITE] Synced operation_id op=%s -> wo=%s operation=%s",
                                 op.id, op.mo_workorder_id.id, op.operation_id.name)
        
        if 'employee_assigned_ids' in vals and not self.env.context.get('skip_mo_sync'):
            for op in self:
                if op.mo_workorder_id:
                    op.mo_workorder_id.write({'employee_assigned_ids': [(6, 0, op.employee_assigned_ids.ids)]})
                    logging.info(" Custom Code:[BOM_OP][WRITE] Synced employees op=%s -> wo=%s employees=%s",
                                 op.id, op.mo_workorder_id.id, op.employee_assigned_ids.ids)
        
        return res

    @api.depends('operation_id', 'operation_id.workcenter_tag_ids')
    def _compute_workcenter_domain(self):
        for record in self:
            if record.operation_id and record.operation_id.workcenter_tag_ids:
                workcenters = self.env['mrp.workcenter'].search([('tag_ids', 'in', record.operation_id.workcenter_tag_ids.ids)])
                record.workcenter_domain_ids = workcenters
            else:
                all_wcs = self.env['mrp.workcenter'].search([])
                record.workcenter_domain_ids = all_wcs

    @api.depends('program_attachment_ids', 'instruction_attachment_ids', 'attachment_ids')
    def _compute_attachment_counts(self):
        for operation in self:
            operation.program_count = len(operation.program_attachment_ids)
            operation.instruction_count = len(operation.instruction_attachment_ids)
            operation.attachment_count = len(operation.attachment_ids)

    @api.depends('program_count', 'instruction_count', 'program_attachment_ids', 'instruction_attachment_ids', 'instruction_text', 'program_text')
    def _compute_attachment_display(self):
        for op in self:
            program_items = []
            if op.program_attachment_ids:
                for att in op.program_attachment_ids:
                    preview_url = f'/web/content/{att.id}'
                    program_items.append(f'<a href="{preview_url}" target="_blank" class="text-primary">{att.name}</a>')
            if op.program_text:
                program_items.append('<span class="text-info">[Text Notes]</span>')
            op.program_display = Markup("<br/>".join(program_items)) if program_items else Markup('<span class="text-muted">No programs</span>')

            instruction_items = []
            if op.instruction_attachment_ids:
                for att in op.instruction_attachment_ids:
                    preview_url = f'/web/content/{att.id}'
                    instruction_items.append(f'<a href="{preview_url}" target="_blank" class="text-primary">{att.name}</a>')
            if op.instruction_text:
                instruction_items.append('<span class="text-info">[Text Notes]</span>')
            op.instruction_display = Markup("<br/>".join(instruction_items)) if instruction_items else Markup('<span class="text-muted">No instructions</span>')

            op.attachment_icons = ''
    
    def action_view_operation_attachments(self):
        self.ensure_one()
        action = {
            'name': f'Attachments - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', 'maeknit.bom.request.operation'), ('res_id', '=', self.id)],
            'context': {'default_res_model': 'maeknit.bom.request.operation','default_res_id': self.id},
        }
        logging.info(" Custom Code:[BOM_OP][OPEN_ATTN] op=%s action_domain=%s", self.id, action['domain'])
        return action

    def _get_primary_pdf_attachment(self, operation):
        pdf_attachments = operation.instruction_attachment_ids.filtered(lambda a: a.mimetype == 'application/pdf')
        if not pdf_attachments:
            pdf_attachments = operation.program_attachment_ids.filtered(lambda a: a.mimetype == 'application/pdf')
        if pdf_attachments:
            att = pdf_attachments[0]
            logging.info(" Custom Code:[BOM_OP][PDF_PICK] op=%s picked att id=%s name=%s", operation.id, att.id, att.name)
            return att.datas
        logging.info(" Custom Code:[BOM_OP][PDF_PICK] op=%s no pdf found", operation.id)
        return False

    def _prepare_worksheet_content(self, operation):
        content_parts = []
        if operation.instruction_text:
            content_parts.append(f"INSTRUCTIONS:\n{operation.instruction_text}")
        if operation.program_text:
            content_parts.append(f"PROGRAM NOTES:\n{operation.program_text}")
        if operation.instruction_attachment_ids:
            instruction_files = []
            for att in operation.instruction_attachment_ids:
                download_url = f"/web/content/{att.id}?download=true"
                instruction_files.append(f"{att.name} (Download: {download_url})")
            content_parts.append(f"Instruction Files: {'; '.join(instruction_files)}")
        if operation.program_attachment_ids:
            program_files = []
            for att in operation.program_attachment_ids:
                download_url = f"/web/content/{att.id}?download=true"
                program_files.append(f"{att.name} (Download: {download_url})")
            content_parts.append(f"Program Files: {'; '.join(program_files)}")
        final = "\n\n".join(content_parts) if content_parts else False
        logging.info(" Custom Code:[BOM_OP][WS_CONTENT] op=%s has_content=%s parts=%s", operation.id, bool(final), len(content_parts))
        return final

    def _open_operation_attachment_wizard(self, file_type):
        self.ensure_one()
        view = self.env.ref('maeknit_sales_customization.view_operation_attachment_wizard_form')
        action = {
            'name': f'Upload {file_type.capitalize()} Files',
            'type': 'ir.actions.act_window',
            'res_model': 'operation.attachment.wizard',
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
            'context': {
                'default_bom_request_id': self.bom_request_id.id,
                'default_operation_id': self.id,
                'default_attachment_type': file_type,
            },
        }
        logging.info(" Custom Code:[BOM_OP][OPEN_WIZ] op=%s type=%s", self.id, file_type)
        return action

    def action_manage_program_files(self):
        logging.info(" Custom Code:[BOM_OP][OPEN_WIZ_SHORTCUT] op=%s type=program", self.id)
        return self._open_operation_attachment_wizard('program')

    def action_manage_instruction_files(self):
        logging.info(" Custom Code:[BOM_OP][OPEN_WIZ_SHORTCUT] op=%s type=instruction", self.id)
        return self._open_operation_attachment_wizard('instruction')
