/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

/**
 * When the user presses Enter on a row in the Structure lines list
 * (maeknit.structure.line), save the parent form instead of adding a new row.
 */
patch(ListRenderer.prototype, {
    onCellKeydownEditMode(hotkey, cell, group, record) {
        if (hotkey === "enter" && this.props.list.resModel === "maeknit.structure.line") {
            this.props.list.model.root.save();
            return true;
        }
        return super.onCellKeydownEditMode(hotkey, cell, group, record);
    },
});
