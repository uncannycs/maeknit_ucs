from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

class MrpCalibrationWizard(models.TransientModel):
    _name = "mrp.calibration.wizard"
    _description = "Calibration Swatch Confirmation"

    mo_id = fields.Many2one("mrp.production", string="Manufacturing Order", required=True)

    def action_generate(self):
        self.ensure_one()
        mo = self.mo_id
        logging.info("Wizard confirmed: generating calibration swatch for MO %s", mo.id)
        return mo.action_generate_calibration_swatch()

    def action_skip(self):
        self.ensure_one()
        logging.info("Wizard skipped for MO %s", self.mo_id.id)
        return self.mo_id.with_context(skip_calibration=True).action_confirm_finalize()
