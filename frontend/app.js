// 丹智慧眼 - 前端主逻辑

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
 * 为图片设置错误回退
 */
function setImgFallback(img, fallbackSrc) {
    img.onerror = function () {
        if (this.src !== fallbackSrc) {
            this.src = fallbackSrc || IMG_PLACEHOLDER;
        }
        this.onerror = null; // 防止死循环
    };
}

// ==================== 页面初始化 ====================
document.addEventListener('DOMContentLoaded', function () {
    loadRecommendedGlasses([]);

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

        const analyzeBtn = this;
        analyzeBtn.disabled = true;
        analyzeBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>分析中...';

        const leftEye = parseFloat(document.getElementById('left-eye').value) || 0;
        const rightEye = parseFloat(document.getElementById('right-eye').value) || 0;
        const pupilDistance = parseFloat(document.getElementById('pupil-distance').value) || 0;
        const myopiaDegree = (leftEye + rightEye) / 2;

        const formData = new FormData();
        formData.append('image', fileInput.files[0]);
        formData.append('pupil_distance', pupilDistance);
        formData.append('corneal_curvature', 43.0);
        formData.append('myopia_degree', myopiaDegree);

        try {
            const result = await apiRequest(API_BASE + '/api/user/submit', {
                method: 'POST',
                body: formData
            });

            if (result.code === 200) {
                document.getElementById('analysis-result').textContent =
                    '分析完成！检测到您的脸型为' + result.data.face_shape + '，为您推荐以下眼镜。';
                document.getElementById('match-progress').style.width = '92%';
                loadRecommendedGlasses(result.data.recommendation);
                showVirtualTryOn(facePreview.src, result.data.recommendation[0].image_url);
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

    // 演示虚拟试戴
    setTimeout(function () {
        document.getElementById('demo-face').style.display = 'block';
        document.getElementById('demo-glasses').style.display = 'block';
    }, 1000);
});

// ==================== 虚拟试戴 ====================
function showVirtualTryOn(faceUrl, glassUrl) {
    const canvas = document.getElementById('face-canvas');
    const ctx = canvas.getContext('2d');
    const faceImg = new Image();
    const glassImg = new Image();

    faceImg.crossOrigin = 'anonymous';
    glassImg.crossOrigin = 'anonymous';

    faceImg.onload = function () {
        canvas.width = faceImg.width;
        canvas.height = faceImg.height;
        ctx.drawImage(faceImg, 0, 0);

        glassImg.onload = function () {
            const glassWidth = faceImg.width * 0.6;
            const glassHeight = glassImg.height * (glassWidth / glassImg.width);
            const glassX = (faceImg.width - glassWidth) / 2;
            const glassY = faceImg.height * 0.35;
            ctx.drawImage(glassImg, glassX, glassY, glassWidth, glassHeight);
        };
        glassImg.onerror = function () {
            console.warn('眼镜图片加载失败:', glassUrl);
            showToast('眼镜图片加载失败，请换一款试试', 'warning');
        };
        glassImg.src = glassUrl;
    };
    faceImg.onerror = function () {
        console.warn('人脸图片加载失败:', faceUrl);
    };
    faceImg.src = faceUrl;
    canvas.style.display = 'block';
}

// ==================== 加载推荐列表 ====================
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
        img.src = glass.image_url;
        img.className = 'card-img-top glass-image';
        img.alt = glass.frame_shape + '眼镜';
        img.loading = 'lazy';
        setImgFallback(img);
        card.appendChild(img);

        const cardBody = document.createElement('div');
        cardBody.className = 'card-body';

        const title = document.createElement('h5');
        title.className = 'card-title';
        title.textContent = glass.frame_shape + '眼镜';
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

        const tryBtn = document.createElement('button');
        tryBtn.className = 'btn btn-sm btn-outline-primary';
        tryBtn.textContent = '立即试戴';
        tryBtn.addEventListener('click', function () {
            const preview = document.getElementById('face-preview');
            if (preview.style.display === 'block' && preview.src) {
                showVirtualTryOn(preview.src, glass.image_url);
            }
        });
        priceRow.appendChild(tryBtn);

        cardBody.appendChild(priceRow);
        card.appendChild(cardBody);
        col.appendChild(card);
        container.appendChild(col);
    });
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
var style = document.createElement('style');
style.textContent =
    '@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}';
document.head.appendChild(style);
