// 丹智慧眼 - 前端主逻辑（首页）
// 依赖 common.js（API_BASE / apiRequest / resolveImageUrl / setImgFallback / showToast）
// 依赖 cart.js（addToCart）

// ==================== 页面初始化 ====================
document.addEventListener('DOMContentLoaded', function () {
    loadRecommendedGlasses([]);
    loadShopGlasses();

    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('face-upload');
    uploadArea.addEventListener('click', () => fileInput.click());

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
            preview.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(file);
    });

    // AI智能分析
    document.getElementById('analyze-btn').addEventListener('click', async function () {
        const facePreview = document.getElementById('face-preview');
        if (facePreview.style.display !== 'block') {
            showToast('请先上传照片！', 'warning');
            return;
        }

        // ---------- 客户端数值校验 ----------
        const leftRaw = document.getElementById('left-eye').value.trim();
        const rightRaw = document.getElementById('right-eye').value.trim();
        const pdRaw = document.getElementById('pupil-distance').value.trim();
        const ccRaw = document.getElementById('corneal-curvature').value.trim();

        const leftEye = parseFloat(leftRaw) || 0;
        const rightEye = parseFloat(rightRaw) || 0;
        const pupilDistance = parseFloat(pdRaw);
        // 角膜曲率留空时使用默认值 43.0
        const cornealCurvature = ccRaw === '' ? 43.0 : parseFloat(ccRaw);

        if (leftRaw !== '' && (leftEye < -20 || leftEye > 10)) {
            showToast('左眼度数超出范围（-20 ~ 10），请检查输入', 'warning');
            return;
        }
        if (rightRaw !== '' && (rightEye < -20 || rightEye > 10)) {
            showToast('右眼度数超出范围（-20 ~ 10），请检查输入', 'warning');
            return;
        }
        if (isNaN(pupilDistance) || pupilDistance < 30 || pupilDistance > 80) {
            showToast('瞳距需在 30 ~ 80mm 之间，请检查输入', 'warning');
            return;
        }
        if (isNaN(cornealCurvature) || cornealCurvature < 30 || cornealCurvature > 50) {
            showToast('角膜曲率需在 30 ~ 50D 之间，请检查输入', 'warning');
            return;
        }

        const myopiaDegree = (leftEye + rightEye) / 2;

        const analyzeBtn = this;
        analyzeBtn.disabled = true;
        analyzeBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>分析中...';

        const formData = new FormData();
        formData.append('image', fileInput.files[0]);
        formData.append('pupil_distance', pupilDistance);
        formData.append('corneal_curvature', cornealCurvature);
        formData.append('myopia_degree', myopiaDegree);

        try {
            const result = await apiRequest(API_BASE + '/api/user/submit', {
                method: 'POST',
                body: formData
            });

            if (result.code === 200) {
                const recs = result.data.recommendation || [];
                if (recs.length === 0) {
                    document.getElementById('analysis-result').textContent =
                        '分析完成！检测到您的脸型为' + result.data.face_shape + '，但暂时没有适配您度数的眼镜，推荐放宽筛选条件后再试。';
                    document.getElementById('match-progress').style.width = '60%';
                    loadRecommendedGlasses([]);
                    showToast('未找到适配您度数范围的眼镜', 'warning');
                } else {
                    document.getElementById('analysis-result').textContent =
                        '分析完成！检测到您的脸型为' + result.data.face_shape + '，为您推荐以下眼镜。';
                    document.getElementById('match-progress').style.width = '92%';
                    loadRecommendedGlasses(recs);
                    showVirtualTryOn(facePreview.src, recs[0].image_url);
                }
            } else {
                showToast('错误：' + result.msg, 'danger');
            }
        } catch (error) {
            console.error('API调用失败：', error);
            showToast(error.message || '后端服务未启动或网络错误，请检查后端是否运行', 'danger');
        } finally {
            analyzeBtn.disabled = false;
            analyzeBtn.innerHTML = '<i class="fas fa-magic me-2"></i> AI智能分析';
        }
    });

    // 换一款按钮
    document.getElementById('try-another').addEventListener('click', function () {
        const recs = window._recommendations;
        if (!recs || recs.length === 0) {
            showToast('暂无推荐眼镜，请先进行AI分析', 'info');
            return;
        }
        window._currentIndex = (window._currentIndex + 1) % recs.length;
        const glass = recs[window._currentIndex];
        const preview = document.getElementById('face-preview');
        if (preview.style.display === 'block' && preview.src) {
            showVirtualTryOn(preview.src, glass.image_url);
        }
    });

    // 商城查询按钮 & 回车搜索
    document.getElementById('shop-search-btn').addEventListener('click', function () {
        shopState.page = 1;
        loadShopGlasses();
    });
    document.getElementById('shop-filter-keyword').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            shopState.page = 1;
            loadShopGlasses();
        }
    });

    // 页脚订阅：校验邮箱格式后提示（演示）
    document.getElementById('subscribe-btn').addEventListener('click', function () {
        const emailInput = document.getElementById('subscribe-email');
        const email = emailInput.value.trim();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            showToast('请输入有效的邮箱地址', 'warning');
            return;
        }
        emailInput.value = '';
        showToast('订阅成功（演示）', 'success');
    });

    // 演示虚拟试戴
    setTimeout(function () {
        document.getElementById('demo-face').style.display = 'block';
        document.getElementById('demo-glasses').style.display = 'block';
    }, 1000);
});

// ==================== 虚拟试戴（MediaPipe 关键点 + 居中降级） ====================

// FaceMesh 实例（懒加载，全局复用）
let _faceMesh = null;
let _faceMeshReady = null;

/**
 * 加载图片为 Promise
 */
function loadImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('图片加载失败: ' + src));
        img.src = src;
    });
}

/**
 * 获取 FaceMesh 实例（CDN 加载失败时 reject，由调用方降级处理）
 */
function getFaceMesh() {
    if (_faceMeshReady) return _faceMeshReady;
    if (typeof FaceMesh === 'undefined') {
        return Promise.reject(new Error('MediaPipe FaceMesh 未加载'));
    }
    _faceMeshReady = new Promise((resolve, reject) => {
        try {
            _faceMesh = new FaceMesh({
                locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`
            });
            _faceMesh.setOptions({
                maxNumFaces: 1,
                refineLandmarks: false,
                minDetectionConfidence: 0.5
            });
            // 单例回调转发：每次 send 前登记一次性回调
            _faceMesh._pendingCallback = null;
            _faceMesh.onResults((results) => {
                const cb = _faceMesh._pendingCallback;
                _faceMesh._pendingCallback = null;
                if (cb) cb(results);
            });
            resolve(_faceMesh);
        } catch (e) {
            reject(e);
        }
    });
    return _faceMeshReady;
}

/**
 * 检测人脸 468 关键点，返回归一化坐标数组；失败/超时 reject
 */
async function detectFaceLandmarks(imageEl) {
    const faceMesh = await getFaceMesh();
    return new Promise((resolve, reject) => {
        // 15 秒超时保护，避免模型加载卡死
        const timer = setTimeout(() => {
            faceMesh._pendingCallback = null;
            reject(new Error('关键点检测超时'));
        }, 15000);

        faceMesh._pendingCallback = (results) => {
            clearTimeout(timer);
            if (results.multiFaceLandmarks && results.multiFaceLandmarks.length > 0) {
                resolve(results.multiFaceLandmarks[0]);
            } else {
                reject(new Error('未检测到人脸'));
            }
        };
        faceMesh.send({ image: imageEl }).catch((e) => {
            clearTimeout(timer);
            reject(e);
        });
    });
}

/**
 * 按关键点绘制眼镜：
 * - 左眼中心 33 号点、右眼中心 263 号点
 * - 眼镜宽度 = 两眼距 × 2.4，中心 = 两眼连线中点，旋转角 = 连线与水平夹角
 */
function drawGlassesByLandmarks(ctx, glassImg, landmarks, w, h) {
    const left = landmarks[33];
    const right = landmarks[263];
    const lx = left.x * w, ly = left.y * h;
    const rx = right.x * w, ry = right.y * h;

    const cx = (lx + rx) / 2;
    const cy = (ly + ry) / 2;
    const eyeDist = Math.hypot(rx - lx, ry - ly);
    const glassWidth = eyeDist * 2.4;
    const glassHeight = glassImg.height * (glassWidth / glassImg.width);
    const angle = Math.atan2(ry - ly, rx - lx);

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.drawImage(glassImg, -glassWidth / 2, -glassHeight / 2, glassWidth, glassHeight);
    ctx.restore();
}

/**
 * 降级方案：居中叠加（旧逻辑）
 */
function drawGlassesCentered(ctx, glassImg, w, h) {
    const glassWidth = w * 0.6;
    const glassHeight = glassImg.height * (glassWidth / glassImg.width);
    const glassX = (w - glassWidth) / 2;
    const glassY = h * 0.35;
    ctx.drawImage(glassImg, glassX, glassY, glassWidth, glassHeight);
}

/**
 * 虚拟试戴主入口：canvas 自适应容器宽度，优先关键点对齐，失败则居中降级
 */
async function showVirtualTryOn(faceUrl, glassUrl) {
    const canvas = document.getElementById('face-canvas');
    const ctx = canvas.getContext('2d');

    let faceImg;
    try {
        faceImg = await loadImage(faceUrl);
    } catch (e) {
        console.warn(e.message);
        return;
    }

    // canvas 自适应容器宽度，按比例缩放
    const containerWidth = canvas.parentElement.clientWidth || 600;
    canvas.width = containerWidth;
    canvas.height = Math.round(containerWidth * faceImg.naturalHeight / faceImg.naturalWidth);
    ctx.drawImage(faceImg, 0, 0, canvas.width, canvas.height);
    canvas.style.display = 'block';

    let glassImg;
    try {
        glassImg = await loadImage(resolveImageUrl(glassUrl));
    } catch (e) {
        console.warn(e.message);
        showToast('眼镜图片加载失败，请换一款试试', 'warning');
        return;
    }

    // 尝试 MediaPipe 关键点对齐；任何失败均静默降级为居中叠加
    try {
        const landmarks = await detectFaceLandmarks(faceImg);
        drawGlassesByLandmarks(ctx, glassImg, landmarks, canvas.width, canvas.height);
    } catch (e) {
        console.warn('关键点检测不可用，降级为居中叠加：', e.message);
        drawGlassesCentered(ctx, glassImg, canvas.width, canvas.height);
    }
}

// ==================== AI 推荐列表 ====================
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

        const priceRow = document.createElement('div');
        priceRow.className = 'd-flex justify-content-between align-items-center';

        const price = document.createElement('span');
        price.className = 'h5 text-primary mb-0';
        price.textContent = '¥' + glass.price;
        priceRow.appendChild(price);

        const btnGroup = document.createElement('div');
        btnGroup.className = 'd-flex gap-2';

        const tryBtn = document.createElement('button');
        tryBtn.className = 'btn btn-sm btn-outline-primary';
        tryBtn.textContent = '立即试戴';
        tryBtn.addEventListener('click', function () {
            const preview = document.getElementById('face-preview');
            if (preview.style.display === 'block' && preview.src) {
                showVirtualTryOn(preview.src, glass.image_url);
            } else {
                showToast('请先上传照片再试戴', 'info');
            }
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

/**
 * 拉取商城列表并渲染
 */
async function loadShopGlasses() {
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
        const result = await apiRequest(API_BASE + '/api/glasses/list?' + params.toString());
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

        const priceRow = document.createElement('div');
        priceRow.className = 'd-flex justify-content-between align-items-center';

        const price = document.createElement('span');
        price.className = 'h5 text-primary mb-0';
        price.textContent = '¥' + glass.price;
        priceRow.appendChild(price);

        const btnGroup = document.createElement('div');
        btnGroup.className = 'd-flex gap-2';

        // 详情链接（跳 detail.html）
        const detailLink = document.createElement('a');
        detailLink.className = 'btn btn-sm btn-outline-primary';
        detailLink.textContent = '详情';
        detailLink.href = 'detail.html?glasses_id=' + encodeURIComponent(glass.glasses_id);
        btnGroup.appendChild(detailLink);

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
