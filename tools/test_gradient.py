import torch

# 极简模型：单线性层
model = torch.nn.Linear(10, 4)
# 确保参数可训练
for param in model.parameters():
    print(f"参数是否可训练: {param.requires_grad}")  # 应输出True

# 随机输入和标签
x = torch.randn(2, 10)  # 2个样本，10维特征
y = torch.tensor([0, 1], dtype=torch.long)  # 标签

# 前向传播
output = model(x)
loss = torch.nn.functional.cross_entropy(output, y)

# 反向传播（核心测试）
loss.backward()

# 检查梯度是否存在
for param in model.parameters():
    print(f"梯度是否存在: {param.grad is not None}")  # 应输出True

print("梯度测试成功！" if all(param.grad is not None for param in model.parameters()) else "梯度测试失败！")