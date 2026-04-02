from odoo import models, fields, api
import logging

class QualityAlert(models.Model):
    _inherit = 'quality.alert'

    program_workorder_id = fields.Many2one(
        'mrp.workorder',
        string='Program Work Order',
        help='The Program work order that needs to be re-done for this quality alert',
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to log quality alert creation for reprogram requests."""
        alerts = super().create(vals_list)
        for alert in alerts:
            if alert.program_workorder_id:
                logging.info(
                    "Custom Code: [QUALITY_ALERT] Created reprogram alert %s linked to Program WO %s",
                    alert.name, alert.program_workorder_id.name
                )
        return alerts
