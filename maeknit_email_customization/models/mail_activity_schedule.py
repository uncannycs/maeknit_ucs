from odoo import api, fields, models


class MailActivitySchedule(models.TransientModel):
    _inherit = 'mail.activity.schedule'

    @api.depends('activity_type_id')
    def _compute_date_deadline(self):
        """Override to always set due date to today instead of activity type's default (+5 days)"""
        for scheduler in self:
            scheduler.date_deadline = fields.Date.context_today(scheduler)
