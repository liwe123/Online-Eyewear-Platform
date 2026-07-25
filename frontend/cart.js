// 丹智慧眼 - 购物车模块（localStorage 实现，无需后端）
// 依赖 common.js（showToast / resolveImageUrl / setImgFallback）
// 页面需提供 id="cart-btn" 的按钮与 id="cart-badge" 的角标元素

const CART_KEY = 'dz_cart';

// 读取购物车
function getCart() {
    try {
        return JSON.parse(localStorage.getItem(CART_KEY)) || [];
    } catch (e) {
        return [];
    }
}

// 保存购物车并刷新角标
function saveCart(cart) {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
    updateCartBadge();
}

// 更新导航栏角标（数量为 0 时隐藏）
function updateCartBadge() {
    const badge = document.getElementById('cart-badge');
    if (!badge) return;
    const total = getCart().reduce((sum, item) => sum + (item.qty || 0), 0);
    badge.textContent = total;
    badge.style.display = total > 0 ? '' : 'none';
}

/**
 * 加入购物车
 * @param {{glasses_id, frame_shape, price, image_url}} item 商品信息
 */
function addToCart(item) {
    const cart = getCart();
    const existing = cart.find(c => c.glasses_id === item.glasses_id);
    if (existing) {
        existing.qty += 1;
    } else {
        cart.push({
            glasses_id: item.glasses_id,
            frame_shape: item.frame_shape,
            name: item.name || '',
            brand: item.brand || '',
            price: parseFloat(item.price) || 0,
            image_url: item.image_url || '',
            qty: 1
        });
    }
    saveCart(cart);
    showToast('已加入购物车', 'success');
}

// 修改某项数量（delta 可为负），数量降到 0 时移除
function changeCartQty(glassesId, delta) {
    let cart = getCart();
    const item = cart.find(c => c.glasses_id === glassesId);
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) {
        cart = cart.filter(c => c.glasses_id !== glassesId);
    }
    saveCart(cart);
    renderCartModal();
}

// 删除单项
function removeCartItem(glassesId) {
    saveCart(getCart().filter(c => c.glasses_id !== glassesId));
    renderCartModal();
}

// 清空购物车
function clearCart() {
    saveCart([]);
    renderCartModal();
    showToast('购物车已清空', 'info');
}

// 渲染购物车 Modal 内容
function renderCartModal() {
    const body = document.getElementById('cart-modal-body');
    const foot = document.getElementById('cart-modal-footer');
    if (!body) return;

    const cart = getCart();
    if (cart.length === 0) {
        body.innerHTML = '<p class="text-center text-muted py-4 mb-0">购物车是空的，快去挑选心仪的眼镜吧</p>';
        if (foot) foot.style.display = 'none';
        return;
    }

    let total = 0;
    const rows = cart.map(item => {
        const subtotal = item.price * item.qty;
        total += subtotal;
        // 数据来自后端库（admin CRUD / CSV 导入），渲染前转义防存储型 XSS
        const safeShape = escapeHtml(item.frame_shape);
        const safeIdAttr = escapeHtml(escapeJsString(item.glasses_id));
        const safeName = escapeHtml(item.name || '');
        const safeBrand = escapeHtml(item.brand || '');
        const displayName = item.name
            ? (safeBrand ? safeBrand + ' · ' + safeName : safeName)
            : safeShape + '眼镜';
        return `
        <div class="cart-item">
            <img src="${escapeHtml(resolveImageUrl(item.image_url))}" alt="${safeShape}"
                 onerror="this.onerror=null;this.src=IMG_PLACEHOLDER;">
            <div class="cart-item-info">
                <div class="cart-item-name">${displayName}</div>
                <div class="cart-item-price">¥${item.price.toFixed(2)}</div>
            </div>
            <div class="cart-item-qty">
                <button type="button" class="qty-btn" onclick="changeCartQty('${safeIdAttr}', -1)">−</button>
                <span>${parseInt(item.qty, 10) || 1}</span>
                <button type="button" class="qty-btn" onclick="changeCartQty('${safeIdAttr}', 1)">+</button>
            </div>
            <div class="cart-item-subtotal">¥${subtotal.toFixed(2)}</div>
            <button type="button" class="cart-item-remove" title="删除"
                    onclick="removeCartItem('${safeIdAttr}')">
                <i class="fas fa-trash-alt"></i>
            </button>
        </div>`;
    }).join('');

    body.innerHTML = rows;
    if (foot) {
        foot.style.display = '';
        document.getElementById('cart-total').textContent = '¥' + total.toFixed(2);
    }
}

// 动态注入购物车 Modal DOM（避免每个页面重复编写）
function injectCartModal() {
    if (document.getElementById('cartModal')) return;
    const wrapper = document.createElement('div');
    wrapper.innerHTML = `
    <div class="modal fade" id="cartModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"><i class="fas fa-shopping-cart me-2"></i>我的购物车</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
                </div>
                <div class="modal-body" id="cart-modal-body"></div>
                <div class="modal-footer justify-content-between" id="cart-modal-footer">
                    <button type="button" class="btn btn-outline-danger btn-sm" onclick="clearCart()">
                        <i class="fas fa-trash me-1"></i>清空
                    </button>
                    <div class="d-flex align-items-center gap-3">
                        <span class="fw-bold">合计：<span id="cart-total" class="cart-total">¥0.00</span></span>
                        <button type="button" class="btn btn-primary-custom btn-sm"
                                onclick="showToast('结算功能演示中，暂未开放', 'info')">
                            去结算 <i class="fas fa-arrow-right ms-1"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>`;
    document.body.appendChild(wrapper.firstElementChild);
}

// 初始化：注入 Modal、绑定按钮、刷新角标
document.addEventListener('DOMContentLoaded', function () {
    injectCartModal();
    updateCartBadge();

    const cartBtn = document.getElementById('cart-btn');
    if (cartBtn) {
        cartBtn.addEventListener('click', function () {
            renderCartModal();
            bootstrap.Modal.getOrCreateInstance(document.getElementById('cartModal')).show();
        });
    }
});
