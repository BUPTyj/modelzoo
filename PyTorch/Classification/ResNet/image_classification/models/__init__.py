# Copyright (c) 2019, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the BSD 3-Clause License  (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://opensource.org/licenses/BSD-3-Clause
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Adapted to tecorigin hardware

from .entrypoints import nvidia_convnets_processing_utils, nvidia_efficientnet
from .resnet import resnet50, resnext101_32x4d, se_resnext101_32x4d, resnet50_v10, resnet18, resnet101
try:
    from .resnet import fused_resnet50
except:
    print('the torch_sdaa not support models,please use the newest ')

