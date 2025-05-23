# 提交PR

## 1. 概述

在完成模型开发及贡献模型所需文件后，您可以通过PR（Pull Request）将相应内容提交到Tecorigin ModelZoo仓库。

本文介绍提交PR前的检查工作以及如何创建PR信息。


## 2. 检查工作

提交PR前的检查工作主要包含以下几个方面：

- 检查路径规范：检查模型和文件是否已放到规定的目录下。
- （可选）优化代码：检查代码格式或内容是否可以进一步优化。
- 检查贡献文件：检查文件是否完整且符合要求。

### 2.1 检查路径规范

您已按照`<框架名>/contrib/<算法领域>/<模型名称>`格式创建目录，并将模型和相应文件放在该目录下。

- 框架名：当前包括PyTorch或PaddlePaddle。请根据您的模型使用的训练框架进行选择。
- 算法领域：当前有Classification、Detection、Face、GNN、NLP、Recommendation、Reinforcement、Segmentation、Speech，请您从中选择。如果所选模型不在上述列表中，可使用其他算法领域名称，并在[Issues](https://github.com/Tecorigin/modelzoo/issues)中对此进行说明。
- 模型名称：模型的名称。

例如，ResNet模型的PyTorch版本提交的路径为: PyTorch/contrib/Classification/ResNet。

### 2.2 优化代码

提交PR之前，请完整检查代码，确认是否有可以进一步优化的代码（例如：删除无关的代码等），从而让代码变得更优雅。

可以使用[lint](https://www.pylint.org/)等format工具统一代码格式，使代码更加规整。

### 2.3 检查贡献文件

检查贡献所需文件是否完整且符合规范。

- 模型训练代码：
  - 模型的精度和性能至少达到原始模型水平。
  - 模型使用DDP和AMP提升性能。
  - 模型使用TCAP\_DLLogger输出统一日志。

- 训练运行文件：
  - 检查是否存在`run_scripts`文件夹。
  - `run_scripts`目录下至少应当包括`argument.py`文件 和 `run_demo.py`文件。

- Dockerfile文件

- Requirement文件

- Readme文件：检查是否已经包含模型使用的Readme文件，且文件至少包含以下内容说明：    
  - 模型概述
  - Docker环境准备
  - 数据集
    - 如果使用开源数据集或权重，提供开源获取方式和数据处理方法。
    - 如果使用非开源数据集或权重，请提供百度网盘下载链接和数据处理方法。
    - 数据集文件请不要提交代码上传，github单文件最大限制100MB。
  - 启动训练的方法
  - 训练结果: 
    - 如果为完整的训练或微调任务，请提供最终的metric结果。 
    - 如果为短训，请提供loss曲线图和最终的loss结果。


## 3. 提交PR

基于您Fork的个人空间的Tecorgin Modelzoo仓库，新建Pull Requests提交内容。关于如何Fork仓库及提交Pull Request，请查阅github官方使用文档：[Fork+PullRequest 模式](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork)。

提交PR时注意以下事项：

- 分支选择：

  - PR的源分支选择本地Tecorgin Modelzoo开发分支。为便于管理，建议您将分支名称命名为`contrib/<开发者团队名称>/<模型名称>`，例如：`contrib/jiangnan_university_ailab/deeplabv3`。
  - 目标分支选择`tecorigin/modelzoo:main`。

- PR标题：PR标题需要标注开发者团队名称及适配的内容，例如：**江南大学AILAB-在PyTorch框架上支持ResNet50在Imagenet上的训练**。
- PR说明：PR说明应当包含以下内容。
  
   * 当前适配的软件栈版本：打印当前软件栈版本，以截图的方式提供即可。
   * 源码参考：提供源码参考链接和对应的`commit id`或`tag`，如果无参考源码，请说明。
   * 工作目录：代码存放路径。
   * 运行命令：启动模型训练的命令。
   * 结果展示：训练结果展示。结果展示需要包含模型精度结果及脚本运行时间。
     * 如果为完整的训练或微调任务，请提供最终的metric结果。
     * 如果为短训，请提供loss曲线图和最终的loss结果。
   * Readme自测结果：确定Readme已经通过自测，非开发者可以通过Readme运行模型训练。

PR的具体内容，请参考以下示例：[https://github.com/Tecorigin/modelzoo/pull/9](https://github.com/Tecorigin/modelzoo/pull/9)    
