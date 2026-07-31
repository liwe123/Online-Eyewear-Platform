# ===========================================================================
# 已废弃（仅供历史参考，请勿在生产中调用）
# ---------------------------------------------------------------------------
# 本模块是早期基于随机噪声训练的 CNN 脸型识别实现，现已不再使用：
#   脸型识别已更换为 MediaPipe FaceMesh 几何方案（见 face_geometry.py），
#   仅当 mediapipe 不可用时才降级到检测框启发式，CNN 已完全退役。
# model_api.py 已不再加载 model/ 下的 .pth/.pkl 假模型文件。
#
# 保留此文件仅用于参考，任何新代码都不得依赖 FaceShapeCNN。
# ===========================================================================

import torch.nn as nn


class FaceShapeCNN(nn.Module):
    def __init__(self, num_classes=4):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 16, kernel_size=3, stride=1, padding=1)
        self.conv2 = nn.Conv2d(16, 32, kernel_size=3, stride=1, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.fc = nn.Linear(32 * 40 * 40, num_classes)

    def forward(self, x):
        x = self.pool(nn.functional.relu(self.conv1(x)))
        x = self.pool(nn.functional.relu(self.conv2(x)))
        x = x.view(x.size(0), -1)
        x = self.fc(x)
        return x
