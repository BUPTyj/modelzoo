# Copyright (c) OpenMMLab. All rights reserved.
import numpy as np
import pytest
import torch

from mmcv.ops import convex_giou, convex_iou

np_pointsets = np.asarray([[
    1.0, 1.0, 2.0, 2.0, 1.0, 2.0, 2.0, 1.0, 1.0, 3.0, 3.0, 1.0, 2.0, 3.0, 3.0,
    2.0, 1.5, 1.5
],
                           [
                               1.5, 1.5, 2.5, 2.5, 1.5, 2.5, 2.5, 1.5, 1.5,
                               3.5, 3.5, 1.5, 2.5, 3.5, 3.5, 2.5, 2.0, 2.0
                           ]])

np_polygons = np.asarray([[1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 2.0, 1.0],
                          [1.0, 1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 1.0]])

np_expected_iou = np.asarray([[0.2857, 0.8750], [0.0588, 0.4286]])

np_expected_giou = np.asarray([0.2857, 0.3831])

np_expected_grad = np.asarray([[
    0.0204, 0.0408, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0612,
    -0.0408, -0.0408, 0.0816, -0.0408, -0.0816, -0.0816, -0.0408, 0.0000,
    0.0000
],
                               [
                                   -0.1848, -0.1848, 0.0000, 0.0000, 0.0000,
                                   0.0000, 0.0000, 0.0000, -0.1076, -0.0801,
                                   -0.0801, -0.1076, -0.0367, -0.0734, -0.0734,
                                   -0.0367, 0.0000, 0.0000
                               ]])


@pytest.mark.skipif(
    not torch.sdaa.is_available(), reason='requires SDAA support')
def test_convex_iou():
    pointsets = torch.from_numpy(np_pointsets).sdaa().float()
    polygons = torch.from_numpy(np_polygons).sdaa().float()
    expected_iou = torch.from_numpy(np_expected_iou).sdaa().float()
    assert torch.allclose(
        convex_iou(pointsets, polygons), expected_iou, atol=1e-3)


@pytest.mark.skipif(
    not torch.sdaa.is_available(), reason='requires SDAA support')
def test_convex_giou():
    pointsets = torch.from_numpy(np_pointsets).sdaa().float()
    polygons = torch.from_numpy(np_polygons).sdaa().float()
    expected_giou = torch.from_numpy(np_expected_giou).sdaa().float()
    expected_grad = torch.from_numpy(np_expected_grad).sdaa().float()
    giou, grad = convex_giou(pointsets, polygons)
    assert torch.allclose(giou, expected_giou, atol=1e-3)
    assert torch.allclose(grad, expected_grad, atol=1e-3)
