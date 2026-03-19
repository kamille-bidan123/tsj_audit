// 记事本前端逻辑
const API_URL = "http://localhost:8081";
let currentUser = null;

// 加载用户
window.addEventListener('load', () => {
    const userId = localStorage.getItem('user_id');
    if (userId) {
        currentUser = { id: parseInt(userId), username: localStorage.getItem('username') || 'Unknown' };
        showNotes();
    }
});

// 显示登录页面
function showLogin() {
    document.getElementById('app').innerHTML = `
        <div class="login-card p-4">
            <h2 class="text-center mb-4">记事本应用</h2>
            <form id="loginForm">
                <div class="mb-3"><label>用户名</label><input type="text" class="form-control" id="username"></div>
                <div class="mb-3"><label>密码</label><input type="password" class="form-control" id="password"></div>
                <button type="submit" class="btn btn-primary w-100">登录</button>
            </form>
            <p class="text-center mt-2"><a href="#" onclick="showRegister()">注册</a> | <a href="#" onclick="showForgotPassword()">忘记密码</a></p>
        </div>`;
    document.getElementById('loginForm').addEventListener('submit', handleLogin);
}

// 处理登录
async function handleLogin(e) {
    e.preventDefault();
    const res = await fetch(API_URL + '/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: document.getElementById('username').value, password: document.getElementById('password').value })
    });
    const data = await res.json();
    if (data.status === 200) {
        localStorage.setItem('user_id', data.data.user_id);
        currentUser = { id: data.data.user_id, username: data.data.username };
        alert('登录成功！');
        showNotes();
    } else { alert('登录失败：' + data.message); }
}

// 显示注册
function showRegister() {
    const modal = new bootstrap.Modal(new Element('div'));
    alert("注册功能需要完整页面支持");
}

// 显示忘记密码
function showForgotPassword() {
    alert("忘记密码功能需要完整页面支持");
}

// 显示笔记列表
async function showNotes() {
    const res = await fetch(API_URL + '/notes?user_id=' + currentUser.id);
    const data = await res.json();
    document.body.innerHTML = `
        <div class="container mt-4">
            <h2>${currentUser.username} 的笔记</h2>
            <button class="btn btn-primary mb-3" onclick="showNewNote()">+ 新建笔记</button>
            <button class="btn btn-secondary mb-3" onclick="showFtpConfig()">FTP 设置</button>
            <button class="btn btn-danger mb-3" onclick="logout()">退出登录</button>
            <div id="notesList"></div>
        </div>`;
    renderNotes(data.data);
}

// 渲染笔记
function renderNotes(notes) {
    const list = document.getElementById('notesList');
    if (!notes || notes.length === 0) {
        list.innerHTML = '<p class="text-muted">暂无笔记</p>';
        return;
    }
    list.innerHTML = notes.map(n => `
        <div class="card mb-2">
            <div class="card-body">
                <h5 class="card-title">${n.title}</h5>
                <p class="card-text">${n.content.substring(0, 100)}...</p>
                <button class="btn btn-sm btn-outline-primary" onclick="editNote(${n.id})">编辑</button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteNote(${n.id})">删除</button>
            </div>
        </div>`).join('');
}

// 新建笔记
function showNewNote() {
    document.body.innerHTML += '<div class="modal"><div class="modal-dialog"><div class="modal-content"><div class="modal-header"><h5>新建笔记</h5></div><div class="modal-body"><input class="form-control" id="noteTitle" placeholder="标题"><textarea class="form-control" id="noteContent" rows="8" placeholder="内容"></textarea></div><div class="modal-footer"><button class="btn btn-primary" onclick="saveNewNote()">保存</button></div></div></div></div>';
}

async function saveNewNote() {
    const res = await fetch(API_URL + '/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: currentUser.id, title: document.getElementById('noteTitle').value, content: document.getElementById('noteContent').value })
    });
    const data = await res.json();
    if (data.status === 201) { alert('保存成功！'); showNotes(); }
}

// 编辑笔记
function editNote(noteId) {
    alert('编辑笔记 ' + noteId);
}

// 删除笔记
async function deleteNote(noteId) {
    if (!confirm('确定要删除吗？')) return;
    const res = await fetch(API_URL + '/notes/delete?note_id=' + noteId, { method: 'POST' });
    const data = await res.json();
    if (data.status === 200) { alert('删除成功！'); showNotes(); }
}

// 退出登录
function logout() {
    localStorage.removeItem('user_id');
    localStorage.removeItem('username');
    currentUser = null;
    showLogin();
}

// FTP 设置
function showFtpConfig() {
    alert('FTP 设置功能需要完整页面支持');
}
