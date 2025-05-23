# Copyright (c) 2021 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Adapted to tecorigin hardware

from .arcmargin import ArcMargin
from .cosmargin import CosMargin
from .circlemargin import CircleMargin
from .fc import FC
from .vehicle_neck import VehicleNeck
from paddle.nn import Tanh
from .bnneck import BNNeck
from .adamargin import AdaMargin

__all__ = ['build_gear']


def build_gear(config):
    support_dict = [
        'ArcMargin', 'CosMargin', 'CircleMargin', 'FC', 'VehicleNeck', 'Tanh',
        'BNNeck', 'AdaMargin'
    ]
    module_name = config.pop('name')
    assert module_name in support_dict, Exception(
        'head only support {}'.format(support_dict))
    module_class = eval(module_name)(**config)
    return module_class
