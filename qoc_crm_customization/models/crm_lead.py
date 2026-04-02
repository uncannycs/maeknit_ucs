from odoo import fields, models, api, Command


class CRMLead(models.Model):
    _inherit = "crm.lead"

    service_revenues = fields.Char()
    season_drop_date = fields.Date()
    onboarding_data = fields.Char()
    gemini_notes = fields.Text()

    parent_id = fields.Many2one("crm.lead")
    child_ids = fields.One2many("crm.lead", "parent_id")

    product_ids = fields.Many2many("crm.lead.product")

    expected_revenue = fields.Monetary(
        compute="_compute_expected_revenue", readonly=False, store=True
    )

    @api.depends("child_ids.expected_revenue")
    def _compute_expected_revenue(self):
        """
        Expected revenue is the sum of the child expected revenue
        """
        for record in self:
            if record.child_ids:
                record.expected_revenue = sum(
                    record.child_ids.mapped("expected_revenue")
                )
            else:
                record.expected_revenue = record.expected_revenue

    def _prepare_opportunity_quotation_context(self):
        """
        Override the data to include the sale order lines for the quotation
        """
        res = super()._prepare_opportunity_quotation_context()
        order_lines = self._get_quotation_lines()
        res["default_order_line"] = [Command.create(line) for line in order_lines]
        return res

    def _get_products(self):
        """
        Get the products for this opportunity and it's children
        """
        products = self.product_ids
        for child in self.child_ids:
            products |= child._get_products()
        return products

    def _get_quotation_lines(self):
        """
        Get the sale order lines for the quotation
        """
        products = self._get_products()
        return [
            {
                "product_id": product.id,
                "product_uom_qty": product.quantity,
                "price_unit": product.price,
            }
            for product in products
        ]


class CRMLeadProduct(models.Model):
    _name = "crm.lead.product"
    _description = "A product associated with a Lead"

    product_id = fields.Many2one("product.product", required=True)
    quantity = fields.Float()
    price = fields.Float(readonly=False, compute="_compute_values", store=True)
    cost = fields.Float(readonly=False, compute="_compute_values", store=True)

    @api.depends("product_id")
    def _compute_values(self):
        """
        Default in the product's values
        """
        for record in self:
            record.price = record.product_id.list_price
            record.cost = record.product_id.standard_price
