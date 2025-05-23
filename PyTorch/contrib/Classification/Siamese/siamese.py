# BSD 3- Clause License Copyright (c) 2023, Tecorigin Co., Ltd. All rights
# reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software
# without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY,OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)  ARISING IN ANY
# WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY
# OF SUCH DAMAGE.


import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.backends.cudnn as cudnn
from PIL import Image
import os
import torch_sdaa

from nets.siamese import Siamese as siamese
from utils.utils import letterbox_image, preprocess_input, cvtColor, show_config


#---------------------------------------------------#
#   使用自己训练好的模型预测需要修改model_path参数
#---------------------------------------------------#
class Siamese(object):
    _defaults = {
        #-----------------------------------------------------#
        #   使用自己训练好的模型进行预测一定要修改model_path
        #   model_path指向logs文件夹下的权值文件
        #-----------------------------------------------------#
        "model_path"        : 'model_data/Omniglot_vgg.pth',
        #-----------------------------------------------------#
        #   输入图片的大小。
        #-----------------------------------------------------#
        "input_shape"       : [105, 105],
        #--------------------------------------------------------------------#
        #   该变量用于控制是否使用letterbox_image对输入图像进行不失真的resize
        #   否则对图像进行CenterCrop
        #--------------------------------------------------------------------#
        "letterbox_image"   : False,
        #-------------------------------#
        #   是否使用sdaa
        #   没有GPU可以设置成False
        #-------------------------------#
        "sdaa"              : True
    }

    @classmethod
    def get_defaults(cls, n):
        if n in cls._defaults:
            return cls._defaults[n]
        else:
            return "Unrecognized attribute name '" + n + "'"

    #---------------------------------------------------#
    #   初始化Siamese
    #---------------------------------------------------#
    def __init__(self, **kwargs):
        self.__dict__.update(self._defaults)
        for name, value in kwargs.items():
            setattr(self, name, value)
        self.generate()
        
        show_config(**self._defaults)
        
    #---------------------------------------------------#
    #   载入模型
    #---------------------------------------------------#
    def generate(self):
        #---------------------------#
        #   载入模型与权值
        #---------------------------#
        print('Loading weights into state dict...')
        device  = torch.device('sdaa' if torch.sdaa.is_available() else 'cpu')
        model   = siamese(self.input_shape)
        model.load_state_dict(torch.load(self.model_path, map_location=device))
        self.net = model.eval()
        print('{} model loaded.'.format(self.model_path))

        if self.sdaa:
            self.net = torch.nn.DataParallel(self.net)
            cudnn.benchmark = True
            local_rank = int(os.environ.get("LOCAL_RANK", -1)) 
            device = torch.device(f"sdaa:{local_rank}")
            self.net = self.net.to(device)
    
    def letterbox_image(self, image, size):
        image   = image.convert("RGB")
        iw, ih  = image.size
        w, h    = size
        scale   = min(w/iw, h/ih)
        nw      = int(iw*scale)
        nh      = int(ih*scale)

        image       = image.resize((nw,nh), Image.BICUBIC)
        new_image   = Image.new('RGB', size, (128,128,128))
        new_image.paste(image, ((w-nw)//2, (h-nh)//2))
        if self.input_shape[-1]==1:
            new_image = new_image.convert("L")
        return new_image
        
    #---------------------------------------------------#
    #   检测图片
    #---------------------------------------------------#
    def detect_image(self, image_1, image_2):
        #---------------------------------------------------------#
        #   在这里将图像转换成RGB图像，防止灰度图在预测时报错。
        #---------------------------------------------------------#
        image_1 = cvtColor(image_1)
        image_2 = cvtColor(image_2)
        
        #---------------------------------------------------#
        #   对输入图像进行不失真的resize
        #---------------------------------------------------#
        image_1 = letterbox_image(image_1, [self.input_shape[1], self.input_shape[0]], self.letterbox_image)
        image_2 = letterbox_image(image_2, [self.input_shape[1], self.input_shape[0]], self.letterbox_image)
        
        #---------------------------------------------------------#
        #   归一化+添加上batch_size维度
        #---------------------------------------------------------#
        photo_1  = preprocess_input(np.array(image_1, np.float32))
        photo_2  = preprocess_input(np.array(image_2, np.float32))

        with torch.no_grad():
            #---------------------------------------------------#
            #   添加上batch维度，才可以放入网络中预测
            #---------------------------------------------------#
            photo_1 = torch.from_numpy(np.expand_dims(np.transpose(photo_1, (2, 0, 1)), 0)).type(torch.FloatTensor)
            photo_2 = torch.from_numpy(np.expand_dims(np.transpose(photo_2, (2, 0, 1)), 0)).type(torch.FloatTensor)
            
            if self.sdaa:
                local_rank = int(os.environ.get("LOCAL_RANK", -1)) 
                device = torch.device(f"sdaa:{local_rank}")
                photo_1 = photo_1.to(device)
                photo_2 = photo_2.to(device)
                
            #---------------------------------------------------#
            #   获得预测结果，output输出为概率
            #---------------------------------------------------#
            output = self.net([photo_1, photo_2])[0]
            output = torch.nn.Sigmoid()(output)

        plt.subplot(1, 2, 1)
        plt.imshow(np.array(image_1))

        plt.subplot(1, 2, 2)
        plt.imshow(np.array(image_2))
        plt.text(-12, -12, 'Similarity:%.3f' % output, ha='center', va= 'bottom',fontsize=11)
        plt.show()
        return output
