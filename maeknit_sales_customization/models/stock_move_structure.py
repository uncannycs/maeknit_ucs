from odoo import models, fields, api
import logging


class StockMove(models.Model):
    _inherit = 'stock.move'
    
    structure_id = fields.Many2one(
        'maeknit.structure.line',
        string='Structure',
        store=True,
        help='Structure line from BOM Request'
    )
    
    @api.model_create_multi
    def create(self, vals_list):
        
        moves = super(StockMove, self).create(vals_list)
        
        for move in moves:
            if move.bom_line_id and hasattr(move.bom_line_id, 'structure_id'):

                if move.bom_line_id.structure_id:
                    try:
                        structure_id_value = move.bom_line_id.structure_id.id if hasattr(move.bom_line_id.structure_id, 'id') else move.bom_line_id.structure_id
                        move.structure_id = structure_id_value
                    except Exception as e:
                        logging.error(f"[STOCK MOVE STRUCTURE] CREATE - Error setting structure_id: {e}")
                else:
                    logging.info(f" Custom Code: [STOCK MOVE STRUCTURE] CREATE - No structure_id on BOM line")
        
        return moves
    
    def write(self, vals):

        result = super(StockMove, self).write(vals)
        
        if 'bom_line_id' in vals:
            for move in self:
                if move.bom_line_id and hasattr(move.bom_line_id, 'structure_id') and move.bom_line_id.structure_id:
                    try:
                        structure_id_value = move.bom_line_id.structure_id.id if hasattr(move.bom_line_id.structure_id, 'id') else move.bom_line_id.structure_id
                        move.structure_id = structure_id_value
                    except Exception as e:
                        logging.error(f"[STOCK MOVE STRUCTURE] WRITE - Error setting structure_id: {e}")
        
        return result
