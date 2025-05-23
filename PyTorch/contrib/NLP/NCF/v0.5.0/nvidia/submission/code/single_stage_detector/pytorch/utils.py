# MIT License
#
# Copyright (c) 2018 kuangliu
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# ------------------------------------------------------------------------------
#
# MIT License
#
# Copyright (c) 2017 Max deGroot, Ellis Brown
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# ------------------------------------------------------------------------------
#
# Copyright (c) 2018, NVIDIA CORPORATION. All rights reserved.
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

import torch
import torch_sdaa
import torchvision
import torchvision.transforms as transforms
import torch.utils.data as data
from PIL import Image
from xml.etree import ElementTree
import os
import glob
from pathlib import Path
import numpy as np
import random
import itertools
import torch.nn.functional as F
try:
    import ujson as json
except ImportError:
    import json
import gc
import time
import bz2
import pickle
from math import sqrt, ceil, cos, sin, pi
from mlperf_compliance import mlperf_log
from mlperf_logger import ssd_print

from SSD import _C as C

from fused_color_jitter import FusedColorJitter

# This function is from https://github.com/kuangliu/pytorch-ssd
def calc_iou_tensor(box1, box2):
    """ Calculation of IoU based on two boxes tensor,
        Reference to https://github.com/kuangliu/pytorch-ssd
        input:
            box1 (N, 4)
            box2 (M, 4)
        output:
            IoU (N, M)
    """
    N = box1.size(0)
    M = box2.size(0)

    be1 = box1.unsqueeze(1).expand(-1, M, -1)
    be2 = box2.unsqueeze(0).expand(N, -1, -1)

    # Left Top & Right Bottom
    lt = torch.max(be1[:,:,:2], be2[:,:,:2])
    #mask1 = (be1[:,:, 0] < be2[:,:, 0]) ^ (be1[:,:, 1] < be2[:,:, 1])
    #mask1 = ~mask1
    rb = torch.min(be1[:,:,2:], be2[:,:,2:])
    #mask2 = (be1[:,:, 2] < be2[:,:, 2]) ^ (be1[:,:, 3] < be2[:,:, 3])
    #mask2 = ~mask2

    delta = rb - lt
    delta[delta < 0] = 0
    intersect = delta[:,:,0]*delta[:,:,1]
    #*mask1.float()*mask2.float()

    delta1 = be1[:,:,2:] - be1[:,:,:2]
    area1 = delta1[:,:,0]*delta1[:,:,1]
    delta2 = be2[:,:,2:] - be2[:,:,:2]
    area2 = delta2[:,:,0]*delta2[:,:,1]

    iou = intersect/(area1 + area2 - intersect)
    return iou

# This class is from https://github.com/kuangliu/pytorch-ssd
class Encoder(object):
    """
        Inspired by https://github.com/kuangliu/pytorch-ssd
        Transform between (bboxes, lables) <-> SSD output

        dboxes: default boxes in size 8732 x 4,
            encoder: input ltrb format, output xywh format
            decoder: input xywh format, output ltrb format

        encode:
            input  : bboxes_in (Tensor nboxes x 4), labels_in (Tensor nboxes)
            output : bboxes_out (Tensor 8732 x 4), labels_out (Tensor 8732)
            criteria : IoU threshold of bboexes

        decode:
            input  : bboxes_in (Tensor 8732 x 4), scores_in (Tensor 8732 x nitems)
            output : bboxes_out (Tensor nboxes x 4), labels_out (Tensor nboxes)
            criteria : IoU threshold of bboexes
            max_output : maximum number of output bboxes
    """

    def __init__(self, dboxes):
        self.dboxes = dboxes(order="ltrb")
        self.dboxes_xywh = dboxes(order="xywh").unsqueeze(dim=0)
        self.nboxes = self.dboxes.size(0)
        #print("# Bounding boxes: {}".format(self.nboxes))
        self.scale_xy = dboxes.scale_xy
        self.scale_wh = dboxes.scale_wh

    def encode(self, bboxes_in, labels_in, criteria = 0.5):

        try:
            ious = calc_iou_tensor(bboxes_in, self.dboxes)
            best_dbox_ious, best_dbox_idx = ious.max(dim=0)
            best_bbox_ious, best_bbox_idx = ious.max(dim=1)

            # set best ious 2.0
            best_dbox_ious.index_fill_(0, best_bbox_idx, 2.0)

            idx = torch.arange(0, best_bbox_idx.size(0), dtype=torch.int64)
            best_dbox_idx[best_bbox_idx[idx]] = idx

            # filter IoU > 0.5
            masks = best_dbox_ious > criteria
            labels_out = torch.zeros(self.nboxes, dtype=torch.long)
            #print(maxloc.shape, labels_in.shape, labels_out.shape)

            #print("labels_out")
            #print(labels_out.shape)
            #print("masks")
            #print(masks.shape)
            #print("labels_in")
            #print(labels_in.shape)
            #print("best_dbox_idx")
            #print(best_dbox_idx.shape)

            labels_out[masks] = labels_in[best_dbox_idx[masks]]
            bboxes_out = self.dboxes.clone()
            bboxes_out[masks, :] = bboxes_in[best_dbox_idx[masks], :]
            # Transform format to xywh format
            x, y, w, h = 0.5*(bboxes_out[:, 0] + bboxes_out[:, 2]), \
                         0.5*(bboxes_out[:, 1] + bboxes_out[:, 3]), \
                         -bboxes_out[:, 0] + bboxes_out[:, 2], \
                         -bboxes_out[:, 1] + bboxes_out[:, 3]
            bboxes_out[:, 0] = x
            bboxes_out[:, 1] = y
            bboxes_out[:, 2] = w
            bboxes_out[:, 3] = h
        except:
            labels_out = torch.zeros(self.nboxes, dtype=torch.long)
            bboxes_out = torch.zeros(self.nboxes, 4)
        return bboxes_out, labels_out

    def scale_back_batch(self, bboxes_in, scores_in):
        """
            Do scale and transform from xywh to ltrb
            suppose input Nx4xnum_bbox Nxlabel_numxnum_bbox
        """
        if bboxes_in.device == torch.device("cpu"):
            self.dboxes = self.dboxes.cpu()
            self.dboxes_xywh = self.dboxes_xywh.cpu()
        else:
            self.dboxes = self.dboxes.cuda()
            self.dboxes_xywh = self.dboxes_xywh.cuda()

        bboxes_in = bboxes_in.permute(0, 2, 1)
        scores_in = scores_in.permute(0, 2, 1)
        #print(bboxes_in.device, scores_in.device, self.dboxes_xywh.device)

        bboxes_in[:, :, :2] = self.scale_xy*bboxes_in[:, :, :2]
        bboxes_in[:, :, 2:] = self.scale_wh*bboxes_in[:, :, 2:]

        bboxes_in[:, :, :2] = bboxes_in[:, :, :2]*self.dboxes_xywh[:, :, 2:] + self.dboxes_xywh[:, :, :2]
        bboxes_in[:, :, 2:] = bboxes_in[:, :, 2:].exp()*self.dboxes_xywh[:, :, 2:]

        # Transform format to ltrb
        l, t, r, b = bboxes_in[:, :, 0] - 0.5*bboxes_in[:, :, 2],\
                     bboxes_in[:, :, 1] - 0.5*bboxes_in[:, :, 3],\
                     bboxes_in[:, :, 0] + 0.5*bboxes_in[:, :, 2],\
                     bboxes_in[:, :, 1] + 0.5*bboxes_in[:, :, 3]

        bboxes_in[:, :, 0] = l
        bboxes_in[:, :, 1] = t
        bboxes_in[:, :, 2] = r
        bboxes_in[:, :, 3] = b

        return bboxes_in, F.softmax(scores_in, dim=-1)

    def decode_batch(self, bboxes_in, scores_in,  criteria = 0.45, max_output=200):
        bboxes, probs = self.scale_back_batch(bboxes_in, scores_in)

        output = []
        for bbox, prob in zip(bboxes.split(1, 0), probs.split(1, 0)):
            bbox = bbox.squeeze(0)
            prob = prob.squeeze(0)
            output.append(self.decode_single(bbox, prob, criteria, max_output))
            #print(output[-1])
        return output

    # perform non-maximum suppression
    def decode_single(self, bboxes_in, scores_in, criteria, max_output, max_num=200):
        # Reference to https://github.com/amdegroot/ssd.pytorch

        bboxes_out = []
        scores_out = []
        labels_out = []

        for i, score in enumerate(scores_in.split(1, 1)):
            # skip background
            # print(score[score>0.90])
            if i == 0: continue
            # print(i)

            score = score.squeeze(1)
            mask = score > 0.05

            bboxes, score = bboxes_in[mask, :], score[mask]
            if score.size(0) == 0: continue

            score_sorted, score_idx_sorted = score.sort(dim=0)

            # select max_output indices
            score_idx_sorted = score_idx_sorted[-max_num:]
            candidates = []
            #maxdata, maxloc = scores_in.sort()

            while score_idx_sorted.numel() > 0:
                idx = score_idx_sorted[-1].item()
                # bboxes_sorted = bboxes[score_idx_sorted, :]
                bboxes_sorted = bboxes.index_select(0, score_idx_sorted)
                bboxes_idx = bboxes[idx, :].unsqueeze(dim=0)
                if True:
                    bbox_offsets = torch.tensor([0, bboxes_sorted.shape[0]], dtype=torch.int32).to(bboxes_sorted.device)
                    iou_sorted = C.calc_ious(1, bboxes_sorted, bbox_offsets, bboxes_idx).squeeze()
                else:
                    iou_sorted = calc_iou_tensor(bboxes_sorted, bboxes_idx).squeeze()
                # we only need iou < criteria
                mask = iou_sorted < criteria
                score_idx_sorted = score_idx_sorted.masked_select(mask)
                # score_idx_sorted = score_idx_sorted[iou_sorted < criteria]
                candidates.append(idx)

            bboxes_out.append(bboxes[candidates, :])
            scores_out.append(score[candidates])
            labels_out.extend([i]*len(candidates))

        bboxes_out, labels_out, scores_out = torch.cat(bboxes_out, dim=0), \
               torch.tensor(labels_out, dtype=torch.long), \
               torch.cat(scores_out, dim=0)


        _, max_ids = scores_out.sort(dim=0)
        max_ids = max_ids[-max_output:]
        return bboxes_out[max_ids, :], labels_out[max_ids], scores_out[max_ids]


class DefaultBoxes(object):
    def __init__(self, fig_size, feat_size, steps, scales, aspect_ratios, \
                       scale_xy=0.1, scale_wh=0.2):

        self.feat_size = feat_size
        self.fig_size = fig_size

        self.scale_xy_ = scale_xy
        self.scale_wh_ = scale_wh

        # According to https://github.com/weiliu89/caffe
        # Calculation method slightly different from paper
        self.steps = steps
        self.scales = scales

        fk = fig_size/np.array(steps)
        self.aspect_ratios = aspect_ratios

        self.default_boxes = []
        # size of feature and number of feature
        for idx, sfeat in enumerate(self.feat_size):

            sk1 = scales[idx]/fig_size
            sk2 = scales[idx+1]/fig_size
            sk3 = sqrt(sk1*sk2)
            all_sizes = [(sk1, sk1), (sk3, sk3)]

            for alpha in aspect_ratios[idx]:
                w, h = sk1*sqrt(alpha), sk1/sqrt(alpha)
                all_sizes.append((w, h))
                all_sizes.append((h, w))
            for w, h in all_sizes:
                for i, j in itertools.product(range(sfeat), repeat=2):
                    cx, cy = (j+0.5)/fk[idx], (i+0.5)/fk[idx]
                    self.default_boxes.append((cx, cy, w, h))

        self.dboxes = torch.tensor(self.default_boxes)
        self.dboxes.clamp_(min=0, max=1)
        # For IoU calculation
        self.dboxes_ltrb = self.dboxes.clone()
        self.dboxes_ltrb[:, 0] = self.dboxes[:, 0] - 0.5*self.dboxes[:, 2]
        self.dboxes_ltrb[:, 1] = self.dboxes[:, 1] - 0.5*self.dboxes[:, 3]
        self.dboxes_ltrb[:, 2] = self.dboxes[:, 0] + 0.5*self.dboxes[:, 2]
        self.dboxes_ltrb[:, 3] = self.dboxes[:, 1] + 0.5*self.dboxes[:, 3]

    @property
    def scale_xy(self):
        return self.scale_xy_

    @property
    def scale_wh(self):
        return self.scale_wh_

    def __call__(self, order="ltrb"):
        if order == "ltrb": return self.dboxes_ltrb
        if order == "xywh": return self.dboxes


# This class is from https://github.com/chauhan-utk/ssd.DomainAdaptation
class SSDCropping(object):
    """ Cropping for SSD, according to original paper
        Choose between following 3 conditions:
        1. Preserve the original image
        2. Random crop minimum IoU is among 0.1, 0.3, 0.5, 0.7, 0.9
        3. Random crop
        Reference to https://github.com/chauhan-utk/ssd.DomainAdaptation
    """
    def __init__(self):

        self.sample_options = (
            # Do nothing
            None,
            # min IoU, max IoU
            (0.1, None),
            (0.3, None),
            (0.5, None),
            (0.7, None),
            (0.9, None),
            # no IoU requirements
            (None, None),
        )
        # Implementation uses 1 iteration to find a possible candidate, this
        # was shown to produce the same mAP as using more iterations.
        self.num_cropping_iterations = 1
        ssd_print(key=mlperf_log.NUM_CROPPING_ITERATIONS,
                             value=self.num_cropping_iterations)

    def __call__(self, img, img_size, bboxes, labels):

        # Ensure always return cropped image
        while True:
            mode = random.choice(self.sample_options)

            if mode is None:
                return img, img_size, bboxes, labels

            htot, wtot = img_size

            min_iou, max_iou = mode
            min_iou = float("-inf") if min_iou is None else min_iou
            max_iou = float("+inf") if max_iou is None else max_iou

            # Implementation use 50 iteration to find possible candidate
            for _ in range(self.num_cropping_iterations):
                # suze of each sampled path in [0.1, 1] 0.3*0.3 approx. 0.1
                w = random.uniform(0.3 , 1.0)
                h = random.uniform(0.3 , 1.0)

                if w/h < 0.5 or w/h > 2:
                    continue

                # left 0 ~ wtot - w, top 0 ~ htot - h
                left = random.uniform(0, 1.0 - w)
                top = random.uniform(0, 1.0 - h)

                right = left + w
                bottom = top + h

                ious = calc_iou_tensor(bboxes, torch.tensor([[left, top, right, bottom]]))

                # tailor all the bboxes and return
                if not ((ious > min_iou) & (ious < max_iou)).all():
                    continue

                # discard any bboxes whose center not in the cropped image
                xc = 0.5*(bboxes[:, 0] + bboxes[:, 2])
                yc = 0.5*(bboxes[:, 1] + bboxes[:, 3])

                masks = (xc > left) & (xc < right) & (yc > top) & (yc < bottom)

                # if no such boxes, continue searching again
                if not masks.any():
                    continue

                bboxes[bboxes[:, 0] < left, 0] = left
                bboxes[bboxes[:, 1] < top, 1] = top
                bboxes[bboxes[:, 2] > right, 2] = right
                bboxes[bboxes[:, 3] > bottom, 3] = bottom

                #print(left, top, right, bottom)
                #print(labels, bboxes, masks)
                bboxes = bboxes[masks, :]
                labels = labels[masks]

                left_idx = int(left*wtot)
                top_idx =  int(top*htot)
                right_idx = int(right*wtot)
                bottom_idx = int(bottom*htot)
                #print(left_idx,top_idx,right_idx,bottom_idx)
                #img = img[:, top_idx:bottom_idx, left_idx:right_idx]
                img = img.crop((left_idx, top_idx, right_idx, bottom_idx))

                bboxes[:, 0] = (bboxes[:, 0] - left)/w
                bboxes[:, 1] = (bboxes[:, 1] - top)/h
                bboxes[:, 2] = (bboxes[:, 2] - left)/w
                bboxes[:, 3] = (bboxes[:, 3] - top)/h

                htot = bottom_idx - top_idx
                wtot = right_idx - left_idx
                return img, (htot, wtot), bboxes, labels

# Don't need to cast to float, already there (from FusedColorJitter)
class ToTensor(object):
    def __init__(self):
        pass

    def __call__(self, img):
        img = torch.Tensor(np.array(img))
        # Transform from HWC to CHW
        img = img.permute(2, 0 ,1).div(255)
        return img

class LightingNoice(object):
    """
        See this question, AlexNet data augumentation:
        https://stackoverflow.com/questions/43328600
    """
    def __init__(self):
        self.eigval = torch.tensor([55.46, 4.794, 1.148])
        self.eigvec = torch.tensor([
            [-0.5675, 0.7192, 0.4009],
            [-0.5808, -0.0045, -0.8140],
            [-0.5836, -0.6948, 0.4203]])

    def __call__(self, img):
        img = torch.Tensor(np.array(img))
        # Transform from HWC to CHW
        img = img.permute(2, 0 ,1)
        return img
        alpha0 = random.gauss(sigma=0.1, mu=0)
        alpha1 = random.gauss(sigma=0.1, mu=0)
        alpha2 = random.gauss(sigma=0.1, mu=0)

        channels = alpha0*self.eigval[0]*self.eigvec[0, :] + \
                   alpha1*self.eigval[1]*self.eigvec[1, :] + \
                   alpha2*self.eigval[2]*self.eigvec[2, :]
        channels = channels.view(3, 1, 1)
        img += channels

        return img

class RandomHorizontalFlip(object):
    def __init__(self, p=0.5):
        self.p = p
        ssd_print(key=mlperf_log.RANDOM_FLIP_PROBABILITY, value=self.p)

    def __call__(self, image, bboxes):
        if random.random() < self.p:
            bboxes[:, 0], bboxes[:, 2] = 1.0 - bboxes[:, 2], 1.0 - bboxes[:, 0]
            return image.transpose(Image.FLIP_LEFT_RIGHT), bboxes
        return image, bboxes

# Do data augumentation
class SSDTransformer(object):
    """ SSD Data Augumentation, according to original paper
        Composed by several steps:
        Cropping
        Resize
        Flipping
        Jittering
    """
    def __init__(self, dboxes, size = (300, 300), val=False):

        # define vgg16 mean
        self.size = size
        self.val = val

        self.dboxes_ = dboxes #DefaultBoxes300()
        self.encoder = Encoder(self.dboxes_)

        self.crop = SSDCropping()
        self.img_trans = transforms.Compose([
            transforms.Resize(self.size),
            #transforms.ColorJitter(brightness=0.125, contrast=0.5,
            #    saturation=0.5, hue=0.05
            #),
            #transforms.ToTensor(),
            FusedColorJitter(),
            ToTensor(),
        ])
        self.hflip = RandomHorizontalFlip()

        # All Pytorch Tensor will be normalized
        # https://discuss.pytorch.org/t/how-to-preprocess-input-for-pre-trained-networks/683

        normalization_mean = [0.485, 0.456, 0.406]
        normalization_std = [0.229, 0.224, 0.225]
        ssd_print(key=mlperf_log.DATA_NORMALIZATION_MEAN, value=normalization_mean)
        ssd_print(key=mlperf_log.DATA_NORMALIZATION_STD, value=normalization_std)
        self.normalize = transforms.Normalize(mean=normalization_mean,
                                              std=normalization_std)

        self.trans_val = transforms.Compose([
            transforms.Resize(self.size),
            transforms.ToTensor(),
            self.normalize,])

    @property
    def dboxes(self):
        return self.dboxes_

    def __call__(self, img, img_size, bbox=None, label=None, max_num=200):
        #img = torch.tensor(img)
        if self.val:
            bbox_out = torch.zeros(max_num, 4)
            label_out =  torch.zeros(max_num, dtype=torch.long)
            bbox_out[:bbox.size(0), :] = bbox
            label_out[:label.size(0)] = label
            return self.trans_val(img), img_size, bbox_out, label_out

        # random crop
        img, img_size, bbox, label = self.crop(img, img_size, bbox, label)

        # random horiz. flip
        img, bbox = self.hflip(img, bbox)

        # [Resize, ColorJitter, ToTensor]
        img = self.img_trans(img).contiguous()

        img = self.normalize(img)

        # handled by later batched encoder
        # bbox, label = self.encoder.encode(bbox, label)

        return img, img_size, bbox, label

# Implement a datareader for COCO dataset
class COCODetection(data.Dataset):
    def __init__(self, img_folder, annotate_file, transform=None):
        self.img_folder = img_folder
        self.annotate_file = annotate_file

        # Start processing annotation
        with open(annotate_file) as fin:
            # loading huge json files tends to cause the gc (cycle collector) to
            # waste a lot of time so:
            gc_old = gc.isenabled()
            gc.disable()

            self.data = json.load(fin)

            if gc_old: gc.enable()

        self.images = {}

        self.label_map = {}
        self.label_info = {}
        #print("Parsing COCO data...")
        start_time = time.time()
        # 0 stand for the background
        cnt = 0
        self.label_info[cnt] = "background"
        for cat in self.data["categories"]:
            cnt += 1
            self.label_map[cat["id"]] = cnt
            self.label_info[cnt] = cat["name"]

        # build inference for images
        for img in self.data["images"]:
            img_id = img["id"]
            img_name = img["file_name"]
            img_size = (img["height"],img["width"])
            #print(img_name)
            if img_id in self.images: raise Exception("dulpicated image record")
            self.images[img_id] = (img_name, img_size, [])

        # read bboxes
        for bboxes in self.data["annotations"]:
            img_id = bboxes["image_id"]
            category_id = bboxes["category_id"]
            bbox = bboxes["bbox"]
            bbox_label = self.label_map[bboxes["category_id"]]
            self.images[img_id][2].append((bbox, bbox_label))

        for k, v in list(self.images.items()):
            if len(v[2]) == 0:
                #print("empty image: {}".format(k))
                self.images.pop(k)

        self.img_keys = list(self.images.keys())
        self.transform = transform
        #print("End parsing COCO data, total time {}".format(time.time()-start_time))

    @property
    def labelnum(self):
        return len(self.label_info)

    @staticmethod
    def load(pklfile):
        #print("Loading from {}".format(pklfile))
        with bz2.open(pklfile, "rb") as fin:
            ret = pickle.load(fin)
        return ret

    def save(self, pklfile):
        #print("Saving to {}".format(pklfile))
        with bz2.open(pklfile, "wb") as fout:
            pickle.dump(self, fout)


    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        img_id = self.img_keys[idx]
        img_data = self.images[img_id]
        fn = img_data[0]
        img_path = os.path.join(self.img_folder, fn)
        s = time.time()
        img = Image.open(img_path).convert("RGB")
        e = time.time()
        decode_time = e - s

        htot, wtot = img_data[1]
        bbox_sizes = []
        bbox_labels = []

        #for (xc, yc, w, h), bbox_label in img_data[2]:
        for (l,t,w,h), bbox_label in img_data[2]:
            r = l + w
            b = t + h
            #l, t, r, b = xc - 0.5*w, yc - 0.5*h, xc + 0.5*w, yc + 0.5*h
            bbox_size = (l/wtot, t/htot, r/wtot, b/htot)
            bbox_sizes.append(bbox_size)
            bbox_labels.append(bbox_label)

        bbox_sizes = torch.tensor(bbox_sizes)
        bbox_labels =  torch.tensor(bbox_labels)

        s = time.time()
        if self.transform != None:
            img, (htot, wtot), bbox_sizes, bbox_labels = \
                self.transform(img, (htot, wtot), bbox_sizes, bbox_labels)
        else:
            pass # img = transforms.ToTensor()(img)

        return img, img_id, (htot, wtot), bbox_sizes, bbox_labels

# Implement a datareader for VOC dataset
class VOCDetection(data.Dataset):
    """  VOC PASCAL 07/12 DataReader
         params:
            img:        image folder
            annotate:   annotation folder (xml)
    """
    def __init__(self, img_folder, annotate_folder, file_filter, transform=None, label_map = {}, difficult=True):
        #print("Reading data informations")

        self.img_folder = img_folder
        self.annotate_folder = annotate_folder
        self.transform = transform
        self.difficult = difficult
        self.file_filter = file_filter

        # Read file filter to filter out files
        with open(file_filter, "r") as fin:
            self.filter = fin.read().strip().split("\n")

        self.images = []
        self.label_num = 0
        self.label_map = {v:k for k, v in label_map.items()}

        for xml_file in glob.glob(os.path.join(annotate_folder, "*.xml")):
            ret = self._parse_xml(xml_file)
            if ret:
                self.images.append(ret)

        self.label_map = {v:k for k, v in self.label_map.items()}
        # Add background label
        self.label_map[0] = "background"
        self.label_num += 1
        #print("Finished Reading")

    def _parse_xml(self, xml_file):
        #print(xml_file)
        root = ElementTree.ElementTree(file=xml_file)
        img_name = root.find("filename").text
        # Get basename
        base_name = Path(img_name).resolve().stem
        if base_name not in self.filter:
            return []

        img_size = (
            int(root.find("size").find("height").text) ,
            int(root.find("size").find("width").text)  ,
            int(root.find("size").find("depth").text)  , )

        tmp_data = []
        for obj in root.findall("object"):
            # extract xmin, ymin, xmax, ymax
            difficult = obj.find("difficult").text
            if difficult == "1" and not self.difficult:
                continue
            bbox = (
                int(obj.find("bndbox").find("xmin").text),
                int(obj.find("bndbox").find("ymin").text),
                int(obj.find("bndbox").find("xmax").text),
                int(obj.find("bndbox").find("ymax").text), )
            bbox_label = obj.find("name").text
            if bbox_label in self.label_map:
                bbox_label = self.label_map[bbox_label]
            else:
                self.label_num += 1
                self.label_map[bbox_label] = self.label_num
                bbox_label = self.label_num
            tmp_data.append((bbox, bbox_label))

        return (img_name, img_size, tmp_data)

    def __getitem__(self, idx):

        image_info = self.images[idx]
        #print(self.images)
        #print(image_info)
        img_path = os.path.join(self.img_folder, image_info[0])
        #img = np.array(Image.open(img_path).convert('RGB'))
        img = Image.open(img_path)

        # Assert the record in xml and image matches
        # assert img.size == image_info[1], "Image Size Does Not Match!"

        htot, wtot, _ = image_info[1]

        bbox_sizes = []
        bbox_labels = []

        for (xmin, ymin, xmax, ymax), bbox_label in image_info[2]:
            #cx, cy, w, h = (xmin + xmax)/2, (ymin + ymax)/2, xmax - xmin, ymax - ymin
            #bbox_size = (cx, cy, w, h)
            #print(cx, cy, w, h)
            #bbox_size = (cx/wtot, cy/htot, w/wtot, h/htot)
            l, t, r, b = xmin, ymin, xmax, ymax
            bbox_size = (l/wtot, t/htot, r/wtot, b/htot)
            bbox_sizes.append(bbox_size)
            #bbox_labels.append(self.label_map[bbox_label])
            bbox_labels.append(bbox_label)

        bbox_sizes = torch.tensor(bbox_sizes)
        bbox_labels =  torch.tensor(bbox_labels)
        #bbox_size = (xmin, ymin, xmax, ymax)
        #bbox_label = bbox_info[3]

        # Perform image transformation
        if self.transform != None:
            img, (htot, wtot), bbox_sizes, bbox_labels = \
                self.transform(img, (htot, wtot), bbox_sizes, bbox_labels)
        else:
            img = torch.tensor(img)

        #print(img.shape, bbox_sizes.shape, bbox_labels.shape)
        #print(idx, "non_bg:", (bbox_labels > 0).sum().item())
        #print(img.shape)
        return img, (htot, wtot), bbox_sizes, bbox_labels

    def __len__(self):
        return len(self.images)


def draw_patches(img, bboxes, labels, order="xywh", label_map={}):

    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    # Suppose bboxes in fractional coordinate:
    # cx, cy, w, h
    # img = img.numpy()
    img = np.array(img)
    labels = np.array(labels)
    bboxes = bboxes.numpy()

    if label_map:
        labels = [label_map.get(l) for l in labels]

    if order == "ltrb":
        xmin, ymin, xmax, ymax = bboxes[:, 0],  bboxes[:, 1],  bboxes[:, 2],  bboxes[:, 3]
        cx, cy, w, h = (xmin + xmax)/2, (ymin + ymax)/2, xmax - xmin, ymax - ymin
    else:
        cx, cy, w, h = bboxes[:, 0],  bboxes[:, 1],  bboxes[:, 2],  bboxes[:, 3]

    htot, wtot,_ = img.shape
    cx *= wtot
    cy *= htot
    w *= wtot
    h *= htot

    bboxes = zip(cx, cy, w, h)

    plt.imshow(img)
    ax = plt.gca()
    for (cx, cy, w, h), label in zip(bboxes, labels):
        if label == "background": continue
        ax.add_patch(patches.Rectangle((cx-0.5*w, cy-0.5*h),
                                        w, h, fill=False, color="r"))
        bbox_props = dict(boxstyle="round", fc="y", ec="0.5", alpha=0.3)
        ax.text(cx-0.5*w, cy-0.5*h, label, ha="center", va="center", size=15, bbox=bbox_props)
    plt.show()


if __name__ == "__main__":

    #trans = SSDTransformer()
    #vd = VOCDetection("../../VOCdevkit/VOC2007/JPEGImages",
    #                  "../../VOCdevkit/VOC2007/Annotations",
    #                  "../../VOCdevkit/VOC2007/ImageSets/Main/trainval.txt",
    #                  transform = trans)

    #imgs, img_size, bbox, label = vd[0]
    #img = imgs[:, :, :]
    #img *= torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
    #img += torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
    #img = img.permute(1, 2, 0)
    #print(bbox[label>0], label[label>0])
    #draw_patches(img, bbox[label>0], label[label>0], order="xywh", label_map=vd.label_map)

    annotate = "../../coco_ssd/instances_valminusminival2014.json"
    coco_root = "../../coco_data/val2014"

    coco = COCODetection(coco_root, annotate)
    #coco.save("save.pb2")
    print(len(coco))
    #img, img_size, bbox, label = coco[2]
    #draw_patches(img, bbox, label, order="ltrb", label_map=coco.label_info)
