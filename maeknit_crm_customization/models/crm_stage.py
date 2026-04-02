from odoo import models, fields, api
import logging

class CrmStage(models.Model):
    _inherit = 'crm.stage'
    
    x_stage_type = fields.Selection([
        ('collection', 'Collection Lead'),
        ('style', 'Style Lead'),
        ('both', 'Both')
    ], string="Stage Type", default='both', required=True,
       help="Determines whether this stage is for collection leads, Style leads, or both")
    
    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        for stage in result:
            logging.info(" Custom Code: Stage created: %s (ID: %s, Type: %s)", stage.name, stage.id, stage.x_stage_type)
        return result
    
    def write(self, vals):
        result = super().write(vals)
        if 'x_stage_type' in vals:
            for stage in self:
                logging.info(" Custom Code: Stage updated: %s (ID: %s, New Type: %s)", stage.name, stage.id, stage.x_stage_type)
        return result
