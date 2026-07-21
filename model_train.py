# -*- coding: utf-8 -*-
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import cv2
from PIL import Image
import os
import joblib
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from facenet_pytorch import MTCNN

from model_utils import FaceShapeCNN

# -------------------------- 1. 初始化配置与目录 --------------------------
os.makedirs("./model", exist_ok=True)  # 模型保存目录
os.makedirs("./data/face", exist_ok=True)  # 人脸数据目录

# 定义脸型类别（方形、圆形、鹅蛋脸、长方形）
frame_shape_list = ["fangxing", "yuanxing", "edanlian", "changfangxing"]
label_encoder = LabelEncoder()
label_encoder.fit(frame_shape_list)
# 保存标签编码器
joblib.dump(label_encoder, "./model/label_encoder.pkl")
print("标签编码器已保存")

# -------------------------- 2. 数据集定义与加载 --------------------------
class FaceDataset(Dataset):
    def __init__(self, image_paths, labels, mtcnn):
        self.image_paths = image_paths  # 图片路径列表
        self.labels = labels  # 标签列表
        self.mtcnn = mtcnn  # 人脸检测器

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        # 读取图片并转换为RGB格式
        img_path = self.image_paths[idx]
        img = Image.open(img_path).convert("RGB")
        
        # 使用MTCNN检测人脸并裁剪（如未检测到则使用原图缩放）
        face = self.mtcnn(img)
        if face is None:
            # 未检测到人脸时，缩放原图为160x160并归一化到 [-1, 1]
            img_resized = cv2.resize(np.array(img), (160, 160))
            face = torch.tensor(img_resized, dtype=torch.float32).permute(2, 0, 1)
            face = (face / 127.5) - 1.0  # 转换为[-1, 1]范围
        else:
            # 检测到人脸时，MTCNN输出已经在 [-1, 1] 范围，直接使用
            face = face.to(dtype=torch.float32)
        
        # 转换标签为张量
        label = torch.tensor(self.labels[idx], dtype=torch.long)
        return face, label

# 加载数据集（如无数据则生成随机示例图片）
image_paths, labels = [], []
for label_idx, shape in enumerate(frame_shape_list):
    shape_dir = f"./data/face/{shape}"
    os.makedirs(shape_dir, exist_ok=True)
    
    # 如目录为空，生成10张随机示例图片
    if len(os.listdir(shape_dir)) == 0:
        for i in range(10):
            # 生成随机像素的160x160图片
            random_img = np.random.randint(0, 255, (160, 160, 3), dtype=np.uint8)
            cv2.imwrite(f"{shape_dir}/demo_{i}.jpg", random_img)
    
    # 收集图片路径和对应标签
    for img_name in os.listdir(shape_dir):
        if img_name.endswith((".jpg", ".png")):
            image_paths.append(f"{shape_dir}/{img_name}")
            labels.append(label_idx)

# 分割训练集和测试集（8:2比例）
train_paths, test_paths, train_labels, test_labels = train_test_split(
    image_paths, labels, test_size=0.2, random_state=42
)

# 初始化MTCNN人脸检测器（输出160x160大小的人脸）
mtcnn = MTCNN(image_size=160, margin=0, device="cpu")

# 创建数据加载器
train_dataset = FaceDataset(train_paths, train_labels, mtcnn)
test_dataset = FaceDataset(test_paths, test_labels, mtcnn)
train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True)
test_loader = DataLoader(test_dataset, batch_size=4)

model = FaceShapeCNN(num_classes=4)
for param in model.parameters():
    param.requires_grad = True  # 所有参数可训练

# 定义损失函数和优化器
criterion = nn.CrossEntropyLoss()  # 交叉熵损失（适用于分类）
optimizer = optim.Adam(model.parameters(), lr=1e-3)  # Adam优化器，学习率0.001

# 设备配置（使用CPU）
device = torch.device("cpu")
model.to(device)

# -------------------------- 4. 模型训练 --------------------------
print("开始训练...")
for epoch in range(3):  # 训练3轮
    model.train()  # 切换到训练模式
    train_loss = 0.0
    
    for batch_idx, (faces, labels) in enumerate(train_loader):
        # 将数据转移到设备（CPU）
        faces, labels = faces.to(device), labels.to(device)
        
        # 正向传播：计算模型输出
        outputs = model(faces)
        # 计算损失
        loss = criterion(outputs, labels)
        
        # 反向传播与参数更新
        optimizer.zero_grad()  # 清空梯度
        loss.backward()        # 反向传播计算梯度
        optimizer.step()       # 更新参数
        
        # 累计损失
        train_loss += loss.item() * faces.size(0)
        print(f"第{epoch+1}轮，第{batch_idx+1}批，损失: {loss.item():.4f}")
    
    # 计算平均损失
    avg_loss = train_loss / len(train_loader.dataset)
    print(f"第{epoch+1}/3轮，平均训练损失: {avg_loss:.4f}\n")

# 保存模型权重
torch.save(model.state_dict(), "./model/face_shape_model.pth")
print("训练完成，模型已保存至 ./model/face_shape_model.pth")

# -------------------------- 5. 训练推荐模型 --------------------------
from sklearn.tree import DecisionTreeClassifier
import pandas as pd

# 读取真实的眼部数据
try:
    eye_df = pd.read_csv("./data/user_eye_data.csv")
    print("成功加载真实眼部数据进行推荐模型训练")
    
    # 提取特征
    X_recommend = eye_df[["pupil_distance", "corneal_curvature", "myopia_degree"]].values
    
    # 构建合理的伪标签（0: fangxing, 1: yuanxing, 2: edanlian, 3: changfangxing）
    # 简单的业务规则：
    # - 高度近视 (myopia_degree < -6.0) 推荐圆框(1)或鹅蛋脸框(2)以减小边缘厚度
    # - 瞳距较大 (pupil_distance > 64) 推荐方框(0)或长方框(3)
    # - 其他情况随机分配或结合曲率
    y_recommend = []
    for index, row in eye_df.iterrows():
        pd_val = row["pupil_distance"]
        myopia = row["myopia_degree"]
        
        if myopia < -6.0:
            y_recommend.append(1 if pd_val < 60 else 2)
        elif pd_val > 64:
            y_recommend.append(0 if myopia > -3.0 else 3)
        else:
            y_recommend.append(np.random.randint(0, 4))
            
    y_recommend = np.array(y_recommend)

except Exception as e:
    print(f"读取 user_eye_data.csv 失败，使用备用随机数据: {e}")
    # 备用：生成模拟的推荐训练数据，但使用更合理的数值范围
    X_recommend = np.column_stack((
        np.random.uniform(50, 75, 100),       # 瞳距: 50-75
        np.random.uniform(39, 47, 100),       # 曲率: 39-47
        np.random.uniform(-10, 0, 100)        # 近视度数: -10~0
    ))
    y_recommend = np.random.randint(0, 4, 100)

# 训练决策树推荐模型
recommend_model = DecisionTreeClassifier(max_depth=5, random_state=42)
recommend_model.fit(X_recommend, y_recommend)

# 保存推荐模型
joblib.dump(recommend_model, "./model/recommend_model.pkl")
print("推荐模型已保存：./model/recommend_model.pkl")