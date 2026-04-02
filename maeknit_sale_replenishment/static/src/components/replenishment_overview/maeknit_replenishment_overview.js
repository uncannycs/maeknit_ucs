/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState, useSubEnv, EventBus } from "@odoo/owl";
import { BomOverviewTable } from "@mrp/components/bom_overview_table/mrp_bom_overview_table";

export class ReplenishmentOverviewComponent extends Component {
    static template = "maeknit_sale_replenishment.ReplenishmentOverviewComponent";
    static components = {
        BomOverviewTable,
    };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            orderName: "",
            lines: [],
        });

        useSubEnv({
            overviewBus: new EventBus(),
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    get activeId() {
        return this.props.action.context.active_id;
    }

    async loadData() {
        // 1. Fetch Sale Order Lines
        const orderId = this.activeId;
        const [order] = await this.orm.read("sale.order", [orderId], ["name", "warehouse_id", "order_line"]);
        this.state.orderName = order.name;

        // 2. Fetch Lines details
        const lines = await this.orm.read("sale.order.line", order.order_line, ["product_id", "product_uom_qty", "display_type"]);

        const validLines = lines.filter(l => l.product_id && !l.display_type);

        // 3. For each line, fetch BOM structure
        const reportLines = [];
        for (const line of validLines) {
            const productId = line.product_id[0];
            const qty = line.product_uom_qty;

            // Find BOM
            const boms = await this.orm.searchRead(
                "mrp.bom",
                [["product_id", "=", productId], ["active", "=", true]]
            );
            let targetBomId = null;
            if (boms.length > 0) {
                targetBomId = boms[0].id;
            } else {
                const product = await this.orm.read("product.product", [productId], ["product_tmpl_id"]);
                const tmplId = product[0].product_tmpl_id[0];
                const tmplBoms = await this.orm.searchRead(
                    "mrp.bom",
                    [["product_tmpl_id", "=", tmplId], ["product_id", "=", false], ["active", "=", true]]
                );
                if (tmplBoms.length > 0) {
                    targetBomId = tmplBoms[0].id;
                }
            }

            if (targetBomId) {
                const bomData = await this.orm.call(
                    "report.mrp.report_bom_structure",
                    "get_html",
                    [targetBomId, qty, productId]
                );
                console.log("++++bomData+++++++++", bomData)
                reportLines.push({
                    lineId: line.id,
                    productName: line.product_id[1],
                    bomData: bomData['lines'],
                    precision: bomData['precision'],
                    uomName: bomData['bom_uom_name'],
                    showOptions: {
                        uom: false,
                        availabilities: true,
                        costs: true,
                        operations: true,
                        leadTimes: true,
                        attachments: false,
                    },
                    currentWarehouse: { id: order.warehouse_id[0] }, // simplified
                    unfoldedIds: new Set(),
                });
            }
        }
        this.state.lines = reportLines;
    }

    onChangeFolded(line, foldInfo) {
        const { ids, isFolded } = foldInfo;
        const operation = isFolded ? "delete" : "add";
        ids.forEach(id => line.unfoldedIds[operation](id));
    }
}

registry.category("actions").add("maeknit_sale_replenishment.replenishment_overview_client_action", ReplenishmentOverviewComponent);
