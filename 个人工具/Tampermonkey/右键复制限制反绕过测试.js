// ==UserScript==
// @name         Anti Copy Restriction Tester
// @namespace    http://tampermonkey.net/
// @version      1.1.0
// @description  For testing copy/right-click interception on host-authorized sites
// @match        *://*/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    const DEBUG = false;
    // 只在这里列出的 host 上启用脚本；留空表示默认不启用，避免误伤所有站点。
    // 支持两种格式：
    // 1. 精确匹配：example.com
    // 2. 通配子域名：*.example.com
    const HOST_RULES = [
        // 'example.com',
        // '*.example.com'

        '*.feishu.cn'
    ];

    function log(...args) {
        if (DEBUG) {
            console.log('[anti-copy-test]', ...args);
        }
    }

    function normalizeHost(host) {
        return String(host || '').trim().toLowerCase();
    }

    function isHostMatched(hostname, rule) {
        const normalizedHostname = normalizeHost(hostname);
        const normalizedRule = normalizeHost(rule);

        if (!normalizedHostname || !normalizedRule) {
            return false;
        }

        if (normalizedRule.startsWith('*.')) {
            const suffix = normalizedRule.slice(2);
            return normalizedHostname === suffix || normalizedHostname.endsWith(`.${suffix}`);
        }

        return normalizedHostname === normalizedRule;
    }

    function shouldEnableForCurrentHost() {
        if (!Array.isArray(HOST_RULES) || HOST_RULES.length === 0) {
            return false;
        }

        const hostname = window.location.hostname;
        return HOST_RULES.some((rule) => isHostMatched(hostname, rule));
    }

    function isCopyShortcut(event) {
        const key = (event.key || '').toLowerCase();
        const code = (event.code || '').toLowerCase();
        const hasMeta = event.ctrlKey || event.metaKey;

        return hasMeta && (
            key === 'c' ||
            key === 'x' ||
            key === 'a' ||
            code === 'keyc' ||
            code === 'keyx' ||
            code === 'keya'
        );
    }

    function stopPageInterception(event) {
        try {
            event.stopImmediatePropagation();
            event.stopPropagation();
        } catch (e) {
            log('stop propagation failed', e);
        }
    }

    function allowCopyRelatedEvent(event) {
        stopPageInterception(event);
    }

    function allowKeyEvent(event) {
        if (isCopyShortcut(event)) {
            stopPageInterception(event);
        }
    }

    function clearInlineHandlers(node) {
        if (!node || node.nodeType !== 1) {
            return;
        }

        const attrs = [
            'oncopy',
            'oncut',
            'onpaste',
            'oncontextmenu',
            'onselectstart',
            'onmousedown',
            'onmouseup',
            'ondragstart',
            'onkeydown',
            'onkeyup'
        ];

        for (const attr of attrs) {
            if (node.hasAttribute && node.hasAttribute(attr)) {
                node.removeAttribute(attr);
            }

            try {
                if (attr in node) {
                    node[attr] = null;
                }
            } catch (e) {
                log('clear inline handler failed', attr, e);
            }
        }
    }

    function clearGlobalInlineHandlers() {
        const targets = [
            window,
            document,
            document.documentElement,
            document.body
        ];

        const props = [
            'oncopy',
            'oncut',
            'onpaste',
            'oncontextmenu',
            'onselectstart',
            'onmousedown',
            'onmouseup',
            'ondragstart',
            'onkeydown',
            'onkeyup'
        ];

        for (const target of targets) {
            if (!target) {
                continue;
            }

            for (const prop of props) {
                try {
                    if (prop in target) {
                        target[prop] = null;
                    }
                } catch (e) {
                    log('clear global handler failed', prop, e);
                }
            }
        }
    }

    function injectStyle() {
        const style = document.createElement('style');
        style.id = '__anti_copy_test_style__';
        style.textContent = `
            * {
                -webkit-user-select: text !important;
                -moz-user-select: text !important;
                -ms-user-select: text !important;
                user-select: text !important;
                -webkit-touch-callout: default !important;
            }

            input, textarea {
                -webkit-user-select: auto !important;
                user-select: auto !important;
            }
        `;

        const parent = document.documentElement || document.head || document.body;
        if (parent) {
            parent.appendChild(style);
        }
    }

    function patchAddEventListener() {
        const rawAddEventListener = EventTarget.prototype.addEventListener;

        EventTarget.prototype.addEventListener = function (type, listener, options) {
            const blockedTypes = new Set([
                'copy',
                'cut',
                'contextmenu',
                'selectstart',
                'dragstart'
            ]);

            if (blockedTypes.has(type)) {
                const wrapped = function (event) {
                    const rawPreventDefault = event.preventDefault;
                    let calledPreventDefault = false;

                    event.preventDefault = function () {
                        calledPreventDefault = true;
                        log('preventDefault blocked for', type);
                    };

                    try {
                        return listener.call(this, event);
                    } finally {
                        event.preventDefault = rawPreventDefault;
                        if (calledPreventDefault) {
                            log('listener attempted to block', type);
                        }
                    }
                };

                return rawAddEventListener.call(this, type, wrapped, options);
            }

            if (type === 'keydown') {
                const wrapped = function (event) {
                    if (isCopyShortcut(event)) {
                        const rawPreventDefault = event.preventDefault;
                        let calledPreventDefault = false;

                        event.preventDefault = function () {
                            calledPreventDefault = true;
                            log('preventDefault blocked for keydown copy shortcut');
                        };

                        try {
                            return listener.call(this, event);
                        } finally {
                            event.preventDefault = rawPreventDefault;
                            if (calledPreventDefault) {
                                log('listener attempted to block copy shortcut');
                            }
                        }
                    }

                    return listener.call(this, event);
                };

                return rawAddEventListener.call(this, type, wrapped, options);
            }

            return rawAddEventListener.call(this, type, listener, options);
        };
    }

    function addCaptureGuards() {
        const guardedEvents = [
            'copy',
            'cut',
            'contextmenu',
            'selectstart',
            'dragstart'
        ];

        for (const type of guardedEvents) {
            window.addEventListener(type, allowCopyRelatedEvent, true);
            document.addEventListener(type, allowCopyRelatedEvent, true);
        }

        window.addEventListener('keydown', allowKeyEvent, true);
        document.addEventListener('keydown', allowKeyEvent, true);
    }

    function walkAndClean(root) {
        if (!root) {
            return;
        }

        clearInlineHandlers(root);

        const elements = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (const el of elements) {
            clearInlineHandlers(el);
        }
    }

    function observeDom() {
        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                if (mutation.type === 'attributes' && mutation.target) {
                    clearInlineHandlers(mutation.target);
                }

                if (mutation.addedNodes) {
                    for (const node of mutation.addedNodes) {
                        if (node.nodeType === 1) {
                            walkAndClean(node);
                        }
                    }
                }
            }
        });

        observer.observe(document.documentElement || document, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: [
                'style',
                'oncopy',
                'oncut',
                'onpaste',
                'oncontextmenu',
                'onselectstart',
                'ondragstart',
                'onkeydown'
            ]
        });
    }

    function init() {
        if (!shouldEnableForCurrentHost()) {
            log('skipped for host', window.location.hostname);
            return;
        }

        patchAddEventListener();
        addCaptureGuards();
        clearGlobalInlineHandlers();

        if (document.documentElement) {
            injectStyle();
            walkAndClean(document.documentElement);
            observeDom();
        } else {
            document.addEventListener('DOMContentLoaded', () => {
                injectStyle();
                walkAndClean(document.documentElement);
                observeDom();
            }, { once: true });
        }

        window.addEventListener('load', () => {
            clearGlobalInlineHandlers();
            walkAndClean(document.documentElement);
        }, { once: true });

        log('initialized');
    }

    init();
})();
