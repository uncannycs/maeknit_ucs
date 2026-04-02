from odoo import models, fields, api, _
import logging

class MrpProductionProduceAllWizard(models.TransientModel):
    _name = "maeknit.mrp.produce.all.wizard"
    _description = "Confirm Produce All and optionally update BOM"

    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True)
    is_swatch_mo = fields.Boolean(related='production_id.is_swatch_mo')
    calibration_data = fields.Json(related='production_id.calibration_data', readonly=False)
    update_bom = fields.Selection(
        [('yes', 'Yes'), ('no', 'No')],
        string="Update BOM before producing?",
        default='yes',
        required=True,
        help="When set to Yes, the wizard will update the BOM and BOM Request "
             "with the current MO components before producing all.",
    )

    def _sync_swatch_to_parent(self, swatch_mo, parent_mo, component_snapshot=None, structure_snapshot=None):
        """Copy all data from a completed swatch MO back to its parent garment MO."""

        # --- Stitch Density (calibration_data) ---
        cal_data = swatch_mo.calibration_data
        if isinstance(cal_data, dict) and any(v for v in cal_data.values() if v):
            parent_cal = dict(parent_mo.calibration_data) if isinstance(parent_mo.calibration_data, dict) else {}
            parent_cal.update(cal_data)
            parent_cal['hasPreExistingSwatch'] = True
            parent_cal['calibrationSwatchId'] = swatch_mo.product_id.id
            parent_mo.write({'calibration_data': parent_cal})
            logging.info("[PRODUCE ALL] Synced calibration_data from %s to %s", swatch_mo.name, parent_mo.name)

        # Unblock parent
        parent_mo.write({'is_blocked_for_calibration': False})

        # --- JSON data fields stored directly on MO ---
        json_fields = ['whole_cad_data', 'measurement_widget_data', 'structure_cad_data']
        json_vals = {}
        for fname in json_fields:
            val = getattr(swatch_mo, fname, None)
            if val:
                json_vals[fname] = val
        if json_vals:
            parent_mo.write(json_vals)
            logging.info("[PRODUCE ALL] Synced JSON fields %s to parent %s", list(json_vals.keys()), parent_mo.name)

        # --- Sketch (excalidraw_data) — computed, reads from bom_request if linked ---
        sketch = getattr(swatch_mo, 'excalidraw_data', None)
        if sketch:
            parent_mo.excalidraw_data = sketch
            logging.info("[PRODUCE ALL] Synced excalidraw sketch to parent %s", parent_mo.name)

        # --- Garment construction ---
        gc = getattr(swatch_mo, 'garment_construction_data', None)
        if gc:
            parent_mo.garment_construction_data = gc
            logging.info("[PRODUCE ALL] Synced garment_construction_data to parent %s", parent_mo.name)

        # --- Artwork — computed, reads from bom_request if linked ---
        artwork = getattr(swatch_mo, 'artwork_data', None)
        if artwork:
            parent_mo.artwork_data = artwork
            logging.info("[PRODUCE ALL] Synced artwork_data to parent %s", parent_mo.name)

        # --- Structure lines (from snapshot taken before _update_bom_request_from_mo wiped them) ---
        # Build a remap of old swatch structure line IDs → new parent structure line IDs
        # so component moves can reference the correct structure line on the parent.
        structure_id_remap = {}  # {swatch_sl_id: parent_sl_id}
        if structure_snapshot:
            parent_mo.structure_ids.unlink()
            for s in structure_snapshot:
                new_sl = self.env['maeknit.structure.line'].with_context(skip_bom_request_cad_sync=True).create({
                    'production_id': parent_mo.id,
                    'name': s['name'],
                    'description': s['description'],
                    'sequence': s['sequence'],
                })
                if s.get('swatch_sl_id'):
                    structure_id_remap[s['swatch_sl_id']] = new_sl.id
            logging.info("[PRODUCE ALL] Synced %d structure lines to parent %s (remap: %s)",
                         len(structure_snapshot), parent_mo.name, structure_id_remap)

        # --- Components: use pre-mark_done snapshot ---
        if component_snapshot:
            logging.info("[COMP SYNC] Using snapshot of %d components", len(component_snapshot))

            try:
                parent_mo.do_unreserve()
            except Exception as e:
                logging.warning("[COMP SYNC] do_unreserve failed: %s", e)

            not_done = parent_mo.move_raw_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
            logging.info("[COMP SYNC] removing %d existing parent moves, adding %d from snapshot",
                         len(not_done), len(component_snapshot))

            move_commands = [(2, m.id, 0) for m in not_done]
            for vals in component_snapshot:
                v = dict(vals)
                # Remap structure_id from deleted swatch line → new parent line
                if v.get('structure_id') and v['structure_id'] in structure_id_remap:
                    v['structure_id'] = structure_id_remap[v['structure_id']]
                elif v.get('structure_id') and v['structure_id'] not in structure_id_remap:
                    v['structure_id'] = False  # stale reference — clear it
                move_commands.append((0, 0, v))

            try:
                parent_mo.write({'move_raw_ids': move_commands})
                logging.info("[COMP SYNC] write OK — parent now has %d move_raw_ids", len(parent_mo.move_raw_ids))
            except Exception as e:
                logging.error("[COMP SYNC] write failed: %s", e)

            try:
                parent_mo.action_assign()
            except Exception as e:
                logging.warning("[COMP SYNC] action_assign failed: %s", e)

            # Sync components to parent BOM request directly — NOT via _update_bom_request_from_mo
            # because that also does (5,0,0) on structure_ids, wiping the structure we just created.
            if parent_mo.bom_request_id:
                try:
                    bom_cmds = [(5, 0, 0)]
                    for s in component_snapshot:
                        old_sid = s.get('structure_id')
                        new_sid = structure_id_remap.get(old_sid, False) if old_sid else False
                        bom_cmds.append((0, 0, {
                            'product_id': s['product_id'],
                            'product_qty': s['product_uom_qty'],
                            'product_uom_id': s['product_uom'],
                            'sequence': s['sequence'],
                            'ply': s['x_ply'],
                            'left_carrier': s['left_carrier'],
                            'right_carrier': s['right_carrier'],
                            'structure_id': new_sid,
                        }))
                    parent_mo.bom_request_id.write({'bom_line_ids': bom_cmds})
                    logging.info("[COMP SYNC] BOM request %s updated", parent_mo.bom_request_id.name)
                except Exception as e:
                    logging.error("[COMP SYNC] BOM request update failed: %s", e)
        else:
            logging.warning("[COMP SYNC] No component snapshot — nothing to sync")

    def action_confirm(self):
        """Produce all and optionally sync BOM/BOM Request data."""
        self.ensure_one()
        production = self.production_id
        parent_mo = production.parent_garment_mo_id

        # Ensure qty_producing is set — Odoo requires this before marking done
        if not production.qty_producing:
            production.qty_producing = production.product_qty

        # For tracked components, reservation creates move lines with no lot.
        # Auto-assign the single selected lot to those lines so validation passes.
        for move in production.move_raw_ids.filtered(
            lambda m: m.state not in ('done', 'cancel') and m.has_tracking != 'none'
        ):
            no_lot_lines = move.move_line_ids.filtered(
                lambda ml: ml.quantity > 0 and not ml.lot_id
            )
            if not no_lot_lines:
                continue
            if len(move.lot_ids) == 1:
                logging.info(
                    "[PRODUCE ALL] Auto-assigning lot '%s' to %d no-lot move_line(s) on move %s",
                    move.lot_ids.name, len(no_lot_lines), move.id,
                )
                no_lot_lines.write({'lot_id': move.lot_ids.id})
            else:
                # No lot selected or multiple lots — zero out the no-lot lines
                logging.warning(
                    "[PRODUCE ALL] Move %s has %d no-lot line(s) but lot_ids=%s — zeroing them out",
                    move.id, len(no_lot_lines), move.lot_ids.mapped('name'),
                )
                no_lot_lines.write({'quantity': 0.0})

        # Snapshot swatch data FIRST — before _update_bom_request_from_mo or button_mark_done
        # wipes structure lines (via (5,0,0) on bom_request.structure_ids) or cancels moves.
        swatch_component_snapshot = []
        swatch_structure_snapshot = []
        if parent_mo:
            ref_moves = production.move_raw_ids.filtered(lambda m: m.state != 'cancel' and not m.scrap_id)
            for move in ref_moves:
                swatch_component_snapshot.append({
                    'name': move.product_id.display_name,
                    'product_id': move.product_id.id,
                    'product_uom_qty': move.product_uom_qty,
                    'product_uom': move.product_uom.id,
                    'picking_type_id': parent_mo.picking_type_id.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': parent_mo.company_id.id,
                    'sequence': move.sequence,
                    'x_ply': move.x_ply,
                    'left_carrier': move.left_carrier,
                    'right_carrier': move.right_carrier,
                    'structure_id': move.structure_id.id if move.structure_id else False,
                })

            for sl in production.structure_ids:
                swatch_structure_snapshot.append({
                    'swatch_sl_id': sl.id,   # original ID — used to remap component structure_id
                    'name': sl.name,
                    'description': sl.description,
                    'sequence': sl.sequence,
                })

            logging.info("[COMP SYNC] Snapshot: %d moves, %d structure lines",
                         len(swatch_component_snapshot), len(swatch_structure_snapshot))

        if self.update_bom == 'yes':
            production._update_bom_request_from_mo()

        # skip_stitch_density_wizard: data collected in this dialog / synced below
        # skip_immediate: qty_producing already set above
        res = production.with_context(
            skip_stitch_density_wizard=True,
            skip_immediate=True,
        ).button_mark_done()
        if res and res is not True:
            return res

        # If this is a swatch MO with a parent, sync all data and navigate there
        if parent_mo:
            self._sync_swatch_to_parent(
                production, parent_mo,
                component_snapshot=swatch_component_snapshot,
                structure_snapshot=swatch_structure_snapshot,
            )
            logging.info("[PRODUCE ALL] Navigating to parent MO %s after swatch sync", parent_mo.name)
            return {
                'type': 'ir.actions.act_window',
                'name': _('Manufacturing Order'),
                'res_model': 'mrp.production',
                'res_id': parent_mo.id,
                'view_mode': 'form',
                'target': 'current',
            }

        return {'type': 'ir.actions.act_window_close'}
