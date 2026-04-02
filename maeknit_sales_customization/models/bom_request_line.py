from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
from odoo import _
from markupsafe import Markup, escape
class BOMRequestLine(models.Model):
    """BOM Request Lines (Components) - Syncs with mrp.bom.line"""
    _name = 'maeknit.bom.request.line'
    _description = 'BOM Request Line'
    _order = 'sequence, id' # Add sequence for ordering

    bom_request_id = fields.Many2one('maeknit.bom.request', string='BOM Request', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', 
        string='Component', 
        required=True,
        domain="[('product_tmpl_id.product_category', 'not in', ['garment', 'swatch', 'services'])]"
    )
    product_qty = fields.Float(string='Quantity', default=0.0, required=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    unit_cost = fields.Float(related='product_id.standard_price', string='Unit Cost', readonly=True)
    line_cost = fields.Float(string='Line Cost', compute='_compute_line_cost', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_id', store=True)
    ply = fields.Selection(
    [(str(i), str(i)) for i in range(1, 11)],
        string="Ply",
        required=True,
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

    structure_id = fields.Many2one('maeknit.structure.line', string='Structure Line', domain="[('bom_request_id', '=', bom_request_id)]")
    is_uk_company = fields.Boolean(
        string='Is UK Company',
        compute='_compute_is_uk_company',
        store=False,
        readonly=True,
    )
    @api.depends('bom_request_id.company_id')
    def _compute_is_uk_company(self):
        for record in self:
            record.is_uk_company = bool(record.bom_request_id.company_id and 'uk' in (record.bom_request_id.company_id.name or '').lower())

    sequence = fields.Integer(string='Sequence', default=10) # Add sequence field
    # Link to the actual mrp.bom.line record
    mrp_bom_line_id = fields.Many2one('mrp.bom.line', string='Original BOM Line', ondelete='set null', copy=False)

    @api.depends('bom_request_id', 'bom_request_id.currency_id')
    def _compute_currency_id(self):
        for line in self:
            line.currency_id = line.bom_request_id.currency_id.id if line.bom_request_id and line.bom_request_id.currency_id else False

    @api.depends("product_qty", "unit_cost", "product_uom_id")
    def _compute_line_cost(self):
        for line in self:
            qty = line.product_qty
            # Special rule: if UoM is grams, apply 0.5 factor
            if line.product_uom_id and line.product_uom_id.name.lower() in ["g", "gram", "grams"]:
                qty = qty /1000
            line.line_cost = qty * line.unit_cost
    
    def _category_is(self, product, keyword):
        if not product or not product.categ_id:
            return False
        name = (product.categ_id.complete_name or product.categ_id.name or "").lower()
        return keyword in name

    def _is_yarn(self, product):
        return self._category_is(product, "yarn")

    def _is_garment(self, product):
        return self._category_is(product, "garment")

    def _is_swatch(self, product):
        return self._category_is(product, "swatch")

    def _get_gram_uom(self):
        """Return the Gram UoM (weight category). Fallback to search if XML ID missing."""
        try:
            return self.env.ref("uom.product_uom_gram")
        except Exception:
            return self.env["uom.uom"].search([
                ("category_id", "=", self.env.ref("uom.uom_categ_wt").id),
                ("name", "ilike", "gram")
            ], limit=1)
            
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Set default UoM when product is selected"""
        logging.info(" Custom Code:Onchange: Product selected, checking UoM assignment %s", self.product_id)
        if not self.product_id:
            return
        gram_uom = self.env.ref('uom.product_uom_gram', raise_if_not_found=False) \
            or self.env['uom.uom'].search([('name', '=', 'g')], limit=1)
        unit_uom = self.env.ref('uom.product_uom_unit', raise_if_not_found=False) \
            or self.env['uom.uom'].search([('name', 'ilike', 'unit')], limit=1)
            
        logging.info(" Custom Code:Found Gram UoM: %s", gram_uom)
        if self._is_yarn(self.product_id.product_tmpl_id) and gram_uom:
            logging.info(" Custom Code:Setting BOM Line UoM to GRAM (yarn product)")
            self.product_uom_id = gram_uom.id

        elif self._is_garment(self.product_id.product_tmpl_id) and unit_uom:
            logging.info(" Custom Code:Setting BOM Line UoM to UNIT (garment product)")
            self.product_uom_id = unit_uom.id

        elif self._is_swatch(self.product_id.product_tmpl_id) and unit_uom:
            logging.info(" Custom Code:Setting BOM Line UoM to UNIT (swatch product)")
            self.product_uom_id = unit_uom.id
        else:
            # Default: use the product's own UoM
            self.product_uom_id = self.product_id.uom_id.id


    @api.model_create_multi
    def create(self, vals_list):
        bom_request_lines = super(BOMRequestLine, self).create(vals_list)

        for line in bom_request_lines:

            if not line.mrp_bom_line_id:
                
                mrp_vals = {
                    'bom_id': line.bom_request_id.bom_id.id,
                    'product_id': line.product_id.id,
                    'product_qty': line.product_qty,
                    'product_uom_id': line.product_uom_id.id,
                    'sequence': line.sequence,
                    'x_ply': line.ply, 
                    'left_carrier': line.left_carrier,
                    'right_carrier': line.right_carrier,
                    'request_line_id': line.id,
                    'structure_id': line.structure_id.id if line.structure_id else False,
                }
                
                mrp_bom_line = self.env['mrp.bom.line'].create(mrp_vals)
                line.mrp_bom_line_id = mrp_bom_line.id
                
                
        return bom_request_lines

    def write(self, vals):

        res = super(BOMRequestLine, self).write(vals)
        
        for line in self:

            if line.mrp_bom_line_id:
                
                update_vals = {
                    'product_id': line.product_id.id,
                    'product_qty': line.product_qty,
                    'product_uom_id': line.product_uom_id.id,
                    'sequence': line.sequence,
                    'x_ply': line.ply, 
                    'left_carrier': line.left_carrier,
                    'right_carrier': line.right_carrier,
                    'request_line_id': line.id,
                    'structure_id': line.structure_id.id if line.structure_id else False,
                }
                
                line.mrp_bom_line_id.write(update_vals)
                
                
        return res

    def unlink(self):
        
        for line in self:
            if line.mrp_bom_line_id:
                line.mrp_bom_line_id.unlink()
                
        result = super(BOMRequestLine, self).unlink()
        return result
