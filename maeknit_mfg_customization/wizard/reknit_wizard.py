from odoo import models, fields, api, _
import logging

class ReknitWizard(models.TransientModel):
    _name = 'reknit.wizard'
    _description = 'Re-knit Wizard'

    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True)
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order')

    # Machine issues (Maintenance Module)
    machine_issue = fields.Selection([
        ('yarn_breakage', 'Yarn breakage'),
        ('takedown_issue', 'Takedown issue'),
        ('needle_issue', 'Needle issue'),
        ('machine_other', 'Other'),
    ], string='Machine Issue')
    
    machine_other_description = fields.Text(string='Machine Other Description')
    
    # Program issues (Quality Module)
    program_issue = fields.Selection([
        ('drop_stitch', 'Drop stitch'),
        ('program_other', 'Other'),
    ], string='Program Issue')
    
    program_other_description = fields.Text(string='Program Other Description')
    
    # Scrap yarn option
    scrap_yarn = fields.Boolean(string='Scrap yarn?', default=False)
    
    # Computed field to show if any issue is selected
    has_issue_selected = fields.Boolean(
        string='Has Issue Selected',
        compute='_compute_has_issue_selected'
    )
    
    @api.onchange('machine_issue')
    def _onchange_machine_issue(self):
        if self.machine_issue:
            self.program_issue = False
            self.program_other_description = False

    @api.onchange('program_issue')
    def _onchange_program_issue(self):
        if self.program_issue:
            self.machine_issue = False
            self.machine_other_description = False
    
    @api.depends('machine_issue', 'program_issue')
    def _compute_has_issue_selected(self):
        for record in self:
            record.has_issue_selected = bool(record.machine_issue or record.program_issue)
    
    def action_confirm_reknit(self):
        """Confirm the re-knit operation with selected options"""
        self.ensure_one()

        if not self.has_issue_selected:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Warning'),
                    'message': _('Please select at least one issue type before confirming.'),
                    'sticky': False,
                    'type': 'warning',
                },
            }

        # Log the re-knit action
        issue_details = []
        mo = self.production_id
        bom_id = mo.bom_id
              

        if self.machine_issue:
            issue_label = (
                self.machine_other_description
                if self.machine_issue == 'machine_other' and self.machine_other_description
                else dict(self._fields['machine_issue'].selection)[self.machine_issue]
            )
            issue_details.append(f"Machine Issue: {issue_label}")

            # Create a Maintenance Request
            self.env["maintenance.request"].create({
                "name": f"Re-knit Machine Issue - {issue_label}",
                "maintenance_type": "corrective",
                "equipment_id": self.production_id.workorder_ids[:1].workcenter_id.equipment_ids[:1].id
                                if self.production_id.workorder_ids else False,
                "production_id": self.production_id.id,
                "description": f"Issue reported during re-knit: {issue_label}",
                "company_id": self.production_id.company_id.id,
            })

        if self.program_issue:
            issue_label = (
                self.program_other_description
                if self.program_issue == "program_other"
                else dict(self._fields["program_issue"].selection).get(self.program_issue, "Unknown")
            )
            issue_details.append(f"Program Issue: {issue_label}")

            # Create Quality Point / Check / Alert
            team = self.env["quality.alert.team"].search([("name", "=", "Machine Programmers")], limit=1)
            test_type = self.env["quality.point.test_type"].search([("technical_name", "=", "passfail")], limit=1)

            if team and test_type:
                qc_point = self.env["quality.point"].search([
                    ("title", "=", issue_label),
                    ("product_ids", "in", [self.production_id.product_id.id]),
                    ("team_id", "=", team.id),
                    ("company_id", "=", self.production_id.company_id.id),
                ], limit=1)

                if not qc_point:
                    qc_point = self.env["quality.point"].create({
                        "name": self.env["ir.sequence"].next_by_code("quality.point") or "New",
                        "title": issue_label,
                        "team_id": team.id,
                        "company_id": self.production_id.company_id.id,
                        "test_type_id": test_type.id,
                        "test_report_type": "pdf",
                        "measure_on": "product",
                        "measure_frequency_type": "all",
                        "product_ids": [(6, 0, [self.production_id.product_id.id])],
                    })

                qc_check = self.env["quality.check"].create({
                    "point_id": qc_point.id,
                    "team_id": team.id,
                    "company_id": self.production_id.company_id.id,
                    "product_id": self.production_id.product_id.id,
                    "production_id": self.production_id.id,
                })

                self.env["quality.alert"].create({
                    "title": issue_label,
                    "team_id": team.id,
                    "company_id": self.production_id.company_id.id,
                    "product_id": self.production_id.product_id.id,
                    "check_id": qc_check.id,
                    "production_id": self.production_id.id,
                })
                
        if self.scrap_yarn:
            issue_details.append("Scrap yarn: Yes - consume all yarn in BOM")
            self._handle_yarn_scrap()
        
        bom_request = self.env['maeknit.bom.request'].search([
            ('bom_id', '=', bom_id.id)
        ], limit=1)

        new_wo = None

        if bom_request:
            if self.program_issue:
                logging.info(" Custom Code:Program issue selected, updating BOM Request %s to 'to_approve'", bom_request.id)
                bom_request._update_bom_state_and_add_task()
            # Get all operations sorted by current sequence
            all_ops = bom_request.operation_ids.sorted('sequence')
            
            # Re-sequence all operations to be sequential (1, 2, 3, 4...)
            for idx, op in enumerate(all_ops, start=1):
                if op.sequence != idx:
                    op.write({'sequence': idx})
                    logging.info(" Custom Code:[REKNIT] Normalized op %s sequence to %s", op.name, idx)
            
            # Now find the last Knit operation (after normalization)
            knit_ops = all_ops.filtered(lambda op: 'Knit' in op.name)
            if knit_ops:
                last_knit = knit_ops[-1]  # Get the LAST Knit operation
                insert_seq = last_knit.sequence + 1
                
                logging.info(" Custom Code:[REKNIT] Last Knit op: %s at sequence %s, inserting new Knit at %s", 
                            last_knit.name, last_knit.sequence, insert_seq)

                # Shift all operations that come AFTER the last Knit down by 1
                later_ops = all_ops.filtered(lambda o: o.sequence >= insert_seq)
                for op_shift in later_ops:
                    new_seq = op_shift.sequence + 1
                    logging.info(" Custom Code:[REKNIT] Shifting op %s from seq %s to %s", op_shift.name, op_shift.sequence, new_seq)
                    op_shift.write({'sequence': new_seq})
                program_version = (last_knit.program_version or 1) + 1 if self.program_issue else last_knit.program_version
                knit_attempt = (last_knit.knit_attempt or 1) + 1            
                # Create the new Knit operation at the correct sequence
                new_op = self.env['maeknit.bom.request.operation'].create({
                    'bom_request_id': bom_request.id,
                    'operation_id': last_knit.operation_id.id,
                    'sequence': insert_seq,
                    'workcenter_id': last_knit.workcenter_id.id,
                    'time_cycle': last_knit.time_cycle,
                    'employee_assigned_ids': [(6, 0, last_knit.employee_assigned_ids.ids)],
                    'knit_attempt': knit_attempt,
                    'program_version': program_version,
                })
                logging.info(" Custom Code:[REKNIT] Created new Knit op %s at sequence %s (after last Knit at seq %s)", 
                            new_op.id, insert_seq, last_knit.sequence)
                
                if not self.program_issue:
                    for att in last_knit.instruction_attachment_ids:
                        new = att.copy({
                            'res_id': new_op.id,
                            'res_model': 'maeknit.bom.request.operation',
                        })
                        new_op.instruction_attachment_ids = [(4, new.id)]

                    for att in last_knit.program_attachment_ids:
                        new = att.copy({
                            'res_id': new_op.id,
                            'res_model': 'maeknit.bom.request.operation',
                        })
                        new_op.program_attachment_ids = [(4, new.id)]

                if bom_request and mo:
                    current_wo = self.env['mrp.workorder'].search([
                        ('production_id', '=', mo.id),
                        ('state', 'in', ['ready', 'progress']),
                        ('name', 'ilike', 'Knit')
                    ], order='id asc', limit=1)

                    if current_wo:
                        logging.info(" Custom Code:[REKNIT] Found current Knit WO: %s (%s)", current_wo.name, current_wo.state)
                        current_wo.qty_producing = current_wo.qty_producing or current_wo.qty_production or 1.0
                        try:
                            current_wo.button_finish()
                            self.env.cr.flush()
                            self.env.invalidate_all()
                            logging.info(" Custom Code:[REKNIT] After button_finish(): state=%s", current_wo.state)
                        except Exception as e:
                            logging.error("[REKNIT] button_finish() failed: %s", e)
                        
                    if not self.program_issue:
                        new_wo = bom_request._sync_operations_to_mo(mo, bom_request, mode='reknit')
                    elif self.program_issue:
                        new_wo = bom_request._sync_operations_to_mo(mo, bom_request, mode='reprogram')
                    self.env.cr.flush()
                    self.env.invalidate_all()
                    logging.info(" Custom Code:[REKNIT] Synced MO %s with BOM Request %s", mo.name, bom_request.name)
                self.env.cr.flush()
                self.env.invalidate_all()

        message_body = f"""
        <p><strong>Re-knit Operation Initiated</strong></p>
        <ul>
            {''.join([f'<li>{detail}</li>' for detail in issue_details])}
        </ul>
        """
        mo.message_post(body=message_body, subject="Re-knit Operation", message_type='comment')

        mo.action_reknit()
        logging.info(" Custom Code:new_wo: %s", new_wo)   
        wc = None
        if self.workorder_id:
            wc = self.workorder_id.workcenter_id  
        # This allows the shopfloor view to refresh without losing filter state
        
        return self._action_open_mes(target_wo_id=new_wo if new_wo else None)
    
    def _action_open_mes(self, target_wo_id=None, workcenter_id=None, production_id=None):
        action = self.env["ir.actions.actions"]._for_xml_id("mrp_workorder.action_mrp_display")
        target_wo = target_wo_id or self.id

        # preserve existing context keys and add your target WO
        if self.program_issue:
            ctx = {
                "workcenter_id": self.workorder_id.workcenter_id.id,
                "search_default_progress": False,
                "search_default_ready": False,
                "search_default_name": self.production_id.name,
                "shouldHideNewWorkcenterButton": True,
                "force_reload": True,          
            }
        else:   
            ctx = {
                "workcenter_id": workcenter_id.id if workcenter_id else self.workorder_id.workcenter_id.id,
                "search_default_progress": True,
                "search_default_ready": True,
                "search_default_name": self.production_id.name,
                "shouldHideNewWorkcenterButton": True,
                "active_workorder_id": target_wo,  
                "force_reload": True,          
            }

        action["context"] = ctx
        return action

    def _handle_yarn_scrap(self):
        self.ensure_one()
        mo = self.production_id
        wo = self.workorder_id
        
        yarn_components = mo.bom_id.bom_line_ids.filtered_domain([
            ('product_id.product_tmpl_id.product_category', '=', 'yarn')
        ])


        for component in yarn_components:
            qty = component.product_qty * mo.product_qty
            
            lot = self.env['stock.lot'].search([
                ('product_id', '=', component.product_id.id),
            ], order="id asc", limit=1)
            
            logging.info(" Custom Code:Found lot %s for product %s", lot.name if lot else 'N/A', component.product_id.name)
            logging.info('component.product_id.id: %s', component.product_id.id)  
            logging.info('mo.company_id.id: %s', mo.company_id.id)
            
            scrap_location = self.env['stock.location'].search([
                ('scrap_location', '=', True),
                ('usage', '=', 'inventory'),
                ('company_id', '=', mo.company_id.id)
            ], limit=1)
            scrap_location_id = scrap_location.id if scrap_location else False

            scrap = self.env['stock.scrap'].with_context(
                default_production_id=mo.id,
                default_company_id=mo.company_id.id,
                default_workorder_id=wo.id if wo else False,
                default_bom_id=mo.bom_id.id,
                default_product_id=component.product_id.id,
                default_scrap_qty=qty,
                default_product_uom_id=component.product_uom_id.id,
                default_lot_id=lot.id if lot else False,
                default_location_id=mo.location_src_id.id,
                default_scrap_location_id=scrap_location_id,
            ).create({})
            logging.info(" Custom Code:Created scrap record %s for product %s, qty %s", scrap.id, component.product_id.name, qty)
            scrap.do_scrap()

    def action_cancel(self):
        """Cancel the wizard without performing re-knit"""
        return {'type': 'ir.actions.act_window_close'}
    
    @api.model
    def open_reknit_wizard(self, production_id, bom_request_id, workorder_id=None):
        logging.info(" Custom Code:Opening re-knit wizard for MO %s, BOM Request %s, WO %s", production_id, bom_request_id, workorder_id)
        ctx = {
            'default_production_id': production_id,
            'active_id': production_id,
            'active_model': 'mrp.production',
        }
        if workorder_id:
            ctx['default_workorder_id'] = workorder_id

        return {
            'type': 'ir.actions.act_window',
            'name': 'Re-knit Options',
            'res_model': 'reknit.wizard',
            'view_mode': 'form',
            'views': [(self.env.ref('maeknit_mfg_customization.reknit_wizard_form_view').id, 'form')],
            'target': 'new',
            'context': ctx,
        }
