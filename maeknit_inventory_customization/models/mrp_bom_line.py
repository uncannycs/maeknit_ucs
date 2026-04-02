from odoo import models, fields, api
import logging

class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'
    
    unit_cost = fields.Float(string='Unit Cost', compute='_compute_unit_cost', store=True)
    line_cost = fields.Float(string='Amount', compute='_compute_line_cost', store=True)
    currency_id = fields.Many2one('res.currency', related='bom_id.currency_id')
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
    
    request_line_id = fields.Many2one(
        'maeknit.bom.request.line',
        string='BOM Request Line',
        readonly=True
    )
    
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

    @api.onchange('product_id')
    def _onchange_product_id(self):
        logging.info(" Custom Code:[BOM LINE] _onchange_product_id triggered")
        """Assign proper UoM based on component product type."""
        if not self.product_id:
            return

        product = self.product_id.product_tmpl_id
        logging.info(" Custom Code:[BOM LINE] Onchange product: %s", product.name)

        gram_uom = (
            self.env.ref("uom.product_uom_gram", raise_if_not_found=False)
            or self.env["uom.uom"].search([("name", "=", "g")], limit=1)
        )
        unit_uom = (
            self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
            or self.env["uom.uom"].search([("name", "ilike", "unit")], limit=1)
        )

        # YARN → GRAM
        if self._is_yarn(product) and gram_uom:
            logging.info(" Custom Code:[BOM LINE] Yarn detected → g")
            self.product_uom_id = gram_uom.id
            return

        # GARMENT → UNIT
        if self._is_garment(product) and unit_uom:
            logging.info(" Custom Code:[BOM LINE] Garment detected → Unit")
            self.product_uom_id = unit_uom.id
            return

        # SWATCH → UNIT
        if self._is_swatch(product) and unit_uom:
            logging.info(" Custom Code:[BOM LINE] Swatch detected → Unit")
            self.product_uom_id = unit_uom.id
            return

        # DEFAULT fallback → product's own UoM
        logging.info(" Custom Code:[BOM LINE] Fallback to product base UoM")
        self.product_uom_id = self.product_id.uom_id.id

    @api.depends('product_id')
    def _compute_unit_cost(self):
        """Compute the unit cost based on the product's cost price"""
        for line in self:
            if line.product_id:
                line.unit_cost = line.product_id.cost_price
                logging.info(f" Custom Code: Computed unit cost for {line.product_id.name}: {line.unit_cost}")
            else:
                line.unit_cost = 0.0
    
    @api.depends('product_qty', 'unit_cost')
    def _compute_line_cost(self):
        """Compute the line cost (quantity * unit cost)"""
        for line in self:
            line.line_cost = line.product_qty * line.unit_cost
            
            # Trigger recomputation of the BOM's total cost
            if line.bom_id:
                line.bom_id._compute_total_cost()
                
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to trigger total cost recalculation"""
        lines = super(MrpBomLine, self).create(vals_list)
        logging.info(" Custom Code:[BOM LINE] Created %d lines, triggering BOM total cost recomputation", len(lines))
        # Trigger recomputation of the BOM's total cost for each created line
        for line in lines:
            if line.bom_id:
                line.bom_id._compute_total_cost()
                
        return lines
    
    def write(self, vals):
        """Override write to trigger total cost recalculation"""
        logging.info(" Custom Code:[BOM LINE] Writing lines with vals: %s", vals)
        result = super(MrpBomLine, self).write(vals)
        
        # Trigger recomputation of the BOM's total cost if relevant fields were updated
        if any(field in vals for field in ['product_id', 'product_qty']):
            for line in self:
                if line.bom_id:
                    line.bom_id._compute_total_cost()
                    
        return result

    @api.depends('company_id')
    def _compute_is_uk_company(self):
        for line in self:
            line.is_uk_company = bool(line.company_id and 'uk' in (line.company_id.name or '').lower())
