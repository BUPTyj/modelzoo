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
import colorsys
import os
import time

import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageDraw, ImageFont

from nets.frcnn import FasterRCNN
from utils.utils import (cvtColor, get_classes, get_new_img_size, resize_image,
                         preprocess_input, show_config)
from utils.utils_bbox import DecodeBox
import torch_sdaa


class FRCNN(object):
    _defaults = {
        "backbone": "vgg",
        "confidence": 0.5,
        "nms_iou": 0.3,
        'anchors_size': [8, 16, 32],
    }

    @classmethod
    def get_defaults(cls, n):
        if n in cls._defaults:
            return cls._defaults[n]
        else:
            return "Unrecognized attribute name '" + n + "'"

    def __init__(self, **kwargs):
        self.__dict__.update(self._defaults)
        for name, value in kwargs.items():
            setattr(self, name, value)
            self._defaults[name] = value
            # ---------------------------------------------------#
        #   获得种类和先验框的数量
        # ---------------------------------------------------#
        self.class_names, self.num_classes = get_classes(self.classes_path)

        self.std = torch.Tensor([0.1, 0.1, 0.2, 0.2]).repeat(self.num_classes + 1)[None]
        self.bbox_util = DecodeBox(self.std, self.num_classes)

        # ---------------------------------------------------#
        #   画框设置不同的颜色
        # ---------------------------------------------------#
        hsv_tuples = [(x / self.num_classes, 1., 1.) for x in range(self.num_classes)]
        self.colors = list(map(lambda x: colorsys.hsv_to_rgb(*x), hsv_tuples))
        self.colors = list(map(lambda x: (int(x[0] * 255), int(x[1] * 255), int(x[2] * 255)), self.colors))
        self.generate()

        show_config(**self._defaults)

    # ---------------------------------------------------#
    #   载入模型
    # ---------------------------------------------------#
    def generate(self):
        # -------------------------------#
        #   载入模型与权值
        # -------------------------------#
        self.net = FasterRCNN(self.num_classes, "predict", anchor_scales=self.anchors_size, backbone=self.backbone)
        device = 'sdaa'
        checkpoint = torch.load(self.model_path, map_location=device)
        self.net.load_state_dict({k.replace('module.',''):v for k,v in checkpoint.items()})
        self.net = self.net.eval()
        print('{} model, anchors, and classes loaded.'.format(self.model_path))


    def detect_image(self, image, crop=False, count=False):
        # ---------------------------------------------------#
        #   计算输入图片的高和宽
        # ---------------------------------------------------#
        image_shape = np.array(np.shape(image)[0:2])
        # ---------------------------------------------------#
        #   计算resize后的图片的大小，resize后的图片短边为600
        # ---------------------------------------------------#
        input_shape = get_new_img_size(image_shape[0], image_shape[1])
        # ---------------------------------------------------------#
        #   在这里将图像转换成RGB图像，防止灰度图在预测时报错。
        #   代码仅仅支持RGB图像的预测，所有其它类型的图像都会转化成RGB
        # ---------------------------------------------------------#
        image = cvtColor(image)
        # ---------------------------------------------------------#
        #   给原图像进行resize，resize到短边为600的大小上
        # ---------------------------------------------------------#
        image_data = resize_image(image, [input_shape[1], input_shape[0]])
        # ---------------------------------------------------------#
        #   添加上batch_size维度
        # ---------------------------------------------------------#
        image_data = np.expand_dims(np.transpose(preprocess_input(np.array(image_data, dtype='float32')), (2, 0, 1)), 0)

        with torch.no_grad():
            images = torch.from_numpy(image_data)

            # -------------------------------------------------------------#
            #   roi_cls_locs  建议框的调整参数
            #   roi_scores    建议框的种类得分
            #   rois          建议框的坐标
            # -------------------------------------------------------------#
            roi_cls_locs, roi_scores, rois, _ = self.net(images)
            # -------------------------------------------------------------#
            #   利用classifier的预测结果对建议框进行解码，获得预测框
            # -------------------------------------------------------------#
            results = self.bbox_util.forward(roi_cls_locs, roi_scores, rois, image_shape, input_shape,
                                             nms_iou=self.nms_iou, confidence=self.confidence)
            # ---------------------------------------------------------#
            #   如果没有检测出物体，返回原图
            # ---------------------------------------------------------#
            if len(results[0]) <= 0:
                return image

            top_label = np.array(results[0][:, 5], dtype='int32')
            top_conf = results[0][:, 4]
            top_boxes = results[0][:, :4]

        # ---------------------------------------------------------#
        #   设置字体与边框厚度
        # ---------------------------------------------------------#
        font = ImageFont.truetype(font='model_data/simhei.ttf',
                                  size=np.floor(3e-2 * image.size[1] + 0.5).astype('int32'))
        thickness = int(max((image.size[0] + image.size[1]) // np.mean(input_shape), 1))
        # ---------------------------------------------------------#
        #   计数
        # ---------------------------------------------------------#
        if count:
            print("top_label:", top_label)
            classes_nums = np.zeros([self.num_classes])
            for i in range(self.num_classes):
                num = np.sum(top_label == i)
                if num > 0:
                    print(self.class_names[i], " : ", num)
                classes_nums[i] = num
            print("classes_nums:", classes_nums)
        # ---------------------------------------------------------#
        #   是否进行目标的裁剪
        # ---------------------------------------------------------#
        if crop:
            for i, c in list(enumerate(top_label)):
                top, left, bottom, right = top_boxes[i]
                top = max(0, np.floor(top).astype('int32'))
                left = max(0, np.floor(left).astype('int32'))
                bottom = min(image.size[1], np.floor(bottom).astype('int32'))
                right = min(image.size[0], np.floor(right).astype('int32'))

                dir_save_path = "img_crop"
                if not os.path.exists(dir_save_path):
                    os.makedirs(dir_save_path)
                crop_image = image.crop([left, top, right, bottom])
                crop_image.save(os.path.join(dir_save_path, "crop_" + str(i) + ".png"), quality=95, subsampling=0)
                print("save crop_" + str(i) + ".png to " + dir_save_path)
        # ---------------------------------------------------------#
        #   图像绘制
        # ---------------------------------------------------------#
        for i, c in list(enumerate(top_label)):
            predicted_class = self.class_names[int(c)]
            box = top_boxes[i]
            score = top_conf[i]

            top, left, bottom, right = box

            top = max(0, np.floor(top).astype('int32'))
            left = max(0, np.floor(left).astype('int32'))
            bottom = min(image.size[1], np.floor(bottom).astype('int32'))
            right = min(image.size[0], np.floor(right).astype('int32'))

            label = '{} {:.2f}'.format(predicted_class, score)
            draw = ImageDraw.Draw(image)
            label_size = draw.textsize(label, font)
            label = label.encode('utf-8')
            # print(label, top, left, bottom, right)

            if top - label_size[1] >= 0:
                text_origin = np.array([left, top - label_size[1]])
            else:
                text_origin = np.array([left, top + 1])

            for i in range(thickness):
                draw.rectangle([left + i, top + i, right - i, bottom - i], outline=self.colors[c])
            draw.rectangle([tuple(text_origin), tuple(text_origin + label_size)], fill=self.colors[c])
            draw.text(text_origin, str(label, 'UTF-8'), fill=(0, 0, 0), font=font)
            del draw

        return image

    def get_FPS(self, image, test_interval):
        # ---------------------------------------------------#
        #   计算输入图片的高和宽
        # ---------------------------------------------------#
        image_shape = np.array(np.shape(image)[0:2])
        input_shape = get_new_img_size(image_shape[0], image_shape[1])
        # ---------------------------------------------------------#
        #   在这里将图像转换成RGB图像，防止灰度图在预测时报错。
        #   代码仅仅支持RGB图像的预测，所有其它类型的图像都会转化成RGB
        # ---------------------------------------------------------#
        image = cvtColor(image)

        # ---------------------------------------------------------#
        #   给原图像进行resize，resize到短边为600的大小上
        # ---------------------------------------------------------#
        image_data = resize_image(image, [input_shape[1], input_shape[0]])
        # ---------------------------------------------------------#
        #   添加上batch_size维度
        # ---------------------------------------------------------#
        image_data = np.expand_dims(np.transpose(preprocess_input(np.array(image_data, dtype='float32')), (2, 0, 1)), 0)

        with torch.no_grad():
            images = torch.from_numpy(image_data)

            roi_cls_locs, roi_scores, rois, _ = self.net(images)
            # -------------------------------------------------------------#
            #   利用classifier的预测结果对建议框进行解码，获得预测框
            # -------------------------------------------------------------#
            results = self.bbox_util.forward(roi_cls_locs, roi_scores, rois, image_shape, input_shape,
                                             nms_iou=self.nms_iou, confidence=self.confidence)
        t1 = time.time()
        for _ in range(test_interval):
            with torch.no_grad():
                roi_cls_locs, roi_scores, rois, _ = self.net(images)
                # -------------------------------------------------------------#
                #   利用classifier的预测结果对建议框进行解码，获得预测框
                # -------------------------------------------------------------#
                results = self.bbox_util.forward(roi_cls_locs, roi_scores, rois, image_shape, input_shape,
                                                 nms_iou=self.nms_iou, confidence=self.confidence)

        t2 = time.time()
        tact_time = (t2 - t1) / test_interval
        return tact_time

    # ---------------------------------------------------#
    #   检测图片
    # ---------------------------------------------------#
    def get_map_txt(self, image_id, image, class_names, map_out_path):
        f = open(os.path.join(map_out_path, "detection-results/" + image_id + ".txt"), "w")
        # ---------------------------------------------------#
        #   计算输入图片的高和宽
        # ---------------------------------------------------#
        image_shape = np.array(np.shape(image)[0:2])
        input_shape = get_new_img_size(image_shape[0], image_shape[1])
        # ---------------------------------------------------------#
        #   在这里将图像转换成RGB图像，防止灰度图在预测时报错。
        #   代码仅仅支持RGB图像的预测，所有其它类型的图像都会转化成RGB
        # ---------------------------------------------------------#
        image = cvtColor(image)

        # ---------------------------------------------------------#
        #   给原图像进行resize，resize到短边为600的大小上
        # ---------------------------------------------------------#
        image_data = resize_image(image, [input_shape[1], input_shape[0]])
        # ---------------------------------------------------------#
        #   添加上batch_size维度
        # ---------------------------------------------------------#
        image_data = np.expand_dims(np.transpose(preprocess_input(np.array(image_data, dtype='float32')), (2, 0, 1)), 0)

        with torch.no_grad():
            images = torch.from_numpy(image_data)
            roi_cls_locs, roi_scores, rois, _ = self.net(images)
            # -------------------------------------------------------------#
            #   利用classifier的预测结果对建议框进行解码，获得预测框
            # -------------------------------------------------------------#
            results = self.bbox_util.forward(roi_cls_locs, roi_scores, rois, image_shape, input_shape,
                                             nms_iou=self.nms_iou, confidence=self.confidence)
            # --------------------------------------#
            #   如果没有检测到物体，则返回原图
            # --------------------------------------#
            if len(results[0]) <= 0:
                return

            top_label = np.array(results[0][:, 5], dtype='int32')
            top_conf = results[0][:, 4]
            top_boxes = results[0][:, :4]

        for i, c in list(enumerate(top_label)):
            predicted_class = self.class_names[int(c)]
            box = top_boxes[i]
            score = str(top_conf[i])

            top, left, bottom, right = box
            if predicted_class not in class_names:
                continue

            f.write("%s %s %s %s %s %s\n" % (
            predicted_class, score[:6], str(int(left)), str(int(top)), str(int(right)), str(int(bottom))))

        f.close()
        return
