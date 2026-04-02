"""
Tests for the Maeknit BOM-MFG sync flow.

Covers:
  - Swatch → Toile copy (_copy_swatch_data)
  - Dev ← Swatch/Toile wizard sync (_sync_from_mo)
  - Sync wizard available pools and preview
  - Component sync on draft vs. confirmed Dev MOs
"""
import json
from odoo.tests import TransactionCase, tagged


@tagged('-at_install', 'post_install', 'maeknit_sync')
class TestMaeknitSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env

        # ── Service products ──────────────────────────────────────────────────
        cls.svc_swatch = env['product.product'].search(
            [('product_tmpl_id.name', '=', 'Swatch Service')], limit=1)
        cls.svc_toile = env['product.product'].search(
            [('product_tmpl_id.name', '=', 'Toile Service')], limit=1)
        cls.svc_dev = env['product.product'].search(
            [('product_tmpl_id.name', '=', 'Development Service')], limit=1)

        # ── Manufacturing picking type + locations ────────────────────────────
        cls.picking_type = env['stock.picking.type'].search(
            [('code', '=', 'mrp_operation')], limit=1)
        cls.loc_src = cls.picking_type.default_location_src_id
        cls.loc_dest = env['stock.location'].search(
            [('usage', '=', 'production')], limit=1)

        # ── Fresh test product with NO BOM (avoids auto-created raw moves) ────
        uom_unit = env['uom.uom'].search(
            [('category_id.name', '=', 'Unit'), ('uom_type', '=', 'reference')], limit=1
        ) or env['uom.uom'].search([], limit=1)
        cls.uom = uom_unit

        # garment product (category='garment') used as MO product_id
        cls.garment = env['product.product'].create({
            'name': '__test_garment_sync__',
            'type': 'consu',
            'uom_id': uom_unit.id,
            'uom_po_id': uom_unit.id,
            'product_category': 'garment',
        })
        # swatch-category product — required so dev_swatch_mo_ids domain matches
        cls.swatch_product = env['product.product'].create({
            'name': '__test_swatch_product_sync__',
            'type': 'consu',
            'uom_id': uom_unit.id,
            'uom_po_id': uom_unit.id,
            'product_category': 'swatch',
        })
        # consumable component for stock move tests
        cls.component = env['product.product'].create({
            'name': '__test_component_sync__',
            'type': 'consu',
            'uom_id': uom_unit.id,
            'uom_po_id': uom_unit.id,
        })

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_mo(self, service, **extra):
        """Create a minimal MO with the given service type and fresh test product."""
        vals = {
            'product_id': self.garment.id,
            'product_qty': 1,
            'product_uom_id': self.uom.id,
            'rel_service': service.id,
            'picking_type_id': self.picking_type.id,
            'location_src_id': self.loc_src.id,
            'location_dest_id': self.loc_dest.id,
        }
        vals.update(extra)
        return self.env['mrp.production'].create(vals)

    def _add_component(self, mo, qty=1.0):
        """Add a raw material move to an MO."""
        self.env['stock.move'].create({
            'name': self.component.display_name,
            'product_id': self.component.id,
            'product_uom_qty': qty,
            'product_uom': self.uom.id,
            'raw_material_production_id': mo.id,
            'picking_type_id': self.picking_type.id,
            'location_id': self.loc_src.id,
            'location_dest_id': self.loc_dest.id,
            'company_id': self.env.company.id,
        })

    def _add_structure_line(self, mo, name='Test Panel'):
        return self.env['maeknit.structure.line'].create({
            'production_id': mo.id,
            'name': name,
            'sequence': 10,
        })

    def _raw_moves(self, mo):
        """Return only the test-component raw moves (filters out BOM-generated ones)."""
        return mo.move_raw_ids.filtered(
            lambda m: m.product_id == self.component and not m.scrap_id
        )

    def _force_state(self, mo, state):
        """Set MO state directly in the ORM cache, bypassing the stored compute."""
        self.env.cache.set(mo, mo._fields['state'], state)

    # ── MO type detection ─────────────────────────────────────────────────────

    def test_mo_type_flags(self):
        swatch = self._make_mo(self.svc_swatch)
        toile = self._make_mo(self.svc_toile)
        dev = self._make_mo(self.svc_dev)

        # store=False computed fields may need cache refresh after creation hooks run
        swatch.invalidate_recordset(['is_swatch_mo', 'is_toile_mo', 'is_dev_mo'])
        toile.invalidate_recordset(['is_swatch_mo', 'is_toile_mo', 'is_dev_mo'])
        dev.invalidate_recordset(['is_swatch_mo', 'is_toile_mo', 'is_dev_mo'])

        self.assertTrue(swatch.is_swatch_mo)
        self.assertFalse(swatch.is_toile_mo)
        self.assertFalse(swatch.is_dev_mo)

        self.assertTrue(toile.is_toile_mo)
        self.assertFalse(toile.is_swatch_mo)
        self.assertFalse(toile.is_dev_mo)

        self.assertTrue(dev.is_dev_mo)
        self.assertFalse(dev.is_swatch_mo)
        self.assertFalse(dev.is_toile_mo)

    # ── Swatch → Toile copy (_copy_swatch_data) ───────────────────────────────

    def test_copy_swatch_data_scalars(self):
        """_copy_swatch_data should copy all scalar/JSON fields from swatch to toile."""
        swatch = self._make_mo(self.svc_swatch)
        toile = self._make_mo(self.svc_toile)

        sketch_data = {'elements': [{'id': '1'}], 'files': {}}
        artwork_json = json.dumps({'elements': [{'id': '2'}], 'files': {}})

        swatch.write({
            'structure_cad_data':                  {'panels': ['A']},
            'excalidraw_data_standalone':          sketch_data,
            'artwork_data_standalone':             artwork_json,   # Text field — JSON string
            'whole_cad_data':                      {'elements': [{'id': '3'}], 'files': {}},
            'garment_construction_data_standalone': {'elements': [{'id': '4'}], 'files': {}},
            'calibration_data':                    {'gauge': 7, 'rows': []},
        })

        toile._copy_swatch_data(swatch)

        self.assertEqual(toile.structure_cad_data, {'panels': ['A']})
        self.assertEqual(toile.excalidraw_data_standalone, sketch_data)
        self.assertEqual(toile.artwork_data_standalone, artwork_json)
        self.assertEqual(toile.calibration_data, {'gauge': 7, 'rows': []})

    def test_copy_swatch_data_structure_lines(self):
        """_copy_swatch_data should copy structure lines."""
        swatch = self._make_mo(self.svc_swatch)
        self._add_structure_line(swatch, 'Body')
        self._add_structure_line(swatch, 'Sleeve')
        toile = self._make_mo(self.svc_toile)

        toile._copy_swatch_data(swatch)

        names = toile.structure_ids.mapped('name')
        self.assertIn('Body', names)
        self.assertIn('Sleeve', names)
        self.assertEqual(len(toile.structure_ids), 2)

    def test_copy_swatch_data_replaces_existing_structure(self):
        """_copy_swatch_data should clear old structure lines before copying."""
        swatch = self._make_mo(self.svc_swatch)
        self._add_structure_line(swatch, 'New Panel')
        toile = self._make_mo(self.svc_toile)
        self._add_structure_line(toile, 'Old Panel')

        toile._copy_swatch_data(swatch)

        names = toile.structure_ids.mapped('name')
        self.assertNotIn('Old Panel', names)
        self.assertIn('New Panel', names)

    # ── Dev ← Source sync (_sync_from_mo) ─────────────────────────────────────

    def test_sync_from_mo_returns_results_dict(self):
        """_sync_from_mo should return a results dict with known keys."""
        swatch = self._make_mo(self.svc_swatch)
        dev = self._make_mo(self.svc_dev)

        results = dev._sync_from_mo(swatch)

        expected_keys = {
            'structure_cad', 'artwork', 'sketch',
            'whole_cad', 'garment_construction', 'stitch_density',
            'structure_lines', 'components',
        }
        self.assertEqual(set(results.keys()), expected_keys)

    def test_sync_from_mo_scalar_fields(self):
        """_sync_from_mo should write all scalar/JSON fields to the Dev MO."""
        swatch = self._make_mo(self.svc_swatch)
        dev = self._make_mo(self.svc_dev)

        artwork_json = json.dumps({'elements': [{'id': 'art'}], 'files': {}})
        swatch.write({
            'structure_cad_data':                  {'panels': ['X']},
            'excalidraw_data_standalone':          {'elements': [], 'files': {}},
            'artwork_data_standalone':             artwork_json,
            'whole_cad_data':                      {'elements': [], 'files': {}},
            'garment_construction_data_standalone': {'elements': [], 'files': {}},
            'calibration_data':                    {'gauge': 5},
        })

        results = dev._sync_from_mo(swatch)

        self.assertEqual(dev.structure_cad_data, {'panels': ['X']})
        self.assertEqual(dev.artwork_data_standalone, artwork_json)
        self.assertEqual(dev.calibration_data, {'gauge': 5})
        self.assertTrue(results['structure_cad'].startswith('OK'))
        self.assertTrue(results['artwork'].startswith('OK'))
        self.assertTrue(results['stitch_density'].startswith('OK'))

    def test_sync_from_mo_empty_fields_marked_empty(self):
        """Result values should say EMPTY when source has no data."""
        swatch = self._make_mo(self.svc_swatch)
        dev = self._make_mo(self.svc_dev)

        results = dev._sync_from_mo(swatch)

        self.assertEqual(results['artwork'], 'EMPTY')
        self.assertEqual(results['sketch'], 'EMPTY')

    def test_sync_from_mo_structure_lines(self):
        """_sync_from_mo should replace structure lines on the Dev MO."""
        swatch = self._make_mo(self.svc_swatch)
        self._add_structure_line(swatch, 'Swatch Body')
        dev = self._make_mo(self.svc_dev)
        self._add_structure_line(dev, 'Old Dev Panel')

        results = dev._sync_from_mo(swatch)

        names = dev.structure_ids.mapped('name')
        self.assertIn('Swatch Body', names)
        self.assertNotIn('Old Dev Panel', names)
        self.assertIn('OK', results['structure_lines'])

    def test_sync_from_mo_components_draft(self):
        """Components should be copied when Dev MO is in draft state."""
        swatch = self._make_mo(self.svc_swatch)
        self._add_component(swatch, qty=3.0)
        dev = self._make_mo(self.svc_dev)

        self.assertEqual(dev.state, 'draft')
        results = dev._sync_from_mo(swatch)

        self.assertIn('OK', results['components'])
        comp_moves = self._raw_moves(dev)
        self.assertEqual(len(comp_moves), 1)
        self.assertAlmostEqual(comp_moves[0].product_uom_qty, 3.0)

    def test_sync_from_mo_components_skipped_when_not_draft(self):
        """Components should be skipped when Dev MO is not in draft state."""
        swatch = self._make_mo(self.svc_swatch)
        self._add_component(swatch, qty=2.0)
        dev = self._make_mo(self.svc_dev)
        self._force_state(dev, 'confirmed')

        results = dev._sync_from_mo(swatch)

        self.assertIn('SKIPPED', results['components'])

    def test_sync_from_mo_clears_old_components_on_draft(self):
        """Existing draft components should be replaced by synced ones."""
        swatch = self._make_mo(self.svc_swatch)
        self._add_component(swatch, qty=5.0)
        dev = self._make_mo(self.svc_dev)
        self._add_component(dev, qty=99.0)  # old component — should be gone after sync

        dev._sync_from_mo(swatch)

        comp_moves = self._raw_moves(dev)
        self.assertEqual(len(comp_moves), 1, "Should have exactly one test-component move after sync")
        self.assertAlmostEqual(comp_moves[0].product_uom_qty, 5.0)

    def test_sync_from_toile(self):
        """_sync_from_mo should work with a Toile as the source (not just Swatch)."""
        toile = self._make_mo(self.svc_toile)
        artwork_json = json.dumps({'elements': [{'id': 'toile_art'}], 'files': {}})
        toile.write({
            'structure_cad_data':     {'panels': ['T']},
            'calibration_data':       {'gauge': 12},
            'artwork_data_standalone': artwork_json,
        })
        self._add_structure_line(toile, 'Toile Body')
        dev = self._make_mo(self.svc_dev)

        results = dev._sync_from_mo(toile)

        self.assertEqual(dev.structure_cad_data, {'panels': ['T']})
        self.assertEqual(dev.calibration_data, {'gauge': 12})
        self.assertTrue(results['artwork'].startswith('OK'))

    # ── Sync wizard ───────────────────────────────────────────────────────────

    def test_wizard_available_pools(self):
        """Wizard should expose the correct swatch and toile pools for the Dev MO."""
        dev = self._make_mo(self.svc_dev)
        # Use swatch_product (product_category='swatch') so dev_swatch_mo_ids domain matches
        swatch1 = self._make_mo(self.svc_swatch, parent_garment_mo_id=dev.id,
                                product_id=self.swatch_product.id,
                                product_uom_id=self.uom.id)
        swatch2 = self._make_mo(self.svc_swatch, parent_garment_mo_id=dev.id,
                                product_id=self.swatch_product.id,
                                product_uom_id=self.uom.id)
        toile = self._make_mo(self.svc_toile, dev_mo_id=dev.id)

        wizard = self.env['maeknit.sync.from.mo.wizard'].create({
            'target_mo_id': dev.id,
        })

        self.assertIn(swatch1, wizard.available_swatch_ids)
        self.assertIn(swatch2, wizard.available_swatch_ids)
        self.assertIn(toile, wizard.available_toile_ids)
        self.assertNotIn(toile, wizard.available_swatch_ids)

    def test_wizard_preview_shows_checkmarks(self):
        """Preview should show ✓ for fields that exist and ○ for empty ones."""
        swatch = self._make_mo(self.svc_swatch)
        swatch.write({
            'calibration_data': {'gauge': 7},
            'structure_cad_data': {'panels': ['A']},
        })
        dev = self._make_mo(self.svc_dev)

        wizard = self.env['maeknit.sync.from.mo.wizard'].create({
            'target_mo_id': dev.id,
            'source_type': 'swatch',
            'swatch_source_id': swatch.id,
        })

        preview = wizard.sync_preview
        self.assertIn('✓', preview, "Should have at least one ✓ for fields with data")
        self.assertIn('○', preview, "Should have ○ for empty fields")
        self.assertIn('Structure CAD', preview)
        self.assertIn('Stitch Density', preview)

    def test_wizard_preview_empty_when_no_source(self):
        """Preview should show a placeholder when no source is selected."""
        dev = self._make_mo(self.svc_dev)
        wizard = self.env['maeknit.sync.from.mo.wizard'].create({
            'target_mo_id': dev.id,
        })
        self.assertIn('Select a source', wizard.sync_preview)

    def test_wizard_action_sync_executes(self):
        """action_sync should complete without error and return a notification action."""
        swatch = self._make_mo(self.svc_swatch)
        swatch.write({'calibration_data': {'gauge': 7}})
        dev = self._make_mo(self.svc_dev)

        wizard = self.env['maeknit.sync.from.mo.wizard'].create({
            'target_mo_id': dev.id,
            'source_type': 'swatch',
            'swatch_source_id': swatch.id,
        })
        result = wizard.action_sync()

        self.assertEqual(result.get('type'), 'ir.actions.client')
        self.assertEqual(result.get('tag'), 'display_notification')
        self.assertEqual(dev.calibration_data, {'gauge': 7})

    def test_wizard_action_sync_no_source_raises(self):
        """action_sync should raise UserError when no source is selected."""
        from odoo.exceptions import UserError
        dev = self._make_mo(self.svc_dev)
        wizard = self.env['maeknit.sync.from.mo.wizard'].create({
            'target_mo_id': dev.id,
            'source_type': 'swatch',
        })
        with self.assertRaises(UserError):
            wizard.action_sync()

    # ── Full workflow: Swatch → Toile → Dev ───────────────────────────────────

    def test_full_workflow_swatch_to_toile_to_dev(self):
        """End-to-end: data flows Swatch → Toile (copy) → Dev (wizard sync)."""
        # 1. Swatch with data
        swatch = self._make_mo(self.svc_swatch)
        calib = {'gauge': 10, 'rows': [1, 2, 3]}
        swatch.write({
            'structure_cad_data': {'panels': ['Body', 'Sleeve']},
            'calibration_data':   calib,
        })
        self._add_structure_line(swatch, 'Body')
        self._add_structure_line(swatch, 'Sleeve')
        self._add_component(swatch, qty=2.0)

        # 2. Toile copies swatch data
        toile = self._make_mo(self.svc_toile)
        toile._copy_swatch_data(swatch)
        self.assertEqual(toile.structure_cad_data, {'panels': ['Body', 'Sleeve']})
        self.assertEqual(len(toile.structure_ids), 2)
        self.assertEqual(toile.calibration_data, calib)

        # 3. Dev MO syncs from swatch via wizard
        dev = self._make_mo(self.svc_dev)
        wizard = self.env['maeknit.sync.from.mo.wizard'].create({
            'target_mo_id': dev.id,
            'source_type': 'swatch',
            'swatch_source_id': swatch.id,
        })
        wizard.action_sync()

        self.assertEqual(dev.calibration_data, calib)
        self.assertEqual(dev.structure_cad_data, {'panels': ['Body', 'Sleeve']})
        self.assertIn('Body', dev.structure_ids.mapped('name'))
        # Component was on swatch (draft dev) — should be copied
        comp_moves = self._raw_moves(dev)
        self.assertEqual(len(comp_moves), 1)
        self.assertAlmostEqual(comp_moves[0].product_uom_qty, 2.0)

    def test_full_workflow_toile_to_dev(self):
        """End-to-end: data flows Toile → Dev via wizard sync."""
        toile = self._make_mo(self.svc_toile)
        toile.write({
            'structure_cad_data': {'panels': ['T1']},
            'calibration_data':   {'gauge': 8},
        })
        self._add_structure_line(toile, 'Toile Panel')
        self._add_component(toile, qty=4.0)
        dev = self._make_mo(self.svc_dev)

        wizard = self.env['maeknit.sync.from.mo.wizard'].create({
            'target_mo_id': dev.id,
            'source_type': 'toile',
            'toile_source_id': toile.id,
        })
        wizard.action_sync()

        self.assertEqual(dev.calibration_data, {'gauge': 8})
        self.assertIn('Toile Panel', dev.structure_ids.mapped('name'))
        comp_moves = self._raw_moves(dev)
        self.assertEqual(len(comp_moves), 1)
        self.assertAlmostEqual(comp_moves[0].product_uom_qty, 4.0)
