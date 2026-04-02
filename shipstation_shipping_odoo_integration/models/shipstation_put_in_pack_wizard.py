import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class ShipstationPutInPackLineItem(models.TransientModel):
    """Line items selected for a specific package with adjustable quantities"""
    _name = 'shipstation.put.in.pack.line.item'
    _description = 'ShipStation Package Line Item'

    package_line_id = fields.Many2one('shipstation.put.in.pack.line', string='Package Line', required=True, ondelete='cascade')
    move_line_id = fields.Many2one('stock.move.line', string='Move Line', required=True)
    product_id = fields.Many2one('product.product', related='move_line_id.product_id', readonly=True)
    max_quantity = fields.Float(string='Available Qty', related='move_line_id.quantity', readonly=True)
    pack_quantity = fields.Float(string='Pack Qty', required=True, digits='Product Unit of Measure')
    product_uom_id = fields.Many2one('uom.uom', related='move_line_id.product_uom_id', readonly=True)


class ShipstationPutInPackLine(models.TransientModel):
    """A package container with selected items"""
    _name = 'shipstation.put.in.pack.line'
    _description = 'ShipStation Package Row'

    wizard_id = fields.Many2one('shipstation.put.in.pack.wizard', string='Wizard', required=True, ondelete='cascade')
    package_num = fields.Integer(string='Package Number', readonly=True)
    name = fields.Char(string='Package Name', required=True)
    package_type_id = fields.Many2one('stock.package.type', string='Package Type', help='Type of package for dimension/weight defaults')
    length = fields.Float(string='Length', digits='Product Unit of Measure')
    width = fields.Float(string='Width', digits='Product Unit of Measure')
    height = fields.Float(string='Height', digits='Product Unit of Measure')
    shipping_weight = fields.Float(string='Shipping Weight', digits='Stock Weight')
    line_item_ids = fields.One2many('shipstation.put.in.pack.line.item', 'package_line_id', string='Items')


class ShipstationPutInPackWizard(models.TransientModel):
    _name = 'shipstation.put.in.pack.wizard'
    _description = 'ShipStation Put in Pack Wizard'

    picking_id = fields.Many2one('stock.picking', string='Picking', required=True)
    package_line_ids = fields.One2many('shipstation.put.in.pack.line', 'wizard_id', string='Packages')
    available_move_line_ids = fields.Many2many('stock.move.line', compute='_compute_available_move_lines', readonly=True)

    @api.depends('picking_id')
    def _compute_available_move_lines(self):
        """Get all unpacked move lines from the picking"""
        for wizard in self:
            available = wizard.picking_id.move_line_ids.filtered(
                lambda ml: not ml.result_package_id
                and float_compare(ml.quantity, 0, precision_rounding=ml.product_uom_id.rounding) > 0
                and ml.product_id.weight > 0
            )
            wizard.available_move_line_ids = available

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        picking = self.env['stock.picking'].browse(self.env.context.get('default_picking_id'))
        if picking:
            res['picking_id'] = picking.id
            if not res.get('package_line_ids'):
                res['package_line_ids'] = [(0, 0, {'name': _('Package 1'), 'package_num': 1})]
        return res

    def _get_packed_quantities(self):
        """Get dict of move_line_id -> quantity already packed"""
        packed = {}
        for pkg_line in self.package_line_ids:
            for item in pkg_line.line_item_ids:
                packed[item.move_line_id.id] = packed.get(item.move_line_id.id, 0) + item.pack_quantity
        return packed

    def action_create_custom_package(self):
        """Create all packages with selected items and quantities"""
        self.ensure_one()
        logging.info(" Custom Code:ShipStation put-in-pack start: picking=%s", self.picking_id)
        created_packages = self.env['stock.quant.package']

        for package_line in self.package_line_ids:
            if not package_line.line_item_ids:
                continue

            # Validate quantities don't exceed available
            for item in package_line.line_item_ids:
                if item.pack_quantity > item.max_quantity:
                    raise ValidationError(
                        _("Cannot pack %(qty)s of %(product)s - only %(max)s available") % {
                            'qty': item.pack_quantity,
                            'product': item.product_id.display_name,
                            'max': item.max_quantity
                        }
                    )

            # Get move lines for this package
            move_lines = package_line.line_item_ids.mapped('move_line_id')

            # Update move line quantities to match pack quantities
            for item in package_line.line_item_ids:
                item.move_line_id.quantity = item.pack_quantity

            logging.info(" Custom Code:Creating package '%s' with items %s", package_line.name, move_lines.ids)

            # Create package with selected move lines
            package = self.picking_id._put_in_pack(move_lines)
            if not package:
                continue

            # Update package details
            updates = {
                'name': package_line.name,
                'is_generate_label_in_shipstation': True,
            }

            # Set dimensions
            for dim_field in ('length', 'width', 'height'):
                value = getattr(package_line, dim_field)
                if value:
                    updates[dim_field] = value

            # Set package type
            if package_line.package_type_id:
                updates['package_type_id'] = package_line.package_type_id.id
            if self.picking_id.delivery_package_id:
                updates['shipstation_delivery_package_id'] = self.picking_id.delivery_package_id.id
            if self.picking_id.carrier_id:
                updates['carrier_id'] = self.picking_id.carrier_id.id

            package.write(updates)

            # Set shipping weight
            if package_line.shipping_weight:
                package.shipping_weight = package_line.shipping_weight

            created_packages |= package

        if not created_packages:
            raise ValidationError(_("No packages were created. Select items to pack."))

        logging.info(" Custom Code:ShipStation put-in-pack completed: created_packages=%s", created_packages.ids)

        # Return action to open the packages in list view
        return {
            'type': 'ir.actions.act_window',
            'name': _('Created Packages'),
            'res_model': 'stock.quant.package',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created_packages.ids)],
            'context': {
                'default_carrier_id': self.picking_id.carrier_id.id if self.picking_id.carrier_id else False,
            },
            'target': 'current',
        }

    def action_add_package(self):
        """Add a new package line for remaining items"""
        self.ensure_one()
        next_num = len(self.package_line_ids) + 1
        new_package = self.env['shipstation.put.in.pack.line'].create({
            'wizard_id': self.id,
            'name': _('Package %d') % next_num,
            'package_num': next_num,
        })
        # Return updated view
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'shipstation.put.in.pack.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model
    def get_available_package_types(self):
        """Get all available package types for selection"""
        return self.env['stock.package.type'].search_read(
            [],
            ['id', 'name', 'packaging_length', 'width', 'height', 'max_weight']
        )
