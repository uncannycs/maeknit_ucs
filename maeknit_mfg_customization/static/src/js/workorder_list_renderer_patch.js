/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { AutoColumnWidthListRenderer } from "@stock/views/list/auto_column_width_list_renderer";

/**
 * Custom controller: row click opens the Manufacturing Order instead of the WO.
 * ListController.setup() already wires this.actionService, so we only need orm.
 */
class WorkorderListController extends ListController {
    async openRecord(record) {
        return this.actionService.doActionButton({
            name: "open_production_order",
            type: "object",
            resModel: "mrp.workorder",
            resId: record.resId,
            resIds: [record.resId],
        });
    }
}

/**
 * Custom renderer: Enter key stays in the same column on the next row.
 */
class WorkorderListRenderer extends AutoColumnWidthListRenderer {
    onCellKeydownEditMode(hotkey, cell, group, record) {
        if (hotkey !== "enter") {
            return super.onCellKeydownEditMode(hotkey, cell, group, record);
        }

        const { list } = this.props;
        const index = list.records.indexOf(record);
        const futureRecord = list.records[index + 1];

        const cellName = cell?.getAttribute("name");
        const currentColumn = cellName
            ? this.columns.find((col) => col.name === cellName)
            : null;

        if (!futureRecord || !currentColumn) {
            return super.onCellKeydownEditMode(hotkey, cell, group, record);
        }

        list.leaveEditMode({ validate: true }).then(async (canProceed) => {
            if (!canProceed) return;
            await new Promise((resolve) => setTimeout(resolve, 0));
            if (!this.cellToFocus) {
                this.cellToFocus = { column: currentColumn, record: futureRecord };
            }
            list.enterEditMode(futureRecord);
        });

        return true;
    }
}

// Replace the built-in mrp_workorder_list_view with our custom Controller + Renderer.
const baseView = registry.category("views").get("mrp_workorder_list_view");
registry.category("views").add(
    "mrp_workorder_list_view",
    { ...baseView, Controller: WorkorderListController, Renderer: WorkorderListRenderer },
    { force: true }
);
