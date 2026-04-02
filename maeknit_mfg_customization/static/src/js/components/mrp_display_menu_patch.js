/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { MrpMenuDialog } from "@mrp_workorder/mrp_display/dialog/mrp_menu_dialog";

patch(MrpMenuDialog.prototype, {
    async callReknitAction() {
        let model = this.props.record.resModel; // "mrp.production" or "mrp.workorder"
        let id = this.props.record.data?.id;
        let workorderId = null;

        if (model === "mrp.workorder") {
            const workorder = await this.orm.read("mrp.workorder", [id], ["production_id"]);
            workorderId = id;
            id = workorder[0].production_id[0];
            model = "mrp.production";
        }

        const action = await this.orm.call(
            model,
            "action_reknit",
            [id],
            { context: { from_shop_floor: true, workorder_id: workorderId } }
        );
        this.action.doAction(action);
        this.props.close();
    },
});
