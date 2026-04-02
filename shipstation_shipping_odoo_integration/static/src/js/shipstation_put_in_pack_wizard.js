'use client';

/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

class ShipstationPutInPackWizard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        // Make parseInt and Object available in template
        this.parseInt = parseInt;
        this.parseFloat = parseFloat;
        this.parseFloat = parseFloat;
        this.Object = Object;

        this.WIZARD_STORAGE_KEY = "shipstation_put_in_pack_wizard_id";
        this.PICKING_STORAGE_KEY = "shipstation_put_in_pack_picking_id";
        this.state = useState({
            wizard: null,
            availableItems: [],
            packageTypes: [],
            packages: {},
            selectedItemsByPackage: {},
            currentPackageNum: 1,
            loading: true,
            error: null,
            deliveryPackage: null,
        });
        this.existingPackageQuantities = {};

        // Get IDs from action params (passed from backend)
        const params = this.props.action?.params || {};
        this.wizardId = params.wizard_id || params.id;
        this.pickingId = params.picking_id;
        if (!this.wizardId) {
            this.wizardId = this._sessionStorageGet(this.WIZARD_STORAGE_KEY);
        }
        if (!this.pickingId) {
            this.pickingId = this._sessionStorageGet(this.PICKING_STORAGE_KEY);
        }

        console.log("Component setup - wizardId:", this.wizardId, "pickingId:", this.pickingId);
        console.log("Full props:", this.props);

        this.loadWizardData();
    }

    async loadWizardData() {
        try {
            this.state.loading = true;

            if (!this.wizardId) {
                this.state.error = _t("No wizard ID provided");
                console.error("No wizard ID found in action params");
                return;
            }

            const wizardId = this.wizardId;

            // Load wizard with available items
            const wizard = await this.orm.read("shipstation.put.in.pack.wizard", [wizardId], [
                "id",
                "picking_id",
                "available_move_line_ids",
                "package_line_ids",
            ]);
            
            this.state.wizard = wizard[0];
            this.pickingId = this.state.wizard.picking_id?.[0] || this.pickingId;
            this._sessionStorageSet(this.WIZARD_STORAGE_KEY, this.state.wizard.id);
            this._sessionStorageSet(this.PICKING_STORAGE_KEY, this.pickingId);
            await this._loadDeliveryPackageInfo(this.pickingId);
            await this._loadExistingPackageQuantities(this.state.wizard.id);

            // Load available items with product weight
            if (this.state.wizard.available_move_line_ids?.length) {
                const items = await this.orm.read(
                    "stock.move.line",
                    this.state.wizard.available_move_line_ids,
                    ["id", "product_id", "quantity", "product_uom_id"]
                );

                // Load product weights
                const productIds = items.map(item => item.product_id[0]);
                const products = await this.orm.read(
                    "product.product",
                    productIds,
                    ["id", "weight"]
                );

                // Map weights to items
                const weightMap = {};
                products.forEach(p => weightMap[p.id] = p.weight);
                items.forEach(item => {
                    item.product_weight = weightMap[item.product_id[0]] || 0;
                });

                this.state.availableItems = items;
            }

            // Load available package types
            const packageTypes = await this.orm.call(
                "shipstation.put.in.pack.wizard",
                "get_available_package_types",
                []
            );
            this.state.packageTypes = packageTypes;

            // Initialize first package with default state
            const defaultDims = this.state.deliveryPackage || {};
            this.state.packages[1] = {
                num: 1,
                name: 'Package 1',
                package_type_id: null,
                length: defaultDims.length || 0,
                width: defaultDims.width || 0,
                height: defaultDims.height || 0,
                shipping_weight: 0,
            };
            this.state.selectedItemsByPackage[1] = [];

            console.log("Wizard loaded:", this.state.wizard);
            console.log("Available items:", this.state.availableItems);
            console.log("Package types:", this.state.packageTypes);
        } catch (e) {
            console.error("Error loading wizard data:", e);
            this.state.error = e.message;
        } finally {
            this.state.loading = false;
        }
    }

    async _loadDeliveryPackageInfo(pickingId) {
        if (!pickingId) {
            this.state.deliveryPackage = null;
            return;
        }
        try {
            const pickingRecords = await this.orm.read("stock.picking", [pickingId], ["delivery_package_id"]);
            const deliveryPackageId = pickingRecords?.[0]?.delivery_package_id?.[0];
            if (!deliveryPackageId) {
                this.state.deliveryPackage = null;
                return;
            }
            const packageRecords = await this.orm.read(
                "shipstation.delivery.package",
                [deliveryPackageId],
                ["id", "name", "package_code", "length", "width", "height"]
            );
            this.state.deliveryPackage = packageRecords?.[0] || null;
        } catch (error) {
            console.error("Error loading ShipStation delivery package:", error);
            this.state.deliveryPackage = null;
        }
    }

    async _loadExistingPackageQuantities(wizardId) {
        this.existingPackageQuantities = {};
        if (!wizardId) {
            return;
        }
        try {
            const packageLineIds = await this.orm.search(
                "shipstation.put.in.pack.line",
                [["wizard_id", "=", wizardId]]
            );
            if (!packageLineIds.length) {
                return;
            }
            const lineItems = await this.orm.searchRead(
                "shipstation.put.in.pack.line.item",
                [["package_line_id", "in", packageLineIds]],
                ["move_line_id", "pack_quantity"]
            );
            for (const lineItem of lineItems) {
                const moveLineId = lineItem.move_line_id?.[0];
                if (!moveLineId) {
                    continue;
                }
                const qty = this.parseFloat(lineItem.pack_quantity) || 0;
                this.existingPackageQuantities[moveLineId] = (this.existingPackageQuantities[moveLineId] || 0) + qty;
            }
        } catch (error) {
            console.error("Error loading existing package quantities:", error);
        }
    }

    selectItemForPackage(item, packageNum) {
        if (!this.state.selectedItemsByPackage[packageNum]) {
            this.state.selectedItemsByPackage[packageNum] = [];
        }

        const existing = this.state.selectedItemsByPackage[packageNum].find(
            (i) => i.id === item.id
        );

        if (!existing) {
            // Calculate how much is available for this item
            const available = this.getAvailableQtyForPackage(item, packageNum);
            const qtyToAdd = Math.min(available, item.quantity);

            if (qtyToAdd > 0) {
                this.state.selectedItemsByPackage[packageNum].push({
                    ...item,
                    pack_quantity: qtyToAdd,
                });
                console.log("Item added to package", packageNum, item);
                // Auto-update weight when item is added
                this.updatePackageWeight(packageNum);
                // Force state update for reactivity
                this.state.selectedItemsByPackage = {...this.state.selectedItemsByPackage};
            }
        }
    }

    removeItemFromPackage(item, packageNum) {
        this.state.selectedItemsByPackage[packageNum] = this.state.selectedItemsByPackage[
            packageNum
        ].filter((i) => i.id !== item.id);
        console.log("Item removed from package", packageNum);
        // Auto-update weight when item is removed
        this.updatePackageWeight(packageNum);
        // Force state update for reactivity
        this.state.selectedItemsByPackage = {...this.state.selectedItemsByPackage};
    }

    updatePackageItemQty(item, packageNum, qty) {
        const pkgItems = this.state.selectedItemsByPackage[packageNum];
        const idx = pkgItems.findIndex((i) => i.id === item.id);
        if (idx >= 0) {
            const maxAvailable = this.getAvailableQtyForPackage(item, packageNum) + (pkgItems[idx].pack_quantity || 0);
            pkgItems[idx].pack_quantity = Math.min(parseFloat(qty) || 0, maxAvailable);
            // Auto-update weight when quantity changes
            this.updatePackageWeight(packageNum);
            // Force state update for reactivity
            this.state.selectedItemsByPackage = {...this.state.selectedItemsByPackage};
        }
    }

    addNewPackage() {
        const existingNums = Object.keys(this.state.selectedItemsByPackage).map(Number);
        const nextNum = Math.max(...existingNums, 0) + 1;

        // Initialize package configuration
        this.state.packages[nextNum] = {
            num: nextNum,
            name: `Package ${nextNum}`,
            package_type_id: null,
            length: 0,
            width: 0,
            height: 0,
            shipping_weight: 0,
        };

        // Initialize empty item selection
        this.state.selectedItemsByPackage[nextNum] = [];
        this.state.currentPackageNum = nextNum;

        console.log("New package added:", nextNum);
    }

    deletePackage(packageNum) {
        // Don't allow deleting if it's the only package
        const packageNums = Object.keys(this.state.selectedItemsByPackage).map(Number);
        if (packageNums.length <= 1) {
            this.notification.add(_t("Cannot delete the only package"), {
                type: "warning"
            });
            return;
        }

        // Remove the package from state
        delete this.state.packages[packageNum];
        delete this.state.selectedItemsByPackage[packageNum];

        // Force state update for reactivity
        this.state.packages = {...this.state.packages};
        this.state.selectedItemsByPackage = {...this.state.selectedItemsByPackage};

        // Update current package number to another existing package
        const remainingNums = Object.keys(this.state.selectedItemsByPackage).map(Number);
        if (remainingNums.length > 0) {
            this.state.currentPackageNum = Math.max(...remainingNums);
        }

        console.log("Package deleted:", packageNum);
        this.notification.add(_t("Package deleted"), {
            type: "info"
        });
    }

    goBack() {
        this._clearStoredWizardContext();
        const pickingId = this.state.wizard?.picking_id?.[0] || this.pickingId;
        if (pickingId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "stock.picking",
                res_id: pickingId,
                views: [[false, "form"]],
                target: "current",
            }, { clearBreadcrumbs: true });
        } else {
            window.history.back();
        }
    }

    goToPicking() {
        const pickingId = this.state.wizard?.picking_id?.[0] || this.pickingId;
        if (!pickingId) {
            return;
        }
        this._clearStoredWizardContext();
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "stock.picking",
            res_id: pickingId,
            views: [[false, "form"]],
            target: "current",
        }, { clearBreadcrumbs: true });
    }

    _sessionStorageSet(key, value) {
        if (typeof window === "undefined" || !window.sessionStorage) {
            return;
        }
        if (value === null || value === undefined) {
            window.sessionStorage.removeItem(key);
            return;
        }
        window.sessionStorage.setItem(key, `${value}`);
    }

    _sessionStorageGet(key) {
        if (typeof window === "undefined" || !window.sessionStorage) {
            return null;
        }
        const value = window.sessionStorage.getItem(key);
        return value ? parseInt(value, 10) : null;
    }

    _clearStoredWizardContext() {
        this._sessionStorageSet(this.WIZARD_STORAGE_KEY, null);
        this._sessionStorageSet(this.PICKING_STORAGE_KEY, null);
    }

    updatePackageDimension(packageNum, field, value) {
        if (!this.state.packages[packageNum]) {
            this.state.packages[packageNum] = {
                num: packageNum,
                name: `Package ${packageNum}`,
                package_type_id: null,
                length: 0,
                width: 0,
                height: 0,
                shipping_weight: 0,
            };
        }
        this.state.packages[packageNum][field] = parseFloat(value) || 0;
    }

    onPackageTypeSelect(packageNum, packageTypeId) {
        const packageType = this.state.packageTypes.find(pt => pt.id === packageTypeId);
        if (!packageType) return;

        const pkg = this.state.packages[packageNum];
        pkg.package_type_id = packageTypeId;

        // Auto-fill dimensions from package type if not set
        if (pkg.length === 0 && packageType.packaging_length) {
            pkg.length = packageType.packaging_length;
        }
        if (pkg.width === 0 && packageType.width) {
            pkg.width = packageType.width;
        }
        if (pkg.height === 0 && packageType.height) {
            pkg.height = packageType.height;
        }
    }

    async createPackages() {
        try {
            this.state.loading = true;
            this.state.error = null;
            const wizardId = this.state.wizard.id;

            // Validate at least one package has items
            const hasItems = Object.values(this.state.selectedItemsByPackage).some(
                items => items && items.length > 0
            );
            if (!hasItems) {
                this.state.error = "Please add at least one item to a package";
                return;
            }

            const validatePickingId = this.state.wizard?.picking_id?.[0] || this.pickingId;
            if (validatePickingId) {
                const validationCheck = await this.orm.call(
                    "stock.picking",
                    "check_shipstation_validation_requirements",
                    [validatePickingId]
                );
                if (!validationCheck?.can_validate) {
                    this.state.error = validationCheck?.message || _t("Cannot validate picking due to missing information.");
                    return;
                }
            }

            // Delete any existing package lines from previous attempts
            const existingLines = await this.orm.searchRead(
                "shipstation.put.in.pack.line",
                [["wizard_id", "=", wizardId]],
                ["id"]
            );
            if (existingLines.length > 0) {
                await this.orm.unlink("shipstation.put.in.pack.line", existingLines.map(l => l.id));
            }

            // Create package lines with full configuration
            for (const [packageNum, items] of Object.entries(this.state.selectedItemsByPackage)) {
                if (!items || items.length === 0) continue;

                const pkgNum = parseInt(packageNum);
                const pkgConfig = this.state.packages[pkgNum] || {};

                // Validate package has dimensions and weight
                if (!pkgConfig.length || !pkgConfig.width || !pkgConfig.height) {
                    this.state.error = `Package ${pkgNum}: Please enter Length, Width, and Height`;
                    return;
                }
                if (!pkgConfig.shipping_weight || pkgConfig.shipping_weight <= 0) {
                    this.state.error = `Package ${pkgNum}: Please enter a valid Weight`;
                    return;
                }

                // Validate weight is not less than minimum calculated weight
                const minWeight = this.calculateMinimumWeight(pkgNum);
                if (pkgConfig.shipping_weight < minWeight) {
                    this.state.error = `Package ${pkgNum}: Shipping weight (${pkgConfig.shipping_weight} lbs) cannot be less than the minimum calculated weight (${minWeight.toFixed(2)} lbs based on product weights)`;
                    return;
                }

                // Create package line with all details
                const packageLineData = {
                    wizard_id: wizardId,
                    package_num: pkgNum,
                    name: pkgConfig.name || `Package ${pkgNum}`,
                    package_type_id: pkgConfig.package_type_id || false,
                    length: pkgConfig.length || 0,
                    width: pkgConfig.width || 0,
                    height: pkgConfig.height || 0,
                    shipping_weight: pkgConfig.shipping_weight || 0,
                };

                const createdLineResult = await this.orm.create("shipstation.put.in.pack.line", [packageLineData]);
                // Ensure lineId is a single integer, not an array
                let lineId = Array.isArray(createdLineResult) ? createdLineResult[0] : createdLineResult;
                lineId = typeof lineId === 'number' ? lineId : parseInt(lineId);
                console.log("Created package line:", lineId, packageLineData);

                // Create line items for each product in this package
                for (const item of items) {
                    if (item.pack_quantity <= 0) continue;

                    const itemData = {
                        package_line_id: lineId,  // Should now be a single integer
                        move_line_id: item.id,
                        pack_quantity: item.pack_quantity,
                    };
                    await this.orm.create("shipstation.put.in.pack.line.item", [itemData]);
                    console.log("Created line item:", item.product_id[1], "qty:", item.pack_quantity);
                }
            }

            // Call backend to create actual packages and get return action
            await this.orm.call(
                "shipstation.put.in.pack.wizard",
                "action_create_custom_package",
                [wizardId]
            );

            this._clearStoredWizardContext();
            this.notification.add(_t("Packages created successfully. Returning to picking..."), {
                type: "success"
            });
            const targetPickingId = validatePickingId;
            if (targetPickingId) {
                await this.action.doAction({
                    type: "ir.actions.act_window",
                    res_model: "stock.picking",
                    res_id: targetPickingId,
                    views: [[false, "form"]],
                    target: "current",
                }, { clearBreadcrumbs: true });
            } else {
                await this.action.doAction({ type: "ir.actions.act_window_close" });
            }

        } catch (e) {
            console.error("Error creating packages:", e);
            const errorMessage =
                e?.data?.message ||
                e?.message ||
                (e?.data?.debug && e.data.debug.split("\n")[0]) ||
                String(e);
            this.state.error = errorMessage;
            this.notification.add(_t("Error creating packages: ") + errorMessage, {
                type: "danger"
            });
        } finally {
            this.state.loading = false;
        }
    }

    getPackageItems(packageNum) {
        return this.state.selectedItemsByPackage[packageNum] || [];
    }

    getAvailableQtyForPackage(item, packageNum) {
        const existingQty = this.existingPackageQuantities[item.id] || 0;
        let totalSelected = 0;
        for (const items of Object.values(this.state.selectedItemsByPackage)) {
            for (const selected of items || []) {
                if (selected.id === item.id) {
                    totalSelected += this.parseFloat(selected.pack_quantity) || 0;
                }
            }
        }
        const itemTotal = this.parseFloat(item.quantity) || 0;
        const available = itemTotal - existingQty - totalSelected;
        return Math.max(0, available);
    }

    calculateMinimumWeight(packageNum) {
        try {
            // Calculate minimum weight based on items: sum(qty * weight in kg)
            const items = this.state.selectedItemsByPackage[packageNum] || [];
            let totalWeightKg = 0;

            for (const item of items) {
                const qty = parseFloat(item.pack_quantity) || 0;
                const weightKg = parseFloat(item.product_weight) || 0;  // Product weight is in kg
                totalWeightKg += qty * weightKg;
            }

            // Convert kg to lbs (1 kg = 2.20462 lbs)
            const totalWeightLbs = totalWeightKg * 2.20462;

            return parseFloat(totalWeightLbs.toFixed(2));
        } catch (e) {
            console.error("Error calculating minimum weight:", e);
            return 0;
        }
    }

    updatePackageWeight(packageNum) {
        // Auto-calculate and update weight when items change
        const minWeight = this.calculateMinimumWeight(packageNum);

        if (!this.state.packages[packageNum]) {
            this.state.packages[packageNum] = {
                num: packageNum,
                name: `Package ${packageNum}`,
                package_type_id: null,
                length: 0,
                width: 0,
                height: 0,
                shipping_weight: minWeight,
            };
        } else {
            // Only update if current weight is less than minimum or zero
            const currentWeight = this.state.packages[packageNum].shipping_weight || 0;
            if (currentWeight < minWeight) {
                this.state.packages[packageNum].shipping_weight = minWeight;
            }
        }

        // Force state update for reactivity
        this.state.packages = {...this.state.packages};
    }

    getWeightWarning(packageNum) {
        try {
            const currentWeight = parseFloat(this.state.packages[packageNum]?.shipping_weight) || 0;
            const minWeight = this.calculateMinimumWeight(packageNum);

            if (currentWeight > 0 && currentWeight < minWeight) {
                return `Warning: Weight is below minimum (${minWeight.toFixed(2)} lbs based on product weights)`;
            }
            return null;
        } catch (e) {
            console.error("Error getting weight warning:", e);
            return null;
        }
    }

    closeWizard() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

ShipstationPutInPackWizard.template = "shipstation_shipping_odoo_integration.ShipstationPutInPackWizard";

registry.category("actions").add("shipstation_put_in_pack_wizard", ShipstationPutInPackWizard);
