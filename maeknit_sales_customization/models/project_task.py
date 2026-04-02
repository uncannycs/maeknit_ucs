from odoo import models, fields, api
import logging
from odoo.exceptions import ValidationError, UserError
from odoo.tools.translate import _

class ProjectTask(models.Model):
    _inherit = "project.task"

    is_clocked_in = fields.Boolean(default=False)
    clock_in_time = fields.Datetime()
    
    bom_request_id = fields.Many2one("maeknit.bom.request", index=True)

    child_task_ids = fields.One2many(
        "project.task",
        "parent_id",
        string="Sub Tasks",
    )
    is_timer_running = fields.Boolean()
    timer_start = fields.Datetime()
    accumulated_seconds = fields.Integer(default=0)
    
    def action_open_task(self):
        """Open the current task in form view"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
 
    @api.model_create_multi
    def create(self, vals_list):
        Br = self.env['maeknit.bom.request']
        for vals in vals_list:
            br_id = vals.get('bom_request_id')
            if br_id and not vals.get('parent_id'):
                br = Br.browse(br_id)
                main = br.project_task_id
                # On create there is no id in vals, so just set if available
                if main:
                    vals['parent_id'] = main.id
                    if not vals.get('project_id') and main.project_id:
                        vals['project_id'] = main.project_id.id
        tasks = super().create(vals_list)

        # Post-create safety: if any task accidentally points to itself, unset parent
        for task in tasks:
            if task.parent_id and task.parent_id.id == task.id:
                task.write({'parent_id': False})
        return tasks

    def write(self, vals):
        res = super().write(vals)

        # If bom_request_id changed, try to backfill parent/project—but never self-parent
        if 'bom_request_id' in vals:
            for task in self:
                if task.bom_request_id and not task.parent_id:
                    main = task.bom_request_id.project_task_id
                    if main and task.id != main.id:
                        updates = {'parent_id': main.id}
                        if not task.project_id and main.project_id:
                            updates['project_id'] = main.project_id.id
                        super(ProjectTask, task).write(updates)
        # Extra safety: if parent_id was set directly to self, clear it
        if 'parent_id' in vals:
            for task in self:
                if task.parent_id and task.parent_id.id == task.id:
                    super(ProjectTask, task).write({'parent_id': False})
        return res

    @api.onchange('bom_request_id')
    def _onchange_bom_request_id_set_parent(self):
        if self.bom_request_id and not self.parent_id:
            main = self.bom_request_id.project_task_id
            if main and (not self.id or self.id != main.id):
                self.parent_id = main.id
                if not self.project_id and main.project_id:
                    self.project_id = main.project_id.id

    @api.constrains('parent_id')
    def _check_parent_not_self(self):
        for rec in self:
            if rec.parent_id and rec.parent_id.id == rec.id:
                raise ValidationError(_("A task cannot be its own parent."))