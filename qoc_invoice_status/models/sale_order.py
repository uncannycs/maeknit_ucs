from odoo import fields, models, api


class SaleOrder(models.Model):
    _inherit = "sale.order"

    invoices_paid = fields.Boolean(compute="_compute_invoices_paid", store=True)

    @api.depends("invoice_ids.payment_state")
    def _compute_invoices_paid(self):
        """
        Indicate if all related invoices are paid, at least one invoice needs to exist
        """
        for record in self:
            payment_states = record.invoice_ids.mapped("payment_state")
            record.invoices_paid = record.invoice_ids and all(
                map(lambda x: x == "paid", payment_states)
            )
