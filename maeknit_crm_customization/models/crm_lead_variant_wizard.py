# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging


class CrmLeadVariantWizard(models.TransientModel):
    _name = 'crm.lead.variant.wizard'
    _description = 'Add Product Variants Wizard'

    product_id = fields.Many2one(
        'product.template',
        string='Product',
        required=True,
        readonly=True
    )

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        required=False,
        readonly=True
    )

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        required=False,
        readonly=True
    )

    variant_line_ids = fields.One2many(
        'crm.lead.variant.wizard.line',
        'wizard_id',
        string='Variant Combinations'
    )

    @api.model
    def default_get(self, fields):
        """Pre-populate with some default lines"""
        res = super().default_get(fields)

        # Add 3 empty lines by default
        if 'variant_line_ids' in fields:
            res['variant_line_ids'] = [
                (0, 0, {}),
                (0, 0, {}),
                (0, 0, {}),
            ]

        return res

    def action_create_variants(self):
        """Create product variants and BOM records for each size+colorway pair.

        If called from a Sale Order (sale_order_id is set), the SO lines for
        this product template are also expanded — one line per variant created.
        """
        self.ensure_one()

        if not self.variant_line_ids:
            return {'type': 'ir.actions.act_window_close'}

        Attribute = self.env['product.attribute']
        AttributeValue = self.env['product.attribute.value']
        MrpBom = self.env['mrp.bom']
        StyleSize = self.env['style.size']
        StyleColorway = self.env['style.colorway']

        # Resolve customer from lead or sale order
        partner = (
            self.lead_id.partner_id
            or (self.sale_order_id.partner_id if self.sale_order_id else False)
        )

        # Resolve Production Service for BOMs created from the Production tab
        production_service = self.env['product.product'].search([
            ('name', '=', 'Production Service')
        ], limit=1)

        size_attr = Attribute.search([('name', '=', 'Size')], limit=1)
        if not size_attr:
            size_attr = Attribute.create({'name': 'Size', 'create_variant': 'always'})

        colorway_attr = Attribute.search([('name', '=', 'Colorway')], limit=1)
        if not colorway_attr:
            colorway_attr = Attribute.create({'name': 'Colorway', 'create_variant': 'always'})

        # Track all (variant, size_name, colorway_name) created in this run
        created_variants = []

        for line in self.variant_line_ids:
            if not line.size_name or not line.colorway_name:
                continue

            size_name = line.size_name.strip()
            colorway_name = line.colorway_name.strip()

            # Get or create attribute values
            size_val = AttributeValue.search([
                ('attribute_id', '=', size_attr.id),
                ('name', '=', size_name),
            ], limit=1)
            if not size_val:
                size_val = AttributeValue.create({
                    'attribute_id': size_attr.id,
                    'name': size_name,
                })

            colorway_val = AttributeValue.search([
                ('attribute_id', '=', colorway_attr.id),
                ('name', '=', colorway_name),
            ], limit=1)
            if not colorway_val:
                colorway_val = AttributeValue.create({
                    'attribute_id': colorway_attr.id,
                    'name': colorway_name,
                })

            # Create the product variant (handles attribute lines + PTAVs internally)
            variant = MrpBom._find_or_create_specific_garment_variant(
                self.product_id, colorway_val, size_val
            )
            if variant:
                created_variants.append((variant, size_name, colorway_name))

            # Create BOM for this combination if one doesn't already exist
            existing_bom = MrpBom.search([
                ('product_tmpl_id', '=', self.product_id.id),
                ('colorway_id', '=', colorway_val.id),
                ('size_id', '=', size_val.id),
            ], limit=1)
            if not existing_bom:
                MrpBom.create({
                    'product_tmpl_id': self.product_id.id,
                    'colorway_id': colorway_val.id,
                    'size_id': size_val.id,
                    'partner_id': partner.id if partner else False,
                    'rel_service': production_service.id if production_service else False,
                })
            else:
                update_vals = {}
                if not existing_bom.partner_id and partner:
                    update_vals['partner_id'] = partner.id
                if not existing_bom.rel_service and production_service:
                    update_vals['rel_service'] = production_service.id
                if update_vals:
                    existing_bom.write(update_vals)

            # Ensure style.size record exists for the production grid
            if not StyleSize.search([
                ('product_tmpl_id', '=', self.product_id.id),
                ('size_id', '=', size_val.id),
            ], limit=1):
                StyleSize.create({
                    'product_tmpl_id': self.product_id.id,
                    'size_id': size_val.id,
                    'active': True,
                })

            # Ensure style.colorway record exists for the production grid
            if not StyleColorway.search([
                ('product_tmpl_id', '=', self.product_id.id),
                ('colorway_id', '=', colorway_val.id),
            ], limit=1):
                StyleColorway.create({
                    'product_tmpl_id': self.product_id.id,
                    'colorway_id': colorway_val.id,
                    'active': True,
                })

        # If called from a Sale Order, expand SO lines to one line per variant
        if self.sale_order_id and created_variants:
            self._expand_so_lines(created_variants)

        return {'type': 'ir.actions.act_window_close'}

    def _expand_so_lines(self, created_variants):
        """Replace or expand SO lines for this product template with one line per variant."""
        SaleOrderLine = self.env['sale.order.line']

        # Find existing lines on this SO that belong to this product template
        existing_lines = SaleOrderLine.search([
            ('order_id', '=', self.sale_order_id.id),
            ('product_id.product_tmpl_id', '=', self.product_id.id),
        ], order='sequence, id')

        if not existing_lines:
            # No existing lines — add new lines for all variants
            ref_line = None
        else:
            ref_line = existing_lines[0]

        # Fields to copy from the reference line
        def _base_vals(ref, variant, size_name, colorway_name):
            vals = {
                'order_id': self.sale_order_id.id,
                'product_id': variant.id,
                'product_uom_qty': ref.product_uom_qty if ref else 1.0,
                'price_unit': ref.price_unit if ref else 0.0,
                'size': size_name,
                'colorway': colorway_name,
            }
            # Copy custom fields if present on the reference line
            for field in ('rel_service', 'style_family', 'crm_child_lead_id',
                          'sample', 'revision', 'sequence'):
                if ref and getattr(ref, field, None):
                    val = getattr(ref, field)
                    vals[field] = val.id if hasattr(val, 'id') else val
            return vals

        # Update the first existing line to the first variant; add lines for the rest
        for idx, (variant, size_name, colorway_name) in enumerate(created_variants):
            if idx == 0 and existing_lines:
                # Update the first matching line in place
                existing_lines[0].write({
                    'product_id': variant.id,
                    'size': size_name,
                    'colorway': colorway_name,
                })
            else:
                SaleOrderLine.create(_base_vals(ref_line, variant, size_name, colorway_name))

        # Remove any leftover original lines (beyond the first) that were not updated
        if len(existing_lines) > 1:
            existing_lines[1:].unlink()


class CrmLeadVariantWizardLine(models.TransientModel):
    _name = 'crm.lead.variant.wizard.line'
    _description = 'Variant Wizard Line'

    wizard_id = fields.Many2one(
        'crm.lead.variant.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )

    size_name = fields.Char(
        string='Size',
        help='Enter size (e.g., S, M, L, XL)'
    )

    colorway_name = fields.Char(
        string='Colorway',
        help='Enter colorway/color (e.g., Red, Blue, Black)'
    )
