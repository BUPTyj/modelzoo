# Wave-MLP

## 1.模型概述

Wave-MLP是一种基于多层感知机（MLP）架构的视觉模型，由研究者们在2021年提出，旨在探索MLP在计算机视觉任务中的潜力。与传统的卷积神经网络（CNN）和基于Transformer的模型（如ViT）不同，Wave-MLP完全依赖于多层感知机结构，通过创新的Wavelet变换和空间通道混合机制来捕捉图像的全局和局部特征，从而实现高效的视觉表征学习。 

## 2.快速开始

使用本模型执行训练的主要流程如下：

1. 基础环境安装：介绍训练前需要完成的基础环境检查和安装。
2. 获取数据集：介绍如何获取训练所需的数据集。
3. 启动训练：介绍如何运行训练。

### 2.1 基础环境安装

1. 虚拟环境启动：

    ```bash
    cd <ModelZoo_path>/PyTorch/contrib/Classification/Wave-MLP
    
    conda activate torch_env
    
    # 执行以下命令验证环境是否正确，正确则会打印版本信息
    python -c 'import torch_sdaa'
    ```

2. 安装python依赖：

    ```bash
    pip install -r requirements.txt
    ```

### 2.2 准备数据集

Wave-MLP运行在ImageNet数据集上，数据集配置可以参考[https://blog.csdn.net/xzxg001/article/details/142465729](https://gitee.com/link?target=https%3A%2F%2Fblog.csdn.net%2Fxzxg001%2Farticle%2Fdetails%2F142465729) 

### 2.3 启动训练

该模型支持单机单核组、单机单卡 

**单机单核组**

```
python train.py --dataset_path /data/datasets/imagenet --batch_size 64 --epochs 20 --distributed False --lr 0.01 --autocast True
```

**单机单卡**

```
torchrun --nproc_per_node=4 train.py --dataset_path /data/datasets/imagenet --batch_size 64 --epochs 20 --distributed True --lr 0.01 --autocast True
```

### 2.4 训练结果

| 加速卡数量 |   模型   | 混合精度 | Batch Size | Iteration | train_loss | AccTop1 |
| :--------: | :------: | :------: | :--------: | :-------: | :--------: | :-----: |
|     1      | Wave-MLP |   amp    |     64     |    12     |     /      |    /    |

**情况说明：**

该模型训练速度慢，在2h训练时间内，一个epoch中只能训练12个iteration。

