from odoo import models, api, fields
from odoo.tools import float_round


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.depends('product_qty', 'product_uom', 'company_id', 'order_id.partner_id')
    def _compute_price_unit_and_date_planned_and_name(self):
        super()._compute_price_unit_and_date_planned_and_name()
        for line in self:
            if not line.product_id or line.invoice_lines or not line.company_id:
                continue
            cost = line.product_id.standard_price
            if not cost:
                continue
            po_line_uom = line.product_uom or line.product_id.uom_po_id
            price_unit = line.env['account.tax']._fix_tax_included_price_company(
                line.product_id.uom_id._compute_price(cost, po_line_uom),
                line.product_id.supplier_taxes_id,
                line.taxes_id,
                line.company_id,
            )
            price_unit = line.product_id.cost_currency_id._convert(
                price_unit,
                line.currency_id,
                line.company_id,
                line.date_order or line.env.context.get('default_date_order'),
                False,
            )
            line.price_unit = float_round(
                price_unit,
                precision_digits=max(
                    line.currency_id.decimal_places,
                    line.env['decimal.precision'].precision_get('Product Price'),
                ),
            )

    def write(self, vals):
        res = super().write(vals)
        if 'price_unit' in vals and not self.env.context.get('_skip_yarn_cost_sync'):
            self.with_context(_skip_yarn_cost_sync=True)._sync_yarn_product_costs()
        return res

    def _sync_yarn_product_costs(self):
        """When a PO line is saved, push the unit price back to the yarn product's
        cost and sales price, converting UOM (e.g. lbs → kg) as needed."""
        for line in self:
            if not line.product_id or line.display_type or not line.price_unit:
                continue

            template = line.product_id.product_tmpl_id
            if template.product_category != 'yarn':
                continue

            # Convert price from PO line UOM to the product's stock UOM
            # e.g. $5/lb → $11.02/kg  (uses Odoo's built-in factor math)
            if line.product_uom and line.product_uom != line.product_id.uom_id:
                price = line.product_uom._compute_price(
                    line.price_unit, line.product_id.uom_id
                )
            else:
                price = line.price_unit

            # Convert currency if the PO currency differs from product cost currency
            if line.currency_id != template.cost_currency_id:
                price = line.currency_id._convert(
                    price,
                    template.cost_currency_id,
                    line.company_id,
                    line.date_order or fields.Date.today(),
                )

            # For yarn: cost = sales price, no negotiation
            template.with_context(_skip_yarn_cost_sync=True).write({
                'standard_price': price,
                'cost_price': price,
                'list_price': price,
                'sales_price': price,
            })
