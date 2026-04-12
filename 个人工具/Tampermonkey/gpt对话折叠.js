// ==UserScript==
// @name         ChatGPT Auto Group Turn Collapser
// @namespace    https://tampermonkey.net/
// @version      1.4.1
// @description  按组自动折叠较早 turn；超过 1.5 倍分组大小时触发；支持同时展开多组；仅监听 turn 级别新增/删除
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    const CONFIG = {
        collapseGroupSize: 6,
        observerDebounceMs: 80,
        healthCheckMs: 1500,
        debug: false
    };

    const AUTO_COLLAPSE_MULTIPLIER = 1.5;

    const TURN_SELECTOR = 'section[data-turn-id][data-testid^="conversation-turn-"]';
    const HIDDEN_CLASS = 'cgpt-auto-group-hidden';
    const PLACEHOLDER_CLASS = 'cgpt-auto-group-placeholder';
    const STICKY_BAR_CLASS = 'cgpt-auto-group-sticky-bar';

    const expandedGroupKeys = new Set();

    let turnsParent = null;
    let turnsObserver = null;
    let healthTimer = null;
    let observerTimer = 0;
    let refreshQueued = false;
    let lastPath = location.pathname;

    function log() {
        if (CONFIG.debug) {
            console.log('[cgpt-auto-group-collapser]', ...arguments);
        }
    }

    function injectStyle() {
        if (document.getElementById('cgpt-auto-group-collapser-style')) {
            return;
        }

        const style = document.createElement('style');
        style.id = 'cgpt-auto-group-collapser-style';
        style.textContent = `
            .${HIDDEN_CLASS} {
                display: none !important;
            }

            .${PLACEHOLDER_CLASS} {
                width: 100%;
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 8px 0;
                padding: 2px 0;
            }

            .${STICKY_BAR_CLASS} {
                position: sticky;
                top: 8px;
                z-index: 20;
                width: 100%;
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 8px 0;
                padding: 2px 0;
                pointer-events: none;
            }

            .cgpt-auto-group-chip {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                max-width: min(680px, calc(100vw - 48px));
                min-height: 34px;
                box-sizing: border-box;
                padding: 4px 10px;
                border: 1px dashed rgba(120, 120, 120, 0.35);
                border-radius: 999px;
                background: rgba(127, 127, 127, 0.10);
                color: inherit;
                font-size: 12px;
                line-height: 1.2;
                overflow: hidden;
                pointer-events: auto;
                backdrop-filter: blur(4px);
            }

            .cgpt-auto-group-title {
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                opacity: 0.9;
            }

            .cgpt-auto-group-btn {
                border: 1px solid rgba(120, 120, 120, 0.35);
                border-radius: 999px;
                background: transparent;
                color: inherit;
                padding: 2px 8px;
                cursor: pointer;
                flex: none;
                font-size: 12px;
                line-height: 1.2;
            }
        `;

        document.documentElement.appendChild(style);
    }

    function getTurnNodes() {
        return Array.from(document.querySelectorAll(TURN_SELECTOR))
            .filter(node => node instanceof HTMLElement);
    }

    function isTurnNode(node) {
        return node instanceof HTMLElement && node.matches(TURN_SELECTOR);
    }

    function getTurnId(turnEl) {
        return turnEl.getAttribute('data-turn-id') || '';
    }

    function pickTurnsParent() {
        const turns = getTurnNodes();
        if (!turns.length) {
            return null;
        }

        const firstParent = turns[0].parentElement;
        if (firstParent && turns.every(node => node.parentElement === firstParent)) {
            return firstParent;
        }

        const counter = new Map();
        for (const node of turns) {
            const parent = node.parentElement;
            if (!parent) {
                continue;
            }
            counter.set(parent, (counter.get(parent) || 0) + 1);
        }

        let bestParent = null;
        let bestCount = 0;
        for (const [parent, count] of counter.entries()) {
            if (count > bestCount) {
                bestParent = parent;
                bestCount = count;
            }
        }

        return bestParent;
    }

    function removeAllUiNodes() {
        document.querySelectorAll(`.${PLACEHOLDER_CLASS}`).forEach(node => node.remove());
        document.querySelectorAll(`.${STICKY_BAR_CLASS}`).forEach(node => node.remove());
    }

    function unhideAllTurns(turns) {
        turns.forEach(turn => {
            turn.classList.remove(HIDDEN_CLASS);
        });
    }

    function getAutoCollapsedTurnCount(totalTurns) {
        const groupSize = CONFIG.collapseGroupSize;
        let remaining = totalTurns;
        let collapsed = 0;

        while (remaining > groupSize * AUTO_COLLAPSE_MULTIPLIER) {
            collapsed += groupSize;
            remaining -= groupSize;
        }

        return Math.min(collapsed, totalTurns);
    }

    function buildGroups(turns) {
        const total = turns.length;
        const collapsedTurnCount = getAutoCollapsedTurnCount(total);
        const groups = [];

        for (let start = 0; start < collapsedTurnCount; start += CONFIG.collapseGroupSize) {
            const endExclusive = Math.min(start + CONFIG.collapseGroupSize, collapsedTurnCount);
            const groupTurns = turns.slice(start, endExclusive);

            if (!groupTurns.length) {
                continue;
            }

            const firstId = getTurnId(groupTurns[0]);
            const lastId = getTurnId(groupTurns[groupTurns.length - 1]);

            groups.push({
                startIndex: start,
                endIndex: endExclusive - 1,
                turns: groupTurns,
                key: `${firstId}__${lastId}__${groupTurns.length}`
            });
        }

        return {
            total,
            collapsedTurnCount,
            groups
        };
    }

    function cleanupExpandedGroupKeys(validGroupKeys) {
        for (const key of Array.from(expandedGroupKeys)) {
            if (!validGroupKeys.has(key)) {
                expandedGroupKeys.delete(key);
            }
        }
    }

    function createChip(titleText, buttonText, onClick) {
        const chip = document.createElement('div');
        chip.className = 'cgpt-auto-group-chip';

        const title = document.createElement('div');
        title.className = 'cgpt-auto-group-title';
        title.textContent = titleText;

        const btn = document.createElement('button');
        btn.className = 'cgpt-auto-group-btn';
        btn.type = 'button';
        btn.textContent = buttonText;
        btn.addEventListener('click', onClick);

        chip.appendChild(title);
        chip.appendChild(btn);

        return chip;
    }

    function insertCollapsedPlaceholder(group, total) {
        const firstTurn = group.turns[0];
        if (!firstTurn || !firstTurn.parentElement) {
            return;
        }

        const wrapper = document.createElement('div');
        wrapper.className = PLACEHOLDER_CLASS;
        wrapper.dataset.groupKey = group.key;

        const titleText = `已折叠较早消息 ${group.startIndex + 1}-${group.endIndex + 1}/${total}（${group.turns.length} 条）`;
        const chip = createChip(titleText, '展开', () => {
            expandedGroupKeys.add(group.key);
            queueRefresh();
        });

        wrapper.appendChild(chip);
        firstTurn.insertAdjacentElement('beforebegin', wrapper);
    }

    function insertExpandedStickyBar(group, total) {
        const firstTurn = group.turns[0];
        if (!firstTurn || !firstTurn.parentElement) {
            return;
        }

        const wrapper = document.createElement('div');
        wrapper.className = STICKY_BAR_CLASS;
        wrapper.dataset.groupKey = group.key;

        const titleText = `已展开较早消息 ${group.startIndex + 1}-${group.endIndex + 1}/${total}`;
        const chip = createChip(titleText, '收起这一组', () => {
            expandedGroupKeys.delete(group.key);
            queueRefresh();
        });

        wrapper.appendChild(chip);
        firstTurn.insertAdjacentElement('beforebegin', wrapper);
    }

    function applyGrouping(turns) {
        const { total, groups } = buildGroups(turns);
        const validGroupKeys = new Set(groups.map(group => group.key));

        cleanupExpandedGroupKeys(validGroupKeys);

        for (const group of groups) {
            const expanded = expandedGroupKeys.has(group.key);

            if (expanded) {
                insertExpandedStickyBar(group, total);
            } else {
                for (const turn of group.turns) {
                    turn.classList.add(HIDDEN_CLASS);
                }
                insertCollapsedPlaceholder(group, total);
            }
        }
    }

    function refreshNow() {
        const turns = getTurnNodes();
        if (!turns.length) {
            return;
        }

        removeAllUiNodes();
        unhideAllTurns(turns);
        applyGrouping(turns);
    }

    function queueRefresh() {
        if (refreshQueued) {
            return;
        }

        refreshQueued = true;
        requestAnimationFrame(() => {
            refreshQueued = false;
            refreshNow();
        });
    }

    function debounceObserverRefresh() {
        clearTimeout(observerTimer);
        observerTimer = window.setTimeout(() => {
            queueRefresh();
        }, CONFIG.observerDebounceMs);
    }

    function disconnectTurnsObserver() {
        if (turnsObserver) {
            turnsObserver.disconnect();
            turnsObserver = null;
        }
        turnsParent = null;
    }

    function attachTurnsObserver() {
        const parent = pickTurnsParent();
        if (!parent) {
            return false;
        }

        if (turnsObserver && turnsParent === parent && document.contains(parent)) {
            return true;
        }

        disconnectTurnsObserver();

        turnsParent = parent;
        turnsObserver = new MutationObserver((mutations) => {
            let hasTurnLevelChange = false;

            for (const mutation of mutations) {
                if (mutation.type !== 'childList') {
                    continue;
                }

                for (const node of mutation.addedNodes) {
                    if (isTurnNode(node)) {
                        hasTurnLevelChange = true;
                        break;
                    }
                }
                if (hasTurnLevelChange) {
                    break;
                }

                for (const node of mutation.removedNodes) {
                    if (isTurnNode(node)) {
                        hasTurnLevelChange = true;
                        break;
                    }
                }
                if (hasTurnLevelChange) {
                    break;
                }
            }

            if (hasTurnLevelChange) {
                debounceObserverRefresh();
            }
        });

        turnsObserver.observe(turnsParent, {
            childList: true,
            subtree: false
        });

        log('turn observer attached', turnsParent);
        return true;
    }

    function ensureObserverBound() {
        const pathChanged = location.pathname !== lastPath;
        const parentInvalid = !turnsParent || !document.contains(turnsParent);

        if (pathChanged) {
            lastPath = location.pathname;
            expandedGroupKeys.clear();
            disconnectTurnsObserver();
        }

        if (!turnsObserver || parentInvalid) {
            const ok = attachTurnsObserver();
            if (ok) {
                queueRefresh();
            }
        }
    }

    function setupHealthCheck() {
        if (healthTimer) {
            clearInterval(healthTimer);
        }

        healthTimer = window.setInterval(() => {
            ensureObserverBound();
        }, CONFIG.healthCheckMs);
    }

    function bootstrap() {
        injectStyle();
        setupHealthCheck();

        ensureObserverBound();
        queueRefresh();

        [300, 800, 1500, 2500].forEach(delay => {
            setTimeout(() => {
                ensureObserverBound();
                queueRefresh();
            }, delay);
        });
    }

    bootstrap();
})();