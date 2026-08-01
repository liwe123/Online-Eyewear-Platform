// 丹智慧眼 - 前端主逻辑（首页）
// 依赖 common.js（API_BASE / apiRequest / resolveImageUrl / setImgFallback / showToast）
// 依赖 cart.js（addToCart）

// ==================== 虚拟试戴（调参入口） ====================
const TRYON_WIDTH_FACTOR = 2.4;      // 眼镜宽 = 双眼外角距 × 系数
const TRYON_VERTICAL_OFFSET = 0.04;  // 眼镜整体下移比例（相对眼镜高度，正值向下）
let _faceLandmarks = [];             // 最近一次分析返回的 468 归一化关键点
const _tryonImgCache = {};           // 眼镜 PNG 内存缓存，避免重复加载

// ==================== 页面初始化 ====================
document.addEventListener('DOMContentLoaded', function () {
    // 页脚年份动态更新
    const copyrightYear = document.getElementById('copyright-year');
    if (copyrightYear) copyrightYear.textContent = new Date().getFullYear();

    loadRecommendedGlasses([]);
    loadShopGlasses();

    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('face-upload');
    if (uploadArea && fileInput) {
        uploadArea.addEventListener('click', () => fileInput.click());

        // 键盘可访问性：Enter / 空格 触发文件选择
        uploadArea.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInput.click();
            }
        });

        // 文件选择预览
        fileInput.addEventListener('change', function (e) {
            const file = e.target.files && e.target.files[0];
            if (!file) return;

            // 文件大小验证
            if (file.size > 5 * 1024 * 1024) {
                showToast('文件大小超过5MB，请重新选择', 'warning');
                this.value = '';
                return;
            }
            if (!file.type.startsWith('image/')) {
                showToast('请选择图片文件', 'warning');
                this.value = '';
                return;
            }

            const reader = new FileReader();
            reader.onload = (e) => {
                const preview = document.getElementById('face-preview');
                if (preview) {
                    preview.src = e.target.result;
                    preview.style.display = 'block';
                }
                // 换了新照片：旧脸型的关键点已失效，清空试戴与关键点叠加
                _faceLandmarks = [];
                const lmCanvas = document.getElementById('face-landmarks');
                const tryCanvas = document.getElementById('tryon-canvas');
                [lmCanvas, tryCanvas].forEach(function (c) {
                    if (c) c.getContext('2d').clearRect(0, 0, c.width, c.height);
                });
                const tryonNote = document.getElementById('tryon-note');
                if (tryonNote) tryonNote.classList.add('d-none');
                document.querySelectorAll('.glass-card.tryon-active').forEach(function (c) {
                    c.classList.remove('tryon-active');
                });
            };
            reader.readAsDataURL(file);
        });
    }

    const analyzeBtn = document.getElementById('analyze-btn');
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', async function () {
            const fileInputEl = document.getElementById('face-upload');
            const facePreview = document.getElementById('face-preview');
            if (!fileInputEl || !facePreview || facePreview.style.display !== 'block' || !fileInputEl.files || !fileInputEl.files[0]) {
                showToast('请先上传照片！', 'warning');
                return;
            }

            const leftEyeEl = document.getElementById('left-eye');
            const rightEyeEl = document.getElementById('right-eye');
            const pupilDistanceEl = document.getElementById('pupil-distance');
            const cornealCurvatureEl = document.getElementById('corneal-curvature');
            const matchProgress = document.getElementById('match-progress');
            if (!leftEyeEl || !rightEyeEl || !pupilDistanceEl || !cornealCurvatureEl || !matchProgress) {
                showToast('页面初始化不完整，请刷新后重试', 'danger');
                return;
            }

            const leftRaw = leftEyeEl.value.trim();
            const rightRaw = rightEyeEl.value.trim();
            const pdRaw = pupilDistanceEl.value.trim();
            const ccRaw = cornealCurvatureEl.value.trim();

            const leftEye = parseFloat(leftRaw) || 0;
            const rightEye = parseFloat(rightRaw) || 0;
            const pupilDistance = parseFloat(pdRaw);
            const cornealCurvature = ccRaw === '' ? 43.0 : parseFloat(ccRaw);

            if (leftRaw !== '' && (leftEye < -20 || leftEye > 1000)) { showToast('左眼度数超出范围（-20 ~ 1000），请检查输入', 'warning'); return; }
            if (rightRaw !== '' && (rightEye < -20 || rightEye > 1000)) { showToast('右眼度数超出范围（-20 ~ 1000），请检查输入', 'warning'); return; }
            if (isNaN(pupilDistance) || pupilDistance < 30 || pupilDistance > 80) { showToast('瞳距需在 30 ~ 80mm 之间，请检查输入', 'warning'); return; }
            if (isNaN(cornealCurvature) || cornealCurvature < 30 || cornealCurvature > 50) { showToast('角膜曲率需在 30 ~ 50D 之间，请检查输入', 'warning'); return; }

            const myopiaDegree = (leftEye + rightEye) / 2;
            const btn = this;
            const originalHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>分析中...';

            const formData = new FormData();
            formData.append('image', fileInputEl.files[0]);
            formData.append('pupil_distance', pupilDistance);
            formData.append('corneal_curvature', cornealCurvature);
            formData.append('myopia_degree', myopiaDegree);

            try {
                const result = await apiRequest(API_BASE + '/api/user/submit', { method: 'POST', body: formData });
                if (result.code === 200) {
                    const payload = result.data || {};
                    const recs = payload.recommendation || [];
                    _faceLandmarks = payload.landmarks || [];
                    renderFaceReport(payload);
                    if (payload.landmarks && payload.landmarks.length) drawLandmarks(payload.landmarks);
                    matchProgress.style.width = recs.length === 0 ? '0%' : '92%';
                    loadRecommendedGlasses(recs);
                    if (recs.length > 0) renderTryOn(recs[0]);   // 自动试戴推荐第 1 款
                    if (recs.length === 0) showToast('未找到合适的镜框', 'warning');
                } else {
                    showToast('错误：' + (result.msg || '分析失败'), 'danger');
                }
            } catch (error) {
                console.error('API调用失败：', error);
                showToast(error.message || '后端服务未启动或网络错误，请检查后端是否运行', 'danger');
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
        });
    }

    // 换一款按钮：循环高亮当前推荐
    const tryAnotherBtn = document.getElementById('try-another');
    if (tryAnotherBtn) {
        tryAnotherBtn.addEventListener('click', function () {
            const recs = window._recommendations;
            if (!recs || recs.length === 0) {
                showToast('暂无推荐眼镜，请先进行AI分析', 'info');
                return;
            }
            window._currentIndex = window._currentIndex || 0;
            window._currentIndex = (window._currentIndex + 1) % recs.length;
            const glass = recs[window._currentIndex];
            renderTryOn(glass);   // 换款同时切换试戴
            showToast('已切换至：' + (glass.name || glass.frame_shape + '眼镜'), 'success');
            const products = document.getElementById('products');
            if (products) products.scrollIntoView({ behavior: 'smooth' });
        });
    }

    // 商城查询按钮 & 回车搜索
    const shopSearchBtn = document.getElementById('shop-search-btn');
    const shopKeyword = document.getElementById('shop-filter-keyword');
    if (shopSearchBtn) {
        shopSearchBtn.addEventListener('click', function () {
            shopState.page = 1;
            loadShopGlasses();
        });
    }
    if (shopKeyword) {
        shopKeyword.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                shopState.page = 1;
                loadShopGlasses();
            }
        });
    }

    const subscribeBtn = document.getElementById('subscribe-btn');
    if (subscribeBtn) {
        subscribeBtn.addEventListener('click', function () {
            const emailInput = document.getElementById('subscribe-email');
            if (!emailInput) return;
            const email = emailInput.value.trim();
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
                showToast('请输入有效的邮箱地址', 'warning');
                return;
            }
            emailInput.value = '';
            showToast('订阅成功（演示）', 'success');
        });
    }

});

// ==================== AI 推荐列表 ====================
// HTML 转义统一使用 common.js 提供的 escapeHtml

function renderFaceReport(data) {
    const report = document.getElementById('analysis-report');
    if (!report) return;
    const shape = data.face_shape || '未知';
    const count = data.landmarks_count || 0;
    const analysis = data.analysis || [];
    const verdict = data.verdict || '';

    let html = '';
    html += '<div class="report-head">';
    html += '  <div class="feature-points"><span class="fp-num">' + count + '</span><span class="fp-label">个面部特征点已分析</span></div>';
    html += '  <div class="face-shape-badge">脸型判定：<b>' + escapeHtml(shape) + '</b></div>';
    html += '</div>';

    const summary = 'AI 已基于 ' + count + ' 个面部特征点完成几何测量，检测到您的脸型为「' + shape + '」';
    html += '<div class="alert alert-info mb-3"><i class="fas fa-info-circle me-2"></i>' + escapeHtml(summary) + '</div>';

    if (verdict) {
        html += '<div class="verdict"><b>判定依据：</b>' + escapeHtml(verdict) + '</div>';
    }
    if (analysis.length) {
        html += '<div class="metric-grid">';
        analysis.forEach(function (m) {
            html += '<div class="metric-card">';
            html += '  <div class="metric-label">' + escapeHtml(m.label) + '</div>';
            html += '  <div class="metric-value">' + escapeHtml(m.value) + '</div>';
            html += '  <div class="metric-desc">' + escapeHtml(m.desc) + '</div>';
            html += '</div>';
        });
        html += '</div>';
    }
    report.innerHTML = html;
}

function drawLandmarks(landmarks) {
    const preview = document.getElementById('face-preview');
    const canvas = document.getElementById('face-landmarks');
    if (!preview || !canvas || !preview.clientWidth) return;
    const w = preview.clientWidth;
    const h = preview.clientHeight;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = 'rgba(99,102,241,0.85)';
    for (let i = 0; i < landmarks.length; i++) {
        const x = landmarks[i][0] * w;
        const y = landmarks[i][1] * h;
        ctx.beginPath();
        ctx.arc(x, y, 1.1, 0, Math.PI * 2);
        ctx.fill();
    }
}

// ==================== 虚拟试戴 ====================

function tryOnUrl(glassesId) {
    // 抠图素材路径：/static/glasses/<id>.jpg → /static/glasses/tryon/<id>.png
    return API_BASE + '/static/glasses/tryon/' + encodeURIComponent(glassesId) + '.png';
}

function renderTryOn(glass) {
    const canvas = document.getElementById('tryon-canvas');
    const preview = document.getElementById('face-preview');
    if (!canvas || !preview || preview.style.display !== 'block') {
        showToast('请先上传照片并完成AI分析', 'info');
        return;
    }
    const gid = glass && glass.glasses_id;
    if (!gid) return;

    const draw = (img) => {
        drawTryOn(preview, canvas, img);
        highlightTryonCard(gid);
        const tryonNote = document.getElementById('tryon-note');
        if (tryonNote) tryonNote.classList.remove('d-none');
    };
    if (_tryonImgCache[gid]) { draw(_tryonImgCache[gid]); return; }

    const img = new Image();
    // CORS 加载，保持 canvas 干净（可截图导出；后端 Flask-CORS 允许前端源）
    img.crossOrigin = 'anonymous';
    img.onload = () => { _tryonImgCache[gid] = img; draw(img); };
    img.onerror = () => {
        drawTryOn(preview, canvas, null);
        showToast('该款暂无试戴素材，请换一款', 'info');
    };
    img.src = tryOnUrl(gid);
}

function drawTryOn(preview, canvas, img) {
    const w = preview.clientWidth;
    const h = preview.clientHeight;
    if (!w || !h) return;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    if (!img) return;

    const lm = _faceLandmarks;
    let W, H, cx, cy, angle = 0;
    // 有 468 关键点 → 按双眼外角（33/263）定位：宽=眼距×系数，旋转对齐眼线
    if (lm && lm.length > 263 && lm[33] && lm[263]) {
        const lx = lm[33][0] * w, ly = lm[33][1] * h;
        const rx = lm[263][0] * w, ry = lm[263][1] * h;
        const eyeDist = Math.hypot(rx - lx, ry - ly);
        if (eyeDist > 1) {
            cx = (lx + rx) / 2;
            cy = (ly + ry) / 2;
            angle = Math.atan2(ry - ly, rx - lx);
            W = eyeDist * TRYON_WIDTH_FACTOR;
            H = W * (img.height / img.width);
        } else { cx = w / 2; cy = h * 0.35; W = w * 0.6; H = W * (img.height / img.width); }
    } else {
        // 无关键点（兜底路径）→ 居中放置
        cx = w / 2; cy = h * 0.35; W = w * 0.6; H = W * (img.height / img.width);
    }
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.drawImage(img, -W / 2, -H / 2 + H * TRYON_VERTICAL_OFFSET, W, H);
    ctx.restore();
}

function highlightTryonCard(glassesId) {
    const id = String(glassesId);
    document.querySelectorAll('.glass-card').forEach(function (card) {
        const btn = card.querySelector('[data-tryon-id]');
        card.classList.toggle('tryon-active', btn && btn.getAttribute('data-tryon-id') === id);
    });
}

function loadRecommendedGlasses(recommendations) {
    const container = document.getElementById('recommended-glasses');
    container.textContent = '';

    if (recommendations.length === 0) {
        const emptyMsg = document.createElement('p');
        emptyMsg.className = 'text-center col-12';
        emptyMsg.textContent = '请上传照片并分析，获取个性化推荐';
        container.appendChild(emptyMsg);
        return;
    }

    window._recommendations = recommendations;
    window._currentIndex = 0;

    recommendations.forEach(function (glass) {
        const col = document.createElement('div');
        col.className = 'col-md-4 col-lg-4';

        const card = document.createElement('div');
        card.className = 'card glass-card';

        const img = document.createElement('img');
        img.src = resolveImageUrl(glass.image_url);
        img.className = 'card-img-top glass-image';
        img.alt = glass.frame_shape + '眼镜';
        img.loading = 'lazy';
        setImgFallback(img);
        card.appendChild(img);

        const cardBody = document.createElement('div');
        cardBody.className = 'card-body';

        const title = document.createElement('h5');
        title.className = 'card-title';
        title.textContent = (glass.name)
            ? ((glass.brand ? glass.brand + ' · ' : '') + glass.name)
            : (glass.frame_shape + '眼镜');
        cardBody.appendChild(title);

        const desc = document.createElement('p');
        desc.className = 'card-text text-muted';
        desc.textContent = glass.frame_material + ' | 折射率: ' + glass.lens_refractive_index;
        cardBody.appendChild(desc);

        if (glass.reason) {
            const reason = document.createElement('div');
            reason.className = 'rec-reason';
            const icon = document.createElement('i');
            icon.className = 'fas fa-lightbulb';
            reason.appendChild(icon);
            reason.appendChild(document.createTextNode(' ' + glass.reason));
            cardBody.appendChild(reason);
        }

        const priceRow = document.createElement('div');
        priceRow.className = 'd-flex justify-content-between align-items-center';

        const price = document.createElement('span');
        price.className = 'h5 text-primary mb-0';
        price.textContent = '¥' + Number(glass.price || 0).toFixed(2);
        priceRow.appendChild(price);

        const btnGroup = document.createElement('div');
        btnGroup.className = 'd-flex gap-2';

        const detailBtn = document.createElement('a');
        detailBtn.className = 'btn btn-sm btn-outline-primary';
        detailBtn.textContent = '查看详情';
        detailBtn.href = 'detail.html?glasses_id=' + encodeURIComponent(glass.glasses_id);
        btnGroup.appendChild(detailBtn);

        const tryBtn = document.createElement('button');
        tryBtn.className = 'btn btn-sm btn-tryon';
        tryBtn.innerHTML = '<i class="fas fa-glasses"></i> 试戴';
        tryBtn.title = '在照片上试戴该镜框';
        tryBtn.setAttribute('data-tryon-id', glass.glasses_id);
        tryBtn.addEventListener('click', function () {
            renderTryOn(glass);
        });
        btnGroup.appendChild(tryBtn);

        const cartBtn = document.createElement('button');
        cartBtn.className = 'btn btn-sm btn-outline-primary';
        cartBtn.innerHTML = '<i class="fas fa-cart-plus"></i>';
        cartBtn.title = '加入购物车';
        cartBtn.addEventListener('click', function () {
            addToCart(glass);
        });
        btnGroup.appendChild(cartBtn);

        priceRow.appendChild(btnGroup);
        cardBody.appendChild(priceRow);
        card.appendChild(cardBody);
        col.appendChild(card);
        container.appendChild(col);
    });
}

// ==================== 眼镜商城 ====================

// 商城状态：页码 / 筛选条件
const shopState = {
    page: 1,
    pageSize: 12
};

// 商城请求竞态控制：取消上一次请求 + 令牌防止过期响应覆盖新结果
let shopAbortController = null;
let shopRequestToken = 0;

/**
 * 拉取商城列表并渲染
 */
async function loadShopGlasses() {
    const myToken = ++shopRequestToken;
    // 取消上一次仍在途的请求，避免并发竞态
    if (shopAbortController) shopAbortController.abort();
    shopAbortController = new AbortController();
    const signal = shopAbortController.signal;

    const container = document.getElementById('shop-glasses');
    const frameShape = document.getElementById('shop-filter-shape').value;
    const keyword = document.getElementById('shop-filter-keyword').value.trim();

    const params = new URLSearchParams({
        page: shopState.page,
        page_size: shopState.pageSize
    });
    if (frameShape) params.set('frame_shape', frameShape);
    if (keyword) params.set('keyword', keyword);

    container.innerHTML = '<p class="text-center col-12 text-muted py-4">加载中...</p>';

    try {
        const result = await apiRequest(API_BASE + '/api/glasses/list?' + params.toString(), { signal });
        if (myToken !== shopRequestToken) return; // 已有更新的请求，丢弃过期响应
        if (result.code !== 200) {
            container.textContent = '';
            const errMsg = document.createElement('p');
            errMsg.className = 'text-center col-12 text-muted py-4';
            errMsg.textContent = '加载失败：' + (result.msg || '未知错误');
            container.appendChild(errMsg);
            renderShopPagination(0);
            return;
        }
        renderShopGlasses(result.data.items || []);
        renderShopPagination(result.data.total || 0);
    } catch (error) {
        if (myToken !== shopRequestToken) return; // 请求已被新请求取代，静默丢弃
        console.error('商城列表加载失败：', error);
        container.innerHTML = '<p class="text-center col-12 text-muted py-4">商城服务暂不可用，请稍后重试</p>';
        renderShopPagination(0);
    }
}

/**
 * 渲染商城商品卡片（复用 glass-card 样式）
 */
function renderShopGlasses(items) {
    const container = document.getElementById('shop-glasses');
    container.textContent = '';

    if (items.length === 0) {
        container.innerHTML = '<p class="text-center col-12 text-muted py-4">没有找到符合条件的眼镜</p>';
        return;
    }

    items.forEach(function (glass) {
        const col = document.createElement('div');
        col.className = 'col-6 col-md-4 col-lg-3';

        const card = document.createElement('div');
        card.className = 'card glass-card';

        const img = document.createElement('img');
        img.src = resolveImageUrl(glass.image_url);
        img.className = 'card-img-top glass-image';
        img.alt = glass.frame_shape + '眼镜';
        img.loading = 'lazy';
        setImgFallback(img);
        card.appendChild(img);

        const cardBody = document.createElement('div');
        cardBody.className = 'card-body';

        const title = document.createElement('h5');
        title.className = 'card-title';
        title.textContent = (glass.name)
            ? ((glass.brand ? glass.brand + ' · ' : '') + glass.name)
            : (glass.frame_shape + '眼镜');
        cardBody.appendChild(title);

        const desc = document.createElement('p');
        desc.className = 'card-text text-muted';
        desc.textContent = glass.frame_material + ' | 折射率: ' + glass.lens_refractive_index;
        cardBody.appendChild(desc);

        if (glass.reason) {
            const reason = document.createElement('div');
            reason.className = 'rec-reason';
            const icon = document.createElement('i');
            icon.className = 'fas fa-lightbulb';
            reason.appendChild(icon);
            reason.appendChild(document.createTextNode(' ' + glass.reason));
            cardBody.appendChild(reason);
        }

        const priceRow = document.createElement('div');
        priceRow.className = 'd-flex justify-content-between align-items-center';

        const price = document.createElement('span');
        price.className = 'h5 text-primary mb-0';
        price.textContent = '¥' + Number(glass.price || 0).toFixed(2);
        priceRow.appendChild(price);

        const btnGroup = document.createElement('div');
        btnGroup.className = 'd-flex gap-2';

        // 详情链接（跳 detail.html）
        const detailLink = document.createElement('a');
        detailLink.className = 'btn btn-sm btn-outline-primary';
        detailLink.textContent = '详情';
        detailLink.href = 'detail.html?glasses_id=' + encodeURIComponent(glass.glasses_id);
        btnGroup.appendChild(detailLink);

        // 试戴（需先完成 AI 分析）
        const tryBtn = document.createElement('button');
        tryBtn.className = 'btn btn-sm btn-tryon';
        tryBtn.innerHTML = '<i class="fas fa-glasses"></i> 试戴';
        tryBtn.title = '在已上传照片上试戴该镜框';
        tryBtn.setAttribute('data-tryon-id', glass.glasses_id);
        tryBtn.addEventListener('click', function () {
            renderTryOn(glass);
        });
        btnGroup.appendChild(tryBtn);

        // 加入购物车
        const cartBtn = document.createElement('button');
        cartBtn.className = 'btn btn-sm btn-outline-primary';
        cartBtn.innerHTML = '<i class="fas fa-cart-plus"></i>';
        cartBtn.title = '加入购物车';
        cartBtn.addEventListener('click', function () {
            addToCart(glass);
        });
        btnGroup.appendChild(cartBtn);

        priceRow.appendChild(btnGroup);
        cardBody.appendChild(priceRow);
        card.appendChild(cardBody);
        col.appendChild(card);
        container.appendChild(col);
    });
}

/**
 * 渲染分页器（上一页 / 页码窗口 / 下一页）
 */
function renderShopPagination(total) {
    const ul = document.getElementById('shop-pagination');
    ul.textContent = '';

    const totalPages = Math.ceil(total / shopState.pageSize);
    if (totalPages <= 1) return;

    const current = shopState.page;

    // 生成一个分页项
    function makeItem(label, page, opts = {}) {
        const li = document.createElement('li');
        li.className = 'page-item' + (opts.active ? ' active' : '') + (opts.disabled ? ' disabled' : '');
        const a = document.createElement('a');
        a.className = 'page-link';
        a.href = 'javascript:void(0)';
        a.innerHTML = label;
        if (!opts.disabled && !opts.active) {
            a.addEventListener('click', function () {
                shopState.page = page;
                loadShopGlasses();
                // 滚动回商城顶部，提升翻页体验
                document.getElementById('shop').scrollIntoView({ behavior: 'smooth' });
            });
        }
        li.appendChild(a);
        return li;
    }

    ul.appendChild(makeItem('&laquo;', current - 1, { disabled: current <= 1 }));

    // 页码窗口：当前页 ±2，始终包含首尾页
    const pages = new Set([1, totalPages]);
    for (let p = current - 2; p <= current + 2; p++) {
        if (p >= 1 && p <= totalPages) pages.add(p);
    }
    const sorted = [...pages].sort((a, b) => a - b);
    let prev = 0;
    sorted.forEach(p => {
        if (p - prev > 1) {
            // 页码断层用省略号
            const li = document.createElement('li');
            li.className = 'page-item disabled';
            li.innerHTML = '<span class="page-link">…</span>';
            ul.appendChild(li);
        }
        ul.appendChild(makeItem(String(p), p, { active: p === current }));
        prev = p;
    });

    ul.appendChild(makeItem('&raquo;', current + 1, { disabled: current >= totalPages }));
}
