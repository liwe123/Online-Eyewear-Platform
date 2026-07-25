// 丹智慧眼 - 共享工具模块（index.html / detail.html 共用）
// 提供：API_BASE、图片URL解析、带超时的请求、图片回退、Toast 提示

// API 地址：优先使用页面 data 属性，否则自动检测当前域名 + 5000 端口
const API_BASE = document.documentElement.dataset.apiBase
    || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? `http://${window.location.hostname}:5000`
        : `${window.location.protocol}//${window.location.hostname}`);

// 请求配置
const FETCH_TIMEOUT = 30000;  // 30秒超时
const MAX_RETRIES = 1;         // 重试次数

// 图片加载失败的默认占位 SVG（Data URI，避免外部依赖）
const IMG_PLACEHOLDER = 'data:image/svg+xml,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200">'
    + '<rect fill="#f0f0f0" width="300" height="200"/>'
    + '<text fill="#999" font-size="16" font-family="sans-serif" text-anchor="middle" x="150" y="105">图片加载失败</text>'
    + '</svg>'
);

/**
 * 解析图片地址：
 * - 以 "/" 开头 → 后端静态路径，拼接 API_BASE
 * - http(s) 开头 → 直接使用
 * - 空值 → 返回占位图
 */
function resolveImageUrl(url) {
    if (!url) return IMG_PLACEHOLDER;
    if (url.charAt(0) === '/') return API_BASE + url;
    return url;
}

/**
 * HTML 转义：防止后端/用户数据中的特殊字符造成 XSS
 * 用于必须拼接触 innerHTML 的场景；优先使用 textContent
 */
function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * 转义用于 JS 字符串上下文（如 onclick 属性内的单引号字符串）
 * 与 escapeHtml 配合：先防 JS 断句，再防 HTML 解析
 */
function escapeJsString(value) {
    return String(value == null ? '' : value)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"')
        .replace(/</g, '\\x3c')
        .replace(/>/g, '\\x3e');
}

/**
 * 带超时的 fetch 封装
 */
function fetchWithTimeout(url, options = {}, timeout = FETCH_TIMEOUT) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    return fetch(url, { ...options, signal: controller.signal })
        .finally(() => clearTimeout(timer));
}

/**
 * 带重试的 API 请求
 */
async function apiRequest(url, options = {}, retries = MAX_RETRIES) {
    for (let i = 0; i <= retries; i++) {
        try {
            const response = await fetchWithTimeout(url, options);
            const result = await response.json();
            return result;
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('请求超时，请稍后重试');
            }
            if (i === retries) throw error;
            // 等待后重试
            await new Promise(r => setTimeout(r, 1000));
        }
    }
}

/**
 * 为图片设置错误回退（内联 SVG，不依赖外链）
 */
function setImgFallback(img, fallbackSrc) {
    img.onerror = function () {
        if (this.src !== fallbackSrc) {
            this.src = fallbackSrc || IMG_PLACEHOLDER;
        }
        this.onerror = null; // 防止死循环
    };
}

// ==================== Toast 消息提示 ====================
function showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999';
        document.body.appendChild(container);
    }

    var colors = {
        info: '#1a1a2e',
        danger: '#dc3545',
        warning: '#c9a96e',
        success: '#34c759'
    };

    var toast = document.createElement('div');
    toast.style.cssText =
        'background:' + (colors[type] || colors.info) +
        ';color:white;padding:12px 20px;border-radius:8px;margin-bottom:10px;' +
        'box-shadow:0 4px 12px rgba(0,0,0,0.15);' +
        'animation:slideIn 0.3s ease;max-width:400px;word-wrap:break-word';
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(function () {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(function () { toast.remove(); }, 300);
    }, 4000);
}

// 注入 Toast 动画
(function () {
    var style = document.createElement('style');
    style.textContent =
        '@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}';
    document.head.appendChild(style);
})();
