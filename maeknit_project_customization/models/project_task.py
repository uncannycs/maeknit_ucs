from odoo import models, api, fields

CLOSED_STATES = [
    ('1_done', 'Done'),
    ('1_canceled', 'Cancelled'),
]

ALL_STATES = [
    '00_ready_to_start',
    '01_in_progress',
    '02_changes_requested',
    '03_approved',
    '04_waiting_normal',
    '1_done',
    '1_canceled',
]

class ProjectTask(models.Model):
    _inherit = "project.task"

    state = fields.Selection(
    selection_add=[
        ('00_ready_to_start', 'Ready to Start'),
        ('04_waiting_normal', 'Waiting'),
        *CLOSED_STATES,
    ],
    default="00_ready_to_start",
    ondelete={state: 'set default' for state in ALL_STATES},
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'state' in fields_list and not res.get('state'):
            res['state'] = '00_ready_to_start'
        return res
    def action_open_bom_request(self):
        """Open BOM Request in a new window."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'maeknit.bom.request',
            'res_id': self.bom_request_id.id,
            'view_mode': 'form',
            'name': self.name,
        }
        
    def action_open_bom_queue(self):
        self.ensure_one()
        if self.bom_request_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "maeknit.bom.request",
                "view_mode": "form",
                "res_id": self.bom_request_id.id,
                "target": "current",
            }
        else:
            return {
                "type": "ir.actions.act_window",
                "res_model": "maeknit.bom.request",
                "view_mode": "tree,form",
                "name": "BOM Queue",
            }

    def unlink(self):
        """
        Defensive unlink override — clears tag relations first to prevent
        foreign key constraint errors on project_project_project_tags_rel.
        """
        for rec in self:
            if rec.tag_ids:
                logging.warning(f"Clearing tags before deleting project {rec.name} ({rec.id})")
                rec.write({'tag_ids': [(5, 0, 0)]})
        return super().unlink()