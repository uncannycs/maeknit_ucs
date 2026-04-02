from odoo import models, fields, api, _
import logging


class SaleOrderLinePricing(models.Model):
    _name = 'sale.order.line.pricing'
    _description = 'Sale Order Line Pricing Calculator Data'

    sale_order_line_id = fields.Many2one(
        'sale.order.line', string='Sale Order Line', required=True, ondelete='cascade'
    )
    operation_ids = fields.One2many(
        'sale.order.line.pricing.operation', 'pricing_id', string='Operations'
    )
    material_cost = fields.Float(string='Material Cost', default=0.0)
    margin_percentage = fields.Float(string='Margin %', default=60.0)
    shipping_cost = fields.Float(string='Shipping Cost', default=0.0)
    total_cost = fields.Float(
        string='Total Cost', compute='_compute_total_cost', store=True
    )

    @api.depends(
        'operation_ids.total_cost',
        'material_cost',
        'margin_percentage',
        'shipping_cost'
    )
    def _compute_total_cost(self):
        for record in self:
            operations_total = round(
                sum(record.operation_ids.mapped('total_cost'))
            )

            subtotal = round(
                operations_total + (record.material_cost or 0.0)
            )

            margin_amount = round(
                subtotal * (record.margin_percentage / 100.0)
            )

            record.total_cost = round(
                subtotal + margin_amount + (record.shipping_cost or 0.0)
            )


class SaleOrderLinePricingOperation(models.Model):
    _name = 'sale.order.line.pricing.operation'
    _description = 'Pricing Operation Line'
    _order = 'sequence, id'

    pricing_id = fields.Many2one(
        'sale.order.line.pricing', string='Pricing', required=True, ondelete='cascade'
    )
    sequence = fields.Integer(string='Sequence', default=10)
    operation_id = fields.Many2one(
        'maeknit.shopfloor.operation', string='Operation', required=True
    )
    operation_name = fields.Char(
        string='Operation Name', related='operation_id.name', store=True
    )
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center')
    employee_id = fields.Many2one('hr.employee', string='Assigned Person')
    expected_minutes = fields.Float(string='Expected Time (Minutes)', default=0.0)
    hourly_rate = fields.Float(string='Hourly Rate', default=30.0)
    workcenter_cost_per_hour = fields.Float(
        string='Workcenter Cost/Hour',
        related='workcenter_id.costs_hour',
        store=True
    )
    is_outsourced = fields.Boolean(string='Outsourced', default=False)
    outsource_amount = fields.Float(string='Outsource Amount (£)', default=0.0)
    total_cost = fields.Float(
        string='Total Cost', compute='_compute_total_cost', store=True
    )

    @api.depends('expected_minutes', 'hourly_rate', 'workcenter_cost_per_hour',
                 'is_outsourced', 'outsource_amount')
    def _compute_total_cost(self):
        for record in self:
            if record.is_outsourced:
                record.total_cost = round(record.outsource_amount or 0.0)
            else:
                hours = record.expected_minutes / 60.0

                labor_cost = round(hours * (record.hourly_rate or 0.0))
                workcenter_cost = round(
                    hours * (record.workcenter_cost_per_hour or 0.0)
                )

                record.total_cost = round(labor_cost + workcenter_cost)
