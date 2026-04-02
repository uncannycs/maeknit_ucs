from odoo import models, fields, api
import logging


class StockMove(models.Model):
    _inherit = "stock.move"

    allowed_operation_ids = fields.Many2many(
        'mrp.routing.workcenter',
        compute='_compute_allowed_operation_ids',
        store=False
    )

    x_ply = fields.Selection(
    [(str(i), str(i)) for i in range(1, 11)],
        string="Ply",
    )
    left_carrier = fields.Selection(
    [(str(i), str(i)) for i in range(1, 11)],
        string="Left Carrier",
    )
    right_carrier = fields.Selection(
    [(str(i), str(i)) for i in range(1, 11)],
        string="Right Carrier",
    )
    carrier = fields.Selection(
    [(str(i), str(i)) for i in range(1, 11)],
        string="Carrier",
    )
    is_uk_company = fields.Boolean(
        string='Is UK Company',
        compute='_compute_is_uk_company',
        store=False,
        readonly=True,
    )
    
    consumed_in_operation_id = fields.Many2one(
        'mrp.routing.workcenter',
        string='Consumed in Operation',
        domain="[('id', 'in', allowed_operation_ids)]",
        check_company=True
    )

    @api.onchange('consumed_in_operation_id')
    def _onchange_consumed_in_operation_id(self):
        """Mirror to operation_id so Odoo recognizes the link."""
        self.operation_id = self.consumed_in_operation_id

    @api.onchange('product_id')
    def _onchange_product_id_set_grams(self):
        """When product is yarn → default UoM = grams (g)."""
        if not self.product_id:
            return

        if self.raw_material_production_id:
            product = self.product_id.product_tmpl_id
            categ_name = (product.categ_id.complete_name or product.categ_id.name or '').lower()
            if 'yarn' not in categ_name:
                return

            gram_uom = self.env.ref('uom.product_uom_gram', raise_if_not_found=False) \
                or self.env['uom.uom'].search([('name', '=', 'g')], limit=1)

            if gram_uom:
                self.product_uom = gram_uom.id

    @api.onchange('product_uom')
    def _onchange_product_uom(self):
        """Override to completely remove Odoo's default warning."""
        return
    
    @api.model_create_multi
    def create(self, vals_list):

        for idx, vals in enumerate(vals_list):
            if 'consumed_in_operation_id' in vals:
                vals['operation_id'] = vals['consumed_in_operation_id']
                
        moves = super().create(vals_list)
        
        for move in moves:
            if move.bom_line_id:
                
                if move.bom_line_id.x_ply:
                    move.x_ply = move.bom_line_id.x_ply
                    
                if move.bom_line_id.left_carrier:
                    move.left_carrier = move.bom_line_id.left_carrier
                
                if move.bom_line_id.right_carrier:
                    move.right_carrier = move.bom_line_id.right_carrier
                
        return moves

    def write(self, vals):

        if 'consumed_in_operation_id' in vals:
            vals['operation_id'] = vals['consumed_in_operation_id']
        
        if 'bom_line_id' in vals:
            logging.info(" Custom Code:[STOCK MOVE] WRITE - BOM Line ID in vals: %s", vals['bom_line_id'])
            bom_line = self.env['mrp.bom.line'].browse(vals['bom_line_id'])
            
            if bom_line and bom_line.exists():
                    
                if bom_line.x_ply:
                    vals['x_ply'] = bom_line.x_ply
                    
                if bom_line.left_carrier:
                    vals['left_carrier'] = bom_line.left_carrier
                
                if bom_line.right_carrier:
                    vals['right_carrier'] = bom_line.right_carrier
            else:
                logging.info(" Custom Code:[STOCK MOVE] WRITE - BOM line not found or empty")
                
        result = super().write(vals)
        return result

    def _compute_allowed_operation_ids(self):
        for line in self:
            production = line.raw_material_production_id or line.production_id

            if production and production.bom_id:
                operations = production.bom_id.operation_ids
                line.allowed_operation_ids = operations
            else:
                line.allowed_operation_ids = self.env['mrp.routing.workcenter']

    @api.depends('company_id')
    def _compute_is_uk_company(self):
        for move in self:
            company = move.company_id
            move.is_uk_company = bool(company and 'uk' in (company.name or '').lower())
