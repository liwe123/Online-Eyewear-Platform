// 测试后端连接
// 临时修改请求，使用有效ID测试
axios.get("http://localhost:5000/api/glasses/detail?glasses_id=valid_id_123")
  .then(response => {
    console.log("后端连接成功：", response.data);
  })
  .catch(error => {
    console.error("后端连接失败：", error);
  });
// 1. 图片预览功能
const faceImageInput = document.getElementById("faceImage");
const imagePreview = document.getElementById("imagePreview");
const previewImg = imagePreview.querySelector("img");

faceImageInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (readerEvent) => {
            previewImg.src = readerEvent.target.result;
            imagePreview.style.display = "block";
        };
        reader.readAsDataURL(file);
    } else {
        imagePreview.style.display = "none";
    }
});

// 2. 表单提交逻辑
const userForm = document.getElementById("userForm");
const submitBtn = document.getElementById("submitBtn");
const loadingSpinner = document.getElementById("loadingSpinner");
const resultCard = document.getElementById("resultCard");
const faceShapeText = document.getElementById("faceShapeText");
const recommendationList = document.getElementById("recommendationList");

userForm.addEventListener("submit", (e) => {
    e.preventDefault(); // 阻止默认提交
    
    // 显示加载状态，隐藏按钮
    submitBtn.classList.add("d-none");
    loadingSpinner.classList.remove("d-none");
    
    // 构建FormData（含图片和表单数据）
    const formData = new FormData(userForm);
    
    // 调用后端接口
    axios.post("http://localhost:5000/api/user/submit", formData, {
        headers: { "Content-Type": "multipart/form-data" }
    })
    .then(response => {
        const data = response.data.data;
        // 显示脸型
        faceShapeText.textContent = `${data.face_shape}脸`;
        // 清空之前的推荐结果
        recommendationList.innerHTML = "";
        // 动态插入推荐结果
        data.recommendation.forEach(glasses => {
            const col = document.createElement("div");
            col.className = "col-md-4 mb-3";
            col.innerHTML = `
                <div class="card h-100">
                    <img src="${glasses.image_url}" class="card-img-top" alt="眼镜图片">
                    <div class="card-body">
                        <h5 class="card-title">${glasses.frame_shape}镜框</h5>
                        <p class="card-text">材质：${glasses.frame_material}</p>
                        <p class="card-text">折射率：${glasses.lens_refractive_index}</p>
                        <p class="card-text text-danger fw-bold">?${glasses.price}</p>
                        <a href="detail.html?glasses_id=${glasses.glasses_id}" class="btn btn-primary w-100">查看详情</a>
                    </div>
                </div>
            `;
            recommendationList.appendChild(col);
        });
        // 显示结果区域
        resultCard.classList.remove("d-none");
    })
    .catch(error => {
        alert("提交失败：" + (error.response?.data?.msg || "服务器错误"));
    })
    .finally(() => {
        // 恢复按钮，隐藏加载状态
        submitBtn.classList.remove("d-none");
        loadingSpinner.classList.add("d-none");
    });
});