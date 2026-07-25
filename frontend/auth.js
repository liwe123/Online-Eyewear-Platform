// 丹智慧眼 - 登录/注册模块
// 依赖 common.js（API_BASE / apiRequest / showToast）
// 页面需提供 id="auth-btn" 的导航按钮

const AUTH_KEY = 'dz_auth';

// 读取登录状态
function getAuth() {
    try {
        return JSON.parse(localStorage.getItem(AUTH_KEY));
    } catch (e) {
        return null;
    }
}

// 退出登录
function logout() {
    localStorage.removeItem(AUTH_KEY);
    updateAuthButton();
    showToast('已退出登录', 'info');
}

// 根据登录状态刷新导航按钮文案
function updateAuthButton() {
    const btn = document.getElementById('auth-btn');
    if (!btn) return;
    const auth = getAuth();
    if (auth && auth.username) {
        // 用户名可含任意字符，textContent 防自我型 XSS
        btn.innerHTML = '<i class="fas fa-user-check me-1"></i> ';
        btn.appendChild(document.createTextNode('你好, ' + auth.username));
    } else {
        btn.innerHTML = '<i class="fas fa-user me-1"></i> 登录';
    }
}

// 动态注入登录/注册 Modal DOM
function injectAuthModal() {
    if (document.getElementById('authModal')) return;
    const wrapper = document.createElement('div');
    wrapper.innerHTML = `
    <div class="modal fade" id="authModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered" style="max-width: 420px;">
            <div class="modal-content">
                <div class="modal-header border-0 pb-0">
                    <ul class="nav nav-tabs border-0" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" id="login-tab" data-bs-toggle="tab"
                                    data-bs-target="#login-pane" type="button" role="tab">登录</button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="register-tab" data-bs-toggle="tab"
                                    data-bs-target="#register-pane" type="button" role="tab">注册</button>
                        </li>
                    </ul>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
                </div>
                <div class="modal-body pt-3">
                    <div class="tab-content">
                        <!-- 登录 -->
                        <div class="tab-pane fade show active" id="login-pane" role="tabpanel">
                            <form id="login-form">
                                <div class="mb-3">
                                    <label class="form-label">用户名</label>
                                    <input type="text" class="form-control" id="login-username"
                                           placeholder="请输入用户名" autocomplete="username">
                                </div>
                                <div class="mb-4">
                                    <label class="form-label">密码</label>
                                    <input type="password" class="form-control" id="login-password"
                                           placeholder="请输入密码" autocomplete="current-password">
                                </div>
                                <button type="submit" class="btn btn-primary-custom w-100" id="login-submit">
                                    登 录
                                </button>
                            </form>
                        </div>
                        <!-- 注册 -->
                        <div class="tab-pane fade" id="register-pane" role="tabpanel">
                            <form id="register-form">
                                <div class="mb-3">
                                    <label class="form-label">用户名</label>
                                    <input type="text" class="form-control" id="register-username"
                                           placeholder="请输入用户名" autocomplete="username">
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">密码</label>
                                    <input type="password" class="form-control" id="register-password"
                                           placeholder="请输入密码" autocomplete="new-password">
                                </div>
                                <div class="mb-4">
                                    <label class="form-label">确认密码</label>
                                    <input type="password" class="form-control" id="register-password2"
                                           placeholder="请再次输入密码" autocomplete="new-password">
                                </div>
                                <button type="submit" class="btn btn-primary-custom w-100" id="register-submit">
                                    注 册
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>`;
    document.body.appendChild(wrapper.firstElementChild);
}

// 提交登录
async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    if (!username || !password) {
        showToast('请输入用户名和密码', 'warning');
        return;
    }

    const btn = document.getElementById('login-submit');
    btn.disabled = true;
    btn.textContent = '登录中...';
    try {
        const result = await apiRequest(API_BASE + '/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        if (result.code === 200) {
            localStorage.setItem(AUTH_KEY, JSON.stringify({
                token: result.data.token,
                username: result.data.username || username
            }));
            updateAuthButton();
            bootstrap.Modal.getOrCreateInstance(document.getElementById('authModal')).hide();
            showToast('登录成功，欢迎回来！', 'success');
        } else {
            showToast(result.msg || '登录失败', 'danger');
        }
    } catch (error) {
        showToast(error.message || '网络错误，请稍后重试', 'danger');
    } finally {
        btn.disabled = false;
        btn.textContent = '登 录';
    }
}

// 提交注册
async function handleRegister(e) {
    e.preventDefault();
    const username = document.getElementById('register-username').value.trim();
    const password = document.getElementById('register-password').value;
    const password2 = document.getElementById('register-password2').value;

    if (!username || !password) {
        showToast('请输入用户名和密码', 'warning');
        return;
    }
    if (password !== password2) {
        showToast('两次输入的密码不一致', 'warning');
        return;
    }

    const btn = document.getElementById('register-submit');
    btn.disabled = true;
    btn.textContent = '注册中...';
    try {
        const result = await apiRequest(API_BASE + '/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        if (result.code === 200) {
            showToast('注册成功，请登录', 'success');
            // 注册成功后切到登录 tab 并预填用户名
            document.getElementById('login-username').value = username;
            bootstrap.Tab.getOrCreateInstance(document.getElementById('login-tab')).show();
        } else {
            showToast(result.msg || '注册失败', 'danger');
        }
    } catch (error) {
        showToast(error.message || '网络错误，请稍后重试', 'danger');
    } finally {
        btn.disabled = false;
        btn.textContent = '注 册';
    }
}

// 初始化：注入 Modal、绑定按钮与表单、刷新按钮文案
document.addEventListener('DOMContentLoaded', function () {
    injectAuthModal();
    updateAuthButton();

    const authBtn = document.getElementById('auth-btn');
    if (authBtn) {
        authBtn.addEventListener('click', function () {
            if (getAuth()) {
                // 已登录 → 直接退出并提示
                logout();
            } else {
                bootstrap.Modal.getOrCreateInstance(document.getElementById('authModal')).show();
            }
        });
    }

    document.getElementById('login-form').addEventListener('submit', handleLogin);
    document.getElementById('register-form').addEventListener('submit', handleRegister);
});
