from odoo import models, fields, api
import logging


class ToileDocWizard(models.TransientModel):
    _name = 'toile.doc.wizard'
    _description = 'Toile Documentation — Record Actual Measurements'

    workorder_id = fields.Many2one('mrp.workorder', required=True, ondelete='cascade')
    production_id = fields.Many2one('mrp.production', required=True)

    # Panel structure — read from parent MO so the JS widget can build the panel/point UI
    measurement_widget_data = fields.Json(
        related='production_id.measurement_widget_data',
        readonly=True,
    )
    # Computed version with image URLs restored from attachments (for widget display)
    measurement_widget_data_with_images = fields.Json(
        related='production_id.measurement_widget_data_with_images',
        readonly=True,
    )

    # The actual measurements being entered; bound to toile_doc_widget in the form view
    toile_doc_data = fields.Json(default=lambda self: {})

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        prod_id = self.env.context.get('default_production_id')
        if prod_id:
            prod = self.env['mrp.production'].browse(prod_id)
            # Pre-load any existing actuals so the widget shows prior versions
            res['toile_doc_data'] = prod.toile_doc_data or {}
        return res

    def _commit_pending_actuals(self):
        """If JS left __pendingActuals in toile_doc_data, commit them as a versioned
        entry into the panel's actualVersions list."""
        pending = (self.toile_doc_data or {}).get('__pendingActuals')
        if not pending:
            return
        panel_id = pending.get('panelId')
        raw_measurements = pending.get('measurements') or {}
        submitted_at = pending.get('submitted_at', '')
        if not panel_id or not any(v not in (None, '', 0) for v in raw_measurements.values()):
            return

        doc = dict(self.toile_doc_data or {})
        panel_doc = doc.get(panel_id) or {}
        if not isinstance(panel_doc, dict):
            panel_doc = {}
        actual_versions = list(panel_doc.get('actualVersions') or [])
        next_version = max((v['version'] for v in actual_versions), default=0) + 1

        measurements = {}
        for point, val in raw_measurements.items():
            try:
                measurements[point] = round(float(val), 3) if val not in (None, '') else None
            except (TypeError, ValueError):
                measurements[point] = None

        actual_versions.append({
            'version': next_version,
            'measurements': measurements,
            'submitted_at': submitted_at,
        })
        panel_doc['actualVersions'] = actual_versions
        panel_doc['selectedVersion'] = next_version
        doc[panel_id] = panel_doc
        # Write back so _save_actuals_to_mo picks it up
        self.toile_doc_data = doc
        logging.info("[ToileDoc] Committed actual v%s for panel %s", next_version, panel_id)

    def _save_actuals_to_mo(self):
        """Persist toile_doc_data from the wizard back to the MO, stripping
        all __ helper keys before writing."""
        doc = dict(self.toile_doc_data or {})
        doc.pop('__pendingNewRequests', None)
        doc.pop('__pendingActuals', None)
        self.production_id.toile_doc_data = doc

    def _apply_new_requests_to_panel_cad(self):
        """If the widget embedded __pendingNewRequests, write a new panelRequest
        version into measurement_widget_data on the MO."""
        pending = (self.toile_doc_data or {}).get('__pendingNewRequests')
        if not pending:
            return
        panel_id = pending.get('panelId')
        overrides = pending.get('overrides') or {}
        if not panel_id or not overrides:
            return

        prod = self.production_id
        panel_cad = dict(prod.measurement_widget_data or {})
        panel_src = panel_cad.get(panel_id)
        if not panel_src:
            return

        # Compute current last-request values
        base = {m['point']: float(m.get('value') or 0)
                for m in (panel_src.get('measurements') or [])}
        panel_requests = panel_src.get('panelRequests') or []
        latest_version = max((r['version'] for r in panel_requests), default=1)

        def compute_at_version(version):
            if version <= 1:
                return dict(base)
            req = next((r for r in panel_requests if r['version'] == version), None)
            if not req:
                return dict(base)
            base_vals = compute_at_version(req.get('baseVersion', version - 1))
            result = dict(base_vals)
            for point, delta in (req.get('changes') or {}).items():
                if point in result:
                    result[point] = round(result[point] + float(delta or 0), 3)
            return result

        last_req_values = compute_at_version(latest_version)

        edited_points = set(pending.get('editedPoints') or overrides.keys())
        changes = {}
        for point in edited_points:
            new_val = overrides.get(point)
            try:
                new_val_f = round(float(new_val), 3)
            except (TypeError, ValueError):
                continue
            last_val = last_req_values.get(point, 0)
            delta = round(new_val_f - last_val, 3)
            if delta != 0:
                changes[point] = delta

        if not changes:
            return

        import datetime
        new_version = latest_version + 1
        panel_src['panelRequests'] = panel_requests + [{
            'version': new_version,
            'baseVersion': latest_version,
            'changes': changes,
            'created_at': datetime.date.today().isoformat(),
        }]
        panel_cad[panel_id] = panel_src
        prod.measurement_widget_data = panel_cad
        logging.info("[ToileDoc] Wrote new panelRequest v%s for panel %s on MO %s",
                     new_version, panel_id, prod.name)

    def action_approve_for_shipment(self):
        """Commit pending actuals, save to MO, then produce (mark done)."""
        self._commit_pending_actuals()
        self._save_actuals_to_mo()
        prod = self.production_id
        if not prod.qty_producing:
            prod.qty_producing = prod.product_qty
        prod.with_context(skip_immediate=True).button_mark_done()
        return {'type': 'ir.actions.act_window_close'}

    def action_remanufacture(self):
        """Commit pending actuals, write new requests into Panel CAD, save to MO,
        mark the documentation WO as done, then open Re-manufacturing wizard."""
        self._commit_pending_actuals()
        self._apply_new_requests_to_panel_cad()
        self._save_actuals_to_mo()
        # Mark the documentation/spec-garment work order as done
        doc_wo = self.workorder_id
        if doc_wo and doc_wo.state not in ('done', 'cancel'):
            if doc_wo.state == 'pending':
                doc_wo.button_start()
            doc_wo.button_finish()
        return self.production_id.action_remanufacture()
