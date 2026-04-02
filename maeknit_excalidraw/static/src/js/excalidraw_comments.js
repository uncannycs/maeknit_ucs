/** @odoo-module **/

/**
 * ExcalidrawComments
 * ──────────────────
 * Manages a comment-pin overlay and sidebar panel on top of an Excalidraw
 * canvas.  The overlay and panel are plain DOM nodes — not React — so they
 * can be siblings to the React root without interfering with it.
 *
 * Usage (from ExcalidrawWidget):
 *
 *   this.commentsController = new ExcalidrawComments({
 *     container,        // the outer .o_excalidraw_widget div
 *     resModel,         // 'maeknit.bom.request'
 *     resId,            // integer record ID
 *     fieldName,        // 'excalidraw_data'
 *     currentUser,      // { uid, name, partnerId }
 *     getExcalidrawAPI, // () => the Excalidraw API ref (may be null initially)
 *     refreshChatter,   // optional () => void — called after comment actions to refresh chatter
 *   })
 *   this.commentsController.start()
 *   // later:
 *   this.commentsController.syncScrollState(appState)
 *   this.commentsController.setCommentMode(bool)
 *   this.commentsController.destroy()
 */
class ExcalidrawComments {
    constructor({ container, resModel, resId, fieldName, currentUser, getExcalidrawAPI, refreshChatter }) {
        this.container = container
        this.resModel = resModel
        this.resId = resId
        this.fieldName = fieldName
        this.currentUser = currentUser           // { uid, name, partnerId }
        this.getExcalidrawAPI = getExcalidrawAPI // () => api | null
        this.refreshChatter = refreshChatter || null

        // ── State ─────────────────────────────────────────────────────────
        this.comments = []
        this.commentMode = false
        this.panelOpen = false
        this.pendingPin = null   // { screenX, screenY, sceneX, sceneY }
        this._pendingDraftText = ''  // preserves comment text across _renderPins() calls
        this.scrollState = null  // mirrors Excalidraw appState scroll/zoom
        this.activeCommentId = null
        this.showResolved = false

        // ── Current elements (updated from widget on every onChange) ──────
        this.currentElements = []

        // ── @mention state ────────────────────────────────────────────────
        this._mentionedPartnerIds = []   // accumulated for pending comment
        this._mentionQuery = ''          // text after @ being searched
        this._mentionStart = -1          // textarea cursor offset where @ appears
        this._mentionUsers = []          // current search results
        this._mentionDropdownEl = null   // dropdown DOM node
        this._mentionHighlightIndex = -1 // keyboard-navigated item index

        // ── DOM nodes (created in _buildDOM) ──────────────────────────────
        this.overlayEl = null
        this.panelEl = null
        this.toggleBtnEl = null

        this._pollInterval = null
        this._handleOverlayClick = this._handleOverlayClick.bind(this)
        this._handleKeyDown = this._handleKeyDown.bind(this)

        // ── Draggable panel state ─────────────────────────────────────────
        this._panelPos = null      // { top, left } once dragged from initial position
        this._dragOffsetX = 0
        this._dragOffsetY = 0
    }

    // ─── Lifecycle ────────────────────────────────────────────────────────────

    start() {
        this._buildDOM()
        this._fetchComments()
        this._pollInterval = setInterval(() => this._fetchComments(), 30_000)
        document.addEventListener('keydown', this._handleKeyDown)
    }

    destroy() {
        clearInterval(this._pollInterval)
        document.removeEventListener('keydown', this._handleKeyDown)
        this.overlayEl?.remove()
        this.panelEl?.remove()
        this.toggleBtnEl?.remove()
        this._mentionDropdownEl?.remove()
    }

    // Called by ExcalidrawWidget.handleExcalidrawChange with the live appState
    syncScrollState(appState) {
        if (!appState) return
        this.scrollState = {
            scrollX: appState.scrollX,
            scrollY: appState.scrollY,
            zoom: appState.zoom,
            offsetLeft: appState.offsetLeft,
            offsetTop: appState.offsetTop,
        }
        this._renderPins()
    }

    setCommentMode(enabled) {
        this.commentMode = enabled
        if (!enabled) this.pendingPin = null
        this._applyOverlayCursor()
        this._renderPins()
    }

    // Called by ExcalidrawWidget.handleExcalidrawChange with the live elements array
    updateElements(elements) {
        this.currentElements = Array.isArray(elements) ? elements : []
        // Re-render pins so anchored comments recompute their positions
        this._renderPins()
    }

    // ─── DOM construction ────────────────────────────────────────────────────

    _buildDOM() {
        // Ensure container is positioned so absolute children work
        this.container.style.position = 'relative'
        this.container.style.overflow = 'hidden'

        // Overlay — sits on top of canvas, captures clicks in comment mode
        this.overlayEl = document.createElement('div')
        this.overlayEl.className = 'o-excalidraw-comment-overlay'
        this.overlayEl.addEventListener('click', this._handleOverlayClick)
        this.container.appendChild(this.overlayEl)

        // Panel toggle bubble (bottom-right, above toolbar)
        this.toggleBtnEl = document.createElement('button')
        this.toggleBtnEl.className = 'o-excalidraw-comment-toggle'
        this.toggleBtnEl.title = 'Comments'
        this.toggleBtnEl.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <span class="o-excalidraw-comment-badge" style="display:none"></span>
        `
        this.toggleBtnEl.addEventListener('click', () => {
            this.panelOpen = !this.panelOpen
            this._renderPanel()
            this._renderToggleBtn()
        })
        this.container.appendChild(this.toggleBtnEl)

        // Panel
        this.panelEl = document.createElement('div')
        this.panelEl.className = 'o-excalidraw-comment-panel'
        this.panelEl.style.display = 'none'
        this.container.appendChild(this.panelEl)

        // Mention dropdown (appended to container, shown near textarea)
        this._mentionDropdownEl = document.createElement('div')
        this._mentionDropdownEl.className = 'o-excalidraw-mention-dropdown'
        this._mentionDropdownEl.style.cssText = `
            display:none;position:absolute;z-index:200;
            background:white;border:1px solid #e5e7eb;border-radius:8px;
            box-shadow:0 4px 16px rgba(0,0,0,0.15);
            min-width:200px;max-width:280px;overflow:hidden;
        `
        this.container.appendChild(this._mentionDropdownEl)
    }

    // ─── Overlay cursor & pointer-events ─────────────────────────────────────

    _applyOverlayCursor() {
        if (!this.overlayEl) return
        if (this.commentMode) {
            this.overlayEl.style.pointerEvents = 'all'
            this.overlayEl.style.cursor = 'crosshair'
        } else {
            this.overlayEl.style.pointerEvents = 'none'
            this.overlayEl.style.cursor = 'default'
        }
    }

    // ─── RPC ─────────────────────────────────────────────────────────────────

    async _rpc(url, params) {
        try {
            const r = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({ jsonrpc: '2.0', method: 'call', id: Date.now(), params }),
            })
            const data = await r.json()
            if (data.error) {
                console.error('[ExcalidrawComments] RPC error:', data.error)
                return null
            }
            return data.result
        } catch (e) {
            console.error('[ExcalidrawComments] fetch error:', e)
            return null
        }
    }

    // ─── Data ────────────────────────────────────────────────────────────────

    async _fetchComments() {
        const result = await this._rpc('/maeknit/excalidraw/comments/list', {
            res_model: this.resModel,
            res_id: this.resId,
            field_name: this.fieldName,
        })
        if (result) {
            this.comments = result.comments || []
            this._renderPins()
            this._renderPanel()
            this._renderToggleBtn()
        }
    }

    async _createComment(sceneX, sceneY, message, partnerIds, elementId, elementFracX, elementFracY) {
        const params = {
            res_model: this.resModel,
            res_id: this.resId,
            field_name: this.fieldName,
            x: sceneX,
            y: sceneY,
            message,
            partner_ids: partnerIds || [],
        }
        if (elementId) {
            params.element_id = elementId
            params.element_frac_x = elementFracX || 0
            params.element_frac_y = elementFracY || 0
        }
        const result = await this._rpc('/maeknit/excalidraw/comments/create', params)
        if (result?.comment) {
            this.comments.push(result.comment)
            this.activeCommentId = result.comment.id
            this.pendingPin = null
            this.commentMode = false
            this.panelOpen = true
            this._applyOverlayCursor()
            this._renderPins()
            this._renderPanel()
            this._renderToggleBtn()
            if (this.refreshChatter) this.refreshChatter()
        }
    }

    async _resolveComment(commentId) {
        // Optimistic update
        this.comments = this.comments.map(c =>
            c.id === commentId ? { ...c, is_resolved: !c.is_resolved } : c
        )
        this._renderPins()
        this._renderPanel()
        this._renderToggleBtn()
        await this._rpc('/maeknit/excalidraw/comments/resolve', { comment_id: commentId })
        if (this.refreshChatter) this.refreshChatter()
    }

    async _deleteComment(commentId) {
        // Optimistic update
        this.comments = this.comments.filter(c => c.id !== commentId)
        if (this.activeCommentId === commentId) this.activeCommentId = null
        this._renderPins()
        this._renderPanel()
        this._renderToggleBtn()
        await this._rpc('/maeknit/excalidraw/comments/delete', { comment_id: commentId })
        if (this.refreshChatter) this.refreshChatter()
    }

    // ─── @mention support ────────────────────────────────────────────────────

    async _searchUsers(q) {
        const result = await this._rpc('/maeknit/excalidraw/users/search', { q })
        return result?.users || []
    }

    _showMentionDropdown(users, anchorEl) {
        if (!this._mentionDropdownEl || !anchorEl) return
        if (users.length === 0) {
            this._hideMentionDropdown()
            return
        }
        this._mentionUsers = users

        const anchorRect = anchorEl.getBoundingClientRect()
        const containerRect = this.container.getBoundingClientRect()
        const top = anchorRect.top - containerRect.top - (users.length * 38 + 8)
        const left = anchorRect.left - containerRect.left

        this._mentionDropdownEl.style.top = `${Math.max(0, top)}px`
        this._mentionDropdownEl.style.left = `${left}px`
        this._mentionDropdownEl.style.display = 'block'

        this._mentionDropdownEl.innerHTML = users.map((u, i) => `
            <div class="o-excalidraw-mention-item" data-index="${i}"
                 style="padding:8px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;
                        font-size:13px;color:#374151;border-bottom:1px solid #f3f4f6;">
                <div style="width:24px;height:24px;border-radius:50%;background:#6366f1;
                            color:white;display:flex;align-items:center;justify-content:center;
                            font-size:11px;font-weight:700;flex-shrink:0;">
                    ${this._esc((u.name || '?')[0].toUpperCase())}
                </div>
                <span>${this._esc(u.name)}</span>
            </div>
        `).join('')

        this._mentionDropdownEl.querySelectorAll('.o-excalidraw-mention-item').forEach(item => {
            item.addEventListener('mousedown', (e) => {
                e.preventDefault()  // prevent textarea blur
                const idx = parseInt(item.dataset.index)
                const user = this._mentionUsers[idx]
                if (user) this._activeTextarea && this._insertMention(user, this._activeTextarea)
            })
            item.addEventListener('mouseover', () => {
                this._mentionHighlightIndex = parseInt(item.dataset.index)
                this._applyMentionHighlight()
            })
        })
        // Apply initial highlight
        this._applyMentionHighlight()
    }

    _hideMentionDropdown() {
        if (this._mentionDropdownEl) this._mentionDropdownEl.style.display = 'none'
        this._mentionUsers = []
        this._mentionQuery = ''
        this._mentionStart = -1
        this._mentionHighlightIndex = -1
    }

    _moveMentionHighlight(delta) {
        if (!this._mentionUsers.length) return
        this._mentionHighlightIndex = Math.max(0,
            Math.min(this._mentionUsers.length - 1, this._mentionHighlightIndex + delta))
        this._applyMentionHighlight()
    }

    _applyMentionHighlight() {
        if (!this._mentionDropdownEl) return
        this._mentionDropdownEl.querySelectorAll('.o-excalidraw-mention-item').forEach((el, i) => {
            el.style.background = i === this._mentionHighlightIndex ? '#f3f4f6' : 'white'
        })
    }

    _insertMention(user, textarea) {
        // Replace @query with @Name in textarea
        const before = textarea.value.slice(0, this._mentionStart)
        const after = textarea.value.slice(this._mentionStart + this._mentionQuery.length + 1)
        const mention = `@${user.name}`
        textarea.value = before + mention + ' ' + after
        textarea.selectionStart = textarea.selectionEnd = before.length + mention.length + 1

        // Track partner for notification
        if (!this._mentionedPartnerIds.includes(user.partner_id)) {
            this._mentionedPartnerIds.push(user.partner_id)
        }

        this._hideMentionDropdown()

        // Update post button state
        const postBtn = textarea.closest('.o-excalidraw-comment-input-card')
            ?.querySelector('.o-excalidraw-post-btn')
        if (postBtn) {
            const hasText = textarea.value.trim().length > 0
            postBtn.style.background = hasText ? '#f97316' : '#d1d5db'
            postBtn.style.cursor = hasText ? 'pointer' : 'default'
        }

        textarea.focus()
    }

    _handleMentionInput(textarea) {
        this._activeTextarea = textarea
        const value = textarea.value
        const cursor = textarea.selectionStart

        // Find the @ closest to cursor (scanning backward)
        let atPos = -1
        for (let i = cursor - 1; i >= 0; i--) {
            if (value[i] === '@') { atPos = i; break }
            if (value[i] === ' ' || value[i] === '\n') break
        }

        if (atPos === -1) {
            this._hideMentionDropdown()
            return
        }

        const query = value.slice(atPos + 1, cursor)
        // Only trigger if query is reasonably short and has no spaces
        if (query.length > 20 || query.includes(' ')) {
            this._hideMentionDropdown()
            return
        }

        this._mentionStart = atPos
        this._mentionQuery = query

        this._searchUsers(query).then(users => {
            // Re-check still in mention mode (user might have kept typing)
            if (this._mentionStart === atPos) {
                this._mentionHighlightIndex = users.length > 0 ? 0 : -1
                this._showMentionDropdown(users, textarea)
            }
        })
    }

    // ─── Element anchoring helpers ────────────────────────────────────────────

    // Find the topmost non-deleted element whose bounding box contains (sceneX, sceneY)
    _findElementAtScene(sceneX, sceneY) {
        for (let i = this.currentElements.length - 1; i >= 0; i--) {
            const el = this.currentElements[i]
            if (el.isDeleted) continue
            const x1 = Math.min(el.x, el.x + (el.width || 0))
            const y1 = Math.min(el.y, el.y + (el.height || 0))
            const x2 = Math.max(el.x, el.x + (el.width || 0))
            const y2 = Math.max(el.y, el.y + (el.height || 0))
            if (sceneX >= x1 && sceneX <= x2 && sceneY >= y1 && sceneY <= y2) {
                return el
            }
        }
        return null
    }

    // Compute the effective scene position for a comment, honouring its element anchor
    _getEffectiveScenePos(comment) {
        if (comment.element_id) {
            const el = this.currentElements.find(e => e.id === comment.element_id && !e.isDeleted)
            if (el && el.width && el.height) {
                return {
                    x: el.x + (comment.element_frac_x || 0) * el.width,
                    y: el.y + (comment.element_frac_y || 0) * el.height,
                }
            }
        }
        // Fallback: use stored absolute scene coordinates
        return { x: comment.x, y: comment.y }
    }

    // ─── Coordinate conversion ────────────────────────────────────────────────

    _getMarkerPosition(comment) {
        if (!this.scrollState || !this.overlayEl) return null
        const lib = window.ExcalidrawLib
        if (!lib?.sceneCoordsToViewportCoords) return null
        const { x, y } = this._getEffectiveScenePos(comment)
        const vp = lib.sceneCoordsToViewportCoords(
            { sceneX: x, sceneY: y },
            this.scrollState
        )
        const rect = this.overlayEl.getBoundingClientRect()
        return { left: vp.x - rect.left, top: vp.y - rect.top }
    }

    _viewportToScene(clientX, clientY) {
        const api = this.getExcalidrawAPI()
        if (!api) return null
        const lib = window.ExcalidrawLib
        if (!lib?.viewportCoordsToSceneCoords) return null
        const appState = api.getAppState()
        return lib.viewportCoordsToSceneCoords({ clientX, clientY }, appState)
    }

    // ─── Event handlers ───────────────────────────────────────────────────────

    _handleOverlayClick(e) {
        if (!this.commentMode) return
        // If clicking on an existing pin or the pending input, don't create a new pending pin
        if (e.target.closest('.o-excalidraw-comment-pin') ||
            e.target.closest('.o-excalidraw-comment-input-card')) return

        const sceneCoords = this._viewportToScene(e.clientX, e.clientY)
        if (!sceneCoords) return

        const rect = this.overlayEl.getBoundingClientRect()
        this._mentionedPartnerIds = []  // reset for new comment

        // Try to anchor to the element under the click point
        const anchorEl = this._findElementAtScene(sceneCoords.x, sceneCoords.y)
        let elementId = null, elementFracX = 0, elementFracY = 0
        if (anchorEl && anchorEl.width && anchorEl.height) {
            elementId = anchorEl.id
            elementFracX = (sceneCoords.x - anchorEl.x) / anchorEl.width
            elementFracY = (sceneCoords.y - anchorEl.y) / anchorEl.height
        }

        this.pendingPin = {
            screenX: e.clientX - rect.left,
            screenY: e.clientY - rect.top,
            sceneX: sceneCoords.x,
            sceneY: sceneCoords.y,
            elementId,
            elementFracX,
            elementFracY,
        }
        this._renderPins()
    }

    _handleKeyDown(e) {
        if (e.key === 'Escape' && (this.commentMode || this.pendingPin)) {
            this._hideMentionDropdown()
            this.pendingPin = null
            this.commentMode = false
            this._applyOverlayCursor()
            this._renderPins()
        }
    }

    // ─── Rendering ────────────────────────────────────────────────────────────

    _renderPins() {
        if (!this.overlayEl) return

        let html = ''

        // Existing comment pins
        for (const comment of this.comments) {
            const pos = this._getMarkerPosition(comment)
            if (!pos) continue
            const isActive = this.activeCommentId === comment.id
            const isResolved = comment.is_resolved
            const initial = (comment.user_name || '?')[0].toUpperCase()
            const pinColor = isResolved ? '#9ca3af' : '#f97316'
            const scale = isActive ? 1.3 : 1
            const shadow = isActive
                ? '0 0 0 3px #fed7aa, 0 2px 8px rgba(0,0,0,0.25)'
                : '0 2px 6px rgba(0,0,0,0.2)'

            html += `
                <div class="o-excalidraw-comment-pin${isResolved ? ' resolved' : ''}${isActive ? ' active' : ''}"
                     data-comment-id="${comment.id}"
                     style="position:absolute;left:${pos.left}px;top:${pos.top}px;
                            transform:translate(-50%,-100%) scale(${scale});
                            z-index:${isActive ? 25 : 20};
                            pointer-events:all;cursor:pointer;transition:transform 0.15s;"
                     title="${this._esc(comment.user_name)}: ${this._esc(comment.message)}">
                    <div style="width:28px;height:28px;border-radius:50% 50% 50% 0;
                                transform:rotate(-45deg);background:${pinColor};
                                display:flex;align-items:center;justify-content:center;
                                box-shadow:${shadow};border:2px solid white;">
                        <span style="transform:rotate(45deg);color:white;font-size:11px;font-weight:700;line-height:1;">
                            ${this._esc(initial)}
                        </span>
                    </div>
                </div>`
        }

        // Pending pin dot + input card
        if (this.pendingPin) {
            const p = this.pendingPin
            html += `
                <div class="o-excalidraw-comment-pending"
                     style="position:absolute;left:${p.screenX}px;top:${p.screenY}px;z-index:30;pointer-events:all;">
                    <div style="width:10px;height:10px;border-radius:50%;background:#f97316;
                                border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.3);
                                transform:translate(-50%,-50%);"></div>
                    <div class="o-excalidraw-comment-input-card"
                         style="margin-top:6px;background:white;border:1px solid #e5e7eb;
                                border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.12);
                                padding:10px;width:240px;transform:translateX(-50%);">
                        <textarea class="o-excalidraw-comment-textarea"
                                  placeholder="Add a comment… use @ to mention"
                                  style="width:100%;border:none;outline:none;resize:none;
                                         font-family:inherit;font-size:13px;line-height:1.5;
                                         min-height:64px;padding:2px 4px;color:#111;
                                         box-sizing:border-box;"></textarea>
                        <div style="display:flex;justify-content:flex-end;gap:6px;margin-top:6px;">
                            <button class="o-excalidraw-cancel-btn"
                                    style="padding:4px 10px;border:1px solid #e5e7eb;border-radius:5px;
                                           background:white;cursor:pointer;font-size:12px;color:#6b7280;">
                                Cancel
                            </button>
                            <button class="o-excalidraw-post-btn"
                                    style="padding:4px 10px;border:none;border-radius:5px;
                                           background:#d1d5db;color:white;cursor:default;
                                           font-size:12px;font-weight:500;">
                                Post
                            </button>
                        </div>
                    </div>
                </div>`
        }

        // Preserve any in-progress comment text before replacing the DOM
        if (this.pendingPin) {
            const existingTextarea = this.overlayEl.querySelector('.o-excalidraw-comment-textarea')
            if (existingTextarea) {
                this._pendingDraftText = existingTextarea.value
            }
        }

        this.overlayEl.innerHTML = html

        // Wire up pin click handlers
        this.overlayEl.querySelectorAll('.o-excalidraw-comment-pin').forEach(pin => {
            pin.addEventListener('click', (e) => {
                e.stopPropagation()
                const id = parseInt(pin.dataset.commentId)
                this.activeCommentId = id
                this.panelOpen = true
                this._renderPins()
                this._renderPanel()
                this._renderToggleBtn()
                // Scroll canvas to center on comment
                const comment = this.comments.find(c => c.id === id)
                if (comment) this._scrollCanvasToComment(comment)
            })
        })

        // Wire up pending input
        if (this.pendingPin) {
            const textarea = this.overlayEl.querySelector('.o-excalidraw-comment-textarea')
            const postBtn = this.overlayEl.querySelector('.o-excalidraw-post-btn')
            const cancelBtn = this.overlayEl.querySelector('.o-excalidraw-cancel-btn')

            // Stop overlay click from propagating through the input card
            this.overlayEl.querySelector('.o-excalidraw-comment-pending')
                .addEventListener('click', e => e.stopPropagation())

            if (textarea) {
                // Restore draft text that was preserved before DOM replacement
                if (this._pendingDraftText) {
                    textarea.value = this._pendingDraftText
                    const hasText = this._pendingDraftText.trim().length > 0
                    if (postBtn) {
                        postBtn.style.background = hasText ? '#f97316' : '#d1d5db'
                        postBtn.style.cursor = hasText ? 'pointer' : 'default'
                    }
                }
                textarea.focus()
                textarea.addEventListener('input', () => {
                    const hasText = textarea.value.trim().length > 0
                    postBtn.style.background = hasText ? '#f97316' : '#d1d5db'
                    postBtn.style.cursor = hasText ? 'pointer' : 'default'
                    this._handleMentionInput(textarea)
                })
                textarea.addEventListener('keydown', (e) => {
                    const dropdownOpen = this._mentionDropdownEl?.style.display !== 'none'
                    if (dropdownOpen) {
                        if (e.key === 'ArrowDown') {
                            e.preventDefault()
                            this._moveMentionHighlight(1)
                            return
                        }
                        if (e.key === 'ArrowUp') {
                            e.preventDefault()
                            this._moveMentionHighlight(-1)
                            return
                        }
                        if (e.key === 'Enter' || e.key === 'Tab') {
                            e.preventDefault()
                            const idx = this._mentionHighlightIndex >= 0
                                ? this._mentionHighlightIndex : 0
                            const user = this._mentionUsers[idx]
                            if (user) this._insertMention(user, textarea)
                            return
                        }
                        if (e.key === 'Escape') {
                            e.stopPropagation()
                            this._hideMentionDropdown()
                            return
                        }
                    }
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        this._submitPending(textarea.value)
                    }
                    if (e.key === 'Escape') this._cancelPending()
                })
                textarea.addEventListener('blur', () => {
                    // Delay to allow mousedown on dropdown item to fire first
                    setTimeout(() => this._hideMentionDropdown(), 150)
                })
            }
            if (postBtn) {
                postBtn.addEventListener('click', () => {
                    if (textarea) this._submitPending(textarea.value)
                })
            }
            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => this._cancelPending())
            }
        }
    }

    _submitPending(value) {
        const msg = (value || '').trim()
        if (!msg || !this.pendingPin) return
        const { sceneX, sceneY, elementId, elementFracX, elementFracY } = this.pendingPin
        const partnerIds = [...this._mentionedPartnerIds]
        this._mentionedPartnerIds = []
        this._pendingDraftText = ''
        this._hideMentionDropdown()
        this._createComment(sceneX, sceneY, msg, partnerIds, elementId, elementFracX, elementFracY)
    }

    _cancelPending() {
        this._hideMentionDropdown()
        this.pendingPin = null
        this._pendingDraftText = ''
        this.commentMode = false
        this._applyOverlayCursor()
        this._renderPins()
    }

    _renderToggleBtn() {
        if (!this.toggleBtnEl) return
        const activeCount = this.comments.filter(c => !c.is_resolved).length
        const badge = this.toggleBtnEl.querySelector('.o-excalidraw-comment-badge')
        if (badge) {
            badge.textContent = activeCount > 9 ? '9+' : String(activeCount)
            badge.style.display = activeCount > 0 ? 'flex' : 'none'
        }
        this.toggleBtnEl.style.background = this.panelOpen ? '#f97316' : 'white'
        this.toggleBtnEl.style.color = this.panelOpen ? 'white' : '#374151'
    }

    _renderPanel() {
        if (!this.panelEl) return
        if (!this.panelOpen) {
            this.panelEl.style.display = 'none'
            return
        }
        this.panelEl.style.display = 'flex'

        // Restore dragged position if set
        if (this._panelPos) {
            this.panelEl.style.top = this._panelPos.top + 'px'
            this.panelEl.style.left = this._panelPos.left + 'px'
            this.panelEl.style.right = 'auto'
        } else {
            this.panelEl.style.top = '10px'
            this.panelEl.style.right = '10px'
            this.panelEl.style.left = 'auto'
        }

        const active = this.comments.filter(c => !c.is_resolved)
            .sort((a, b) => new Date(b.create_date) - new Date(a.create_date))
        const resolved = this.comments.filter(c => c.is_resolved)
            .sort((a, b) => new Date(b.create_date) - new Date(a.create_date))

        const totalCount = this.comments.length

        let commentsHtml = ''
        if (totalCount === 0) {
            commentsHtml = `
                <p style="font-size:13px;color:#9ca3af;text-align:center;margin-top:40px;line-height:1.6;">
                    No comments yet.<br/>
                    <span style="font-size:12px;">Click <strong>Comment</strong> then click anywhere on the canvas.</span>
                </p>`
        } else {
            commentsHtml += active.map(c => this._commentCardHtml(c)).join('')
            if (resolved.length > 0) {
                commentsHtml += `
                    <div style="margin-top:8px;">
                        <button class="o-excalidraw-resolved-toggle"
                                style="background:none;border:none;cursor:pointer;font-size:12px;
                                       color:#9ca3af;padding:4px 0;display:flex;align-items:center;gap:4px;">
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            ${this.showResolved ? 'Hide' : 'Show'} ${resolved.length} resolved
                        </button>
                        ${this.showResolved ? resolved.map(c => this._commentCardHtml(c)).join('') : ''}
                    </div>`
            }
        }

        this.panelEl.innerHTML = `
            <!-- Header (draggable) -->
            <div class="o-excalidraw-panel-header" style="padding:10px 14px;border-bottom:1px solid #e5e7eb;
                        display:flex;align-items:center;justify-content:space-between;flex-shrink:0;border-radius:8px 8px 0 0;">
                <span style="font-size:13px;font-weight:600;color:#111;display:flex;align-items:center;gap:6px;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;">
                        <circle cx="9" cy="5" r="1" fill="#9ca3af"/><circle cx="15" cy="5" r="1" fill="#9ca3af"/>
                        <circle cx="9" cy="12" r="1" fill="#9ca3af"/><circle cx="15" cy="12" r="1" fill="#9ca3af"/>
                        <circle cx="9" cy="19" r="1" fill="#9ca3af"/><circle cx="15" cy="19" r="1" fill="#9ca3af"/>
                    </svg>
                    Comments${totalCount > 0 ? ` (${totalCount})` : ''}
                </span>
                <div style="display:flex;gap:4px;align-items:center;">
                    <button class="o-excalidraw-refresh-btn" title="Refresh"
                            style="background:none;border:none;cursor:pointer;padding:4px;color:#9ca3af;">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                        </svg>
                    </button>
                    <button class="o-excalidraw-close-btn"
                            style="background:none;border:none;cursor:pointer;padding:4px;color:#9ca3af;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                    </button>
                </div>
            </div>
            <!-- Comment list -->
            <div style="flex:1;overflow-y:auto;padding:10px 10px 0;">
                ${commentsHtml}
                <div style="height:10px;"></div>
            </div>
            <!-- Add comment button -->
            <div style="padding:10px;border-top:1px solid #f3f4f6;flex-shrink:0;">
                <button class="o-excalidraw-add-btn"
                        style="width:100%;padding:8px;
                               background:${this.commentMode ? '#fff7ed' : '#f9fafb'};
                               color:${this.commentMode ? '#f97316' : '#374151'};
                               border:1px solid ${this.commentMode ? '#fed7aa' : '#e5e7eb'};
                               border-radius:6px;cursor:pointer;font-size:13px;font-weight:500;
                               display:flex;align-items:center;justify-content:center;gap:6px;">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                    ${this.commentMode ? 'Click canvas to place…' : 'Add comment'}
                </button>
            </div>`

        // Wire up panel buttons
        this.panelEl.querySelector('.o-excalidraw-close-btn')?.addEventListener('click', () => {
            this.panelOpen = false
            this._renderPanel()
            this._renderToggleBtn()
        })
        this.panelEl.querySelector('.o-excalidraw-refresh-btn')?.addEventListener('click', () => {
            this._fetchComments()
        })
        this.panelEl.querySelector('.o-excalidraw-add-btn')?.addEventListener('click', () => {
            this.commentMode = !this.commentMode
            if (!this.commentMode) this.pendingPin = null
            this._applyOverlayCursor()
            this._renderPins()
            this._renderPanel()
        })
        this.panelEl.querySelector('.o-excalidraw-resolved-toggle')?.addEventListener('click', () => {
            this.showResolved = !this.showResolved
            this._renderPanel()
        })

        // Wire up comment card resolve/delete/focus buttons
        this.panelEl.querySelectorAll('[data-resolve-id]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation()
                this._resolveComment(parseInt(btn.dataset.resolveId))
            })
        })
        this.panelEl.querySelectorAll('[data-delete-id]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation()
                this._deleteComment(parseInt(btn.dataset.deleteId))
            })
        })
        this.panelEl.querySelectorAll('[data-focus-id]').forEach(card => {
            card.addEventListener('click', () => {
                const id = parseInt(card.dataset.focusId)
                this.activeCommentId = id
                const comment = this.comments.find(c => c.id === id)
                if (comment) this._scrollCanvasToComment(comment)
                this._renderPins()
                this._renderPanel()
            })
        })

        this._makePanelDraggable()
    }

    _makePanelDraggable() {
        const header = this.panelEl.querySelector('.o-excalidraw-panel-header')
        if (!header) return

        const onMouseMove = (e) => {
            const containerRect = this.container.getBoundingClientRect()
            const panelRect = this.panelEl.getBoundingClientRect()
            let newLeft = e.clientX - containerRect.left - this._dragOffsetX
            let newTop = e.clientY - containerRect.top - this._dragOffsetY
            // Keep panel within container bounds
            newLeft = Math.max(0, Math.min(newLeft, containerRect.width - panelRect.width))
            newTop = Math.max(0, Math.min(newTop, containerRect.height - 40))
            this._panelPos = { top: newTop, left: newLeft }
            this.panelEl.style.top = newTop + 'px'
            this.panelEl.style.left = newLeft + 'px'
            this.panelEl.style.right = 'auto'
        }

        const onMouseUp = () => {
            document.removeEventListener('mousemove', onMouseMove)
            document.removeEventListener('mouseup', onMouseUp)
            header.style.cursor = 'grab'
        }

        header.addEventListener('mousedown', (e) => {
            // Don't drag when clicking buttons inside the header
            if (e.target.closest('button')) return
            e.preventDefault()
            const panelRect = this.panelEl.getBoundingClientRect()
            const containerRect = this.container.getBoundingClientRect()
            this._dragOffsetX = e.clientX - panelRect.left
            this._dragOffsetY = e.clientY - panelRect.top
            // If still right-anchored, convert to left/top
            if (!this._panelPos) {
                this._panelPos = {
                    top: panelRect.top - containerRect.top,
                    left: panelRect.left - containerRect.left,
                }
            }
            this.panelEl.style.left = this._panelPos.left + 'px'
            this.panelEl.style.top = this._panelPos.top + 'px'
            this.panelEl.style.right = 'auto'
            header.style.cursor = 'grabbing'
            document.addEventListener('mousemove', onMouseMove)
            document.addEventListener('mouseup', onMouseUp)
        })
    }

    _commentCardHtml(comment) {
        const isActive = this.activeCommentId === comment.id
        const isResolved = comment.is_resolved
        const initial = (comment.user_name || '?')[0].toUpperCase()
        const avatarBg = isResolved ? '#9ca3af' : '#f97316'
        const borderColor = isActive ? '#f97316' : '#f3f4f6'
        const bg = isActive ? '#fff7ed' : isResolved ? '#f9fafb' : 'white'
        const opacity = isResolved ? '0.65' : '1'
        const resolveColor = isResolved ? '#10b981' : '#d1d5db'
        const resolveTitle = isResolved ? 'Unresolve' : 'Mark resolved'
        const isOwner = comment.user_id === this.currentUser.uid
        const date = comment.create_date ? new Date(comment.create_date) : null
        const dateLabel = date ? date.toLocaleString(undefined, {
            month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
        }) : ''

        const deleteBtn = isOwner ? `
            <button data-delete-id="${comment.id}" title="Delete"
                    style="background:none;border:none;cursor:pointer;padding:2px;color:#d1d5db;border-radius:3px;">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                </svg>
            </button>` : ''

        return `
            <div data-focus-id="${comment.id}"
                 style="padding:8px 10px;border-radius:6px;border:1px solid ${borderColor};
                        margin-bottom:6px;background:${bg};opacity:${opacity};
                        cursor:pointer;transition:border-color 0.15s,background 0.15s;">
                <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:4px;">
                    <div style="width:22px;height:22px;border-radius:50%;background:${avatarBg};
                                color:white;display:flex;align-items:center;justify-content:center;
                                font-size:11px;font-weight:700;flex-shrink:0;margin-top:1px;">
                        ${this._esc(initial)}
                    </div>
                    <div style="flex:1;min-width:0;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:12px;font-weight:600;color:#374151;">
                                ${this._esc(comment.user_name || '')}
                            </span>
                            <div style="display:flex;gap:2px;">
                                <button data-resolve-id="${comment.id}" title="${resolveTitle}"
                                        style="background:none;border:none;cursor:pointer;padding:2px;color:${resolveColor};border-radius:3px;">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                        <polyline points="20 6 9 17 4 12"/>
                                    </svg>
                                </button>
                                ${deleteBtn}
                            </div>
                        </div>
                        <p style="font-size:13px;color:#374151;margin:2px 0 0;line-height:1.5;word-break:break-word;">
                            ${this._renderMentions(comment.message || '')}
                        </p>
                        <span style="font-size:11px;color:#d1d5db;">${this._esc(dateLabel)}</span>
                    </div>
                </div>
            </div>`
    }

    _scrollCanvasToComment(comment) {
        const api = this.getExcalidrawAPI()
        if (!api) return
        const appState = api.getAppState()
        const zoom = appState.zoom?.value || 1
        const newScrollX = appState.width / 2 / zoom - comment.x
        const newScrollY = appState.height / 2 / zoom - comment.y
        api.updateScene({ appState: { scrollX: newScrollX, scrollY: newScrollY } })
    }

    // ─── Utility ─────────────────────────────────────────────────────────────

    _esc(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
    }

    // Render @Name mentions as highlighted spans in comment text
    _renderMentions(text) {
        return this._esc(text).replace(/@(\S+)/g, (_, name) =>
            `<span style="color:#6366f1;font-weight:600;">@${name}</span>`
        )
    }
}

// Expose globally so excalidraw_widget.js can instantiate it
window.ExcalidrawComments = ExcalidrawComments
