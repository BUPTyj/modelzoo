# Copyright (c) OpenMMLab. All rights reserved.
import pytest
import torch
import torch_sdaa
from mmcv.ops import DeformConv2dPack
from mmengine.utils.dl_utils.parrots_wrapper import _BatchNorm
from torch.nn.modules import AvgPool2d, GroupNorm

from mmseg.models.backbones import ResNet, ResNetV1d
from mmseg.models.backbones.resnet import BasicBlock, Bottleneck
from mmseg.models.utils import ResLayer
from .utils import all_zeros, check_norm_state, is_block, is_norm


def test_resnet_basic_block():
    with pytest.raises(AssertionError):
        # Not implemented yet.
        dcn = dict(type='DCN', deform_groups=1, fallback_on_stride=False)
        BasicBlock(64, 64, dcn=dcn)

    with pytest.raises(AssertionError):
        # Not implemented yet.
        plugins = [
            dict(
                cfg=dict(type='ContextBlock', ratio=1. / 16),
                position='after_conv3')
        ]
        BasicBlock(64, 64, plugins=plugins)

    with pytest.raises(AssertionError):
        # Not implemented yet
        plugins = [
            dict(
                cfg=dict(
                    type='GeneralizedAttention',
                    spatial_range=-1,
                    num_heads=8,
                    attention_type='0010',
                    kv_stride=2),
                position='after_conv2')
        ]
        BasicBlock(64, 64, plugins=plugins)

    # Test BasicBlock with checkpoint forward
    block = BasicBlock(16, 16, with_cp=True)
    assert block.with_cp
    x = torch.randn(1, 16, 28, 28)
    x_out = block(x)
    assert x_out.shape == torch.Size([1, 16, 28, 28])

    # test BasicBlock structure and forward
    block = BasicBlock(32, 32)
    assert block.conv1.in_channels == 32
    assert block.conv1.out_channels == 32
    assert block.conv1.kernel_size == (3, 3)
    assert block.conv2.in_channels == 32
    assert block.conv2.out_channels == 32
    assert block.conv2.kernel_size == (3, 3)
    x = torch.randn(1, 32, 28, 28)
    x_out = block(x)
    assert x_out.shape == torch.Size([1, 32, 28, 28])


def test_resnet_bottleneck():
    with pytest.raises(AssertionError):
        # Style must be in ['pytorch', 'caffe']
        Bottleneck(64, 64, style='tensorflow')

    with pytest.raises(AssertionError):
        # Allowed positions are 'after_conv1', 'after_conv2', 'after_conv3'
        plugins = [
            dict(
                cfg=dict(type='ContextBlock', ratio=1. / 16),
                position='after_conv4')
        ]
        Bottleneck(64, 16, plugins=plugins)

    with pytest.raises(AssertionError):
        # Need to specify different postfix to avoid duplicate plugin name
        plugins = [
            dict(
                cfg=dict(type='ContextBlock', ratio=1. / 16),
                position='after_conv3'),
            dict(
                cfg=dict(type='ContextBlock', ratio=1. / 16),
                position='after_conv3')
        ]
        Bottleneck(64, 16, plugins=plugins)

    with pytest.raises(KeyError):
        # Plugin type is not supported
        plugins = [dict(cfg=dict(type='WrongPlugin'), position='after_conv3')]
        Bottleneck(64, 16, plugins=plugins)

    # Test Bottleneck with checkpoint forward
    block = Bottleneck(64, 16, with_cp=True)
    assert block.with_cp
    x = torch.randn(1, 64, 56, 56)
    x_out = block(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])

    # Test Bottleneck style
    block = Bottleneck(64, 64, stride=2, style='pytorch')
    assert block.conv1.stride == (1, 1)
    assert block.conv2.stride == (2, 2)
    block = Bottleneck(64, 64, stride=2, style='caffe')
    assert block.conv1.stride == (2, 2)
    assert block.conv2.stride == (1, 1)

    # Test Bottleneck DCN
    dcn = dict(type='DCN', deform_groups=1, fallback_on_stride=False)
    with pytest.raises(AssertionError):
        Bottleneck(64, 64, dcn=dcn, conv_cfg=dict(type='Conv'))
    block = Bottleneck(64, 64, dcn=dcn)
    assert isinstance(block.conv2, DeformConv2dPack)

    # Test Bottleneck forward
    block = Bottleneck(64, 16)
    x = torch.randn(1, 64, 56, 56)
    x_out = block(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])

    # Test Bottleneck with 1 ContextBlock after conv3
    plugins = [
        dict(
            cfg=dict(type='ContextBlock', ratio=1. / 16),
            position='after_conv3')
    ]
    block = Bottleneck(64, 16, plugins=plugins)
    assert block.context_block.in_channels == 64
    x = torch.randn(1, 64, 56, 56)
    x_out = block(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])

    # Test Bottleneck with 1 GeneralizedAttention after conv2
    plugins = [
        dict(
            cfg=dict(
                type='GeneralizedAttention',
                spatial_range=-1,
                num_heads=8,
                attention_type='0010',
                kv_stride=2),
            position='after_conv2')
    ]
    block = Bottleneck(64, 16, plugins=plugins)
    assert block.gen_attention_block.in_channels == 16
    x = torch.randn(1, 64, 56, 56)
    x_out = block(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])

    # Test Bottleneck with 1 GeneralizedAttention after conv2, 1 NonLocal2d
    # after conv2, 1 ContextBlock after conv3
    plugins = [
        dict(
            cfg=dict(
                type='GeneralizedAttention',
                spatial_range=-1,
                num_heads=8,
                attention_type='0010',
                kv_stride=2),
            position='after_conv2'),
        dict(cfg=dict(type='NonLocal2d'), position='after_conv2'),
        dict(
            cfg=dict(type='ContextBlock', ratio=1. / 16),
            position='after_conv3')
    ]
    block = Bottleneck(64, 16, plugins=plugins)
    assert block.gen_attention_block.in_channels == 16
    assert block.nonlocal_block.in_channels == 16
    assert block.context_block.in_channels == 64
    x = torch.randn(1, 64, 56, 56)
    x_out = block(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])

    # Test Bottleneck with 1 ContextBlock after conv2, 2 ContextBlock after
    # conv3
    plugins = [
        dict(
            cfg=dict(type='ContextBlock', ratio=1. / 16, postfix=1),
            position='after_conv2'),
        dict(
            cfg=dict(type='ContextBlock', ratio=1. / 16, postfix=2),
            position='after_conv3'),
        dict(
            cfg=dict(type='ContextBlock', ratio=1. / 16, postfix=3),
            position='after_conv3')
    ]
    block = Bottleneck(64, 16, plugins=plugins)
    assert block.context_block1.in_channels == 16
    assert block.context_block2.in_channels == 64
    assert block.context_block3.in_channels == 64
    x = torch.randn(1, 64, 56, 56)
    x_out = block(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])


def test_resnet_res_layer():
    # Test ResLayer of 3 Bottleneck w\o downsample
    layer = ResLayer(Bottleneck, 64, 16, 3)
    assert len(layer) == 3
    assert layer[0].conv1.in_channels == 64
    assert layer[0].conv1.out_channels == 16
    for i in range(1, len(layer)):
        assert layer[i].conv1.in_channels == 64
        assert layer[i].conv1.out_channels == 16
    for i in range(len(layer)):
        assert layer[i].downsample is None
    x = torch.randn(1, 64, 56, 56)
    x_out = layer(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])

    # Test ResLayer of 3 Bottleneck with downsample
    layer = ResLayer(Bottleneck, 64, 64, 3)
    assert layer[0].downsample[0].out_channels == 256
    for i in range(1, len(layer)):
        assert layer[i].downsample is None
    x = torch.randn(1, 64, 56, 56)
    x_out = layer(x)
    assert x_out.shape == torch.Size([1, 256, 56, 56])

    # Test ResLayer of 3 Bottleneck with stride=2
    layer = ResLayer(Bottleneck, 64, 64, 3, stride=2)
    assert layer[0].downsample[0].out_channels == 256
    assert layer[0].downsample[0].stride == (2, 2)
    for i in range(1, len(layer)):
        assert layer[i].downsample is None
    x = torch.randn(1, 64, 56, 56)
    x_out = layer(x)
    assert x_out.shape == torch.Size([1, 256, 28, 28])

    # Test ResLayer of 3 Bottleneck with stride=2 and average downsample
    layer = ResLayer(Bottleneck, 64, 64, 3, stride=2, avg_down=True)
    assert isinstance(layer[0].downsample[0], AvgPool2d)
    assert layer[0].downsample[1].out_channels == 256
    assert layer[0].downsample[1].stride == (1, 1)
    for i in range(1, len(layer)):
        assert layer[i].downsample is None
    x = torch.randn(1, 64, 56, 56)
    x_out = layer(x)
    assert x_out.shape == torch.Size([1, 256, 28, 28])

    # Test ResLayer of 3 Bottleneck with dilation=2
    layer = ResLayer(Bottleneck, 64, 16, 3, dilation=2)
    for i in range(len(layer)):
        assert layer[i].conv2.dilation == (2, 2)
    x = torch.randn(1, 64, 56, 56)
    x_out = layer(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])

    # Test ResLayer of 3 Bottleneck with dilation=2, contract_dilation=True
    layer = ResLayer(Bottleneck, 64, 16, 3, dilation=2, contract_dilation=True)
    assert layer[0].conv2.dilation == (1, 1)
    for i in range(1, len(layer)):
        assert layer[i].conv2.dilation == (2, 2)
    x = torch.randn(1, 64, 56, 56)
    x_out = layer(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])

    # Test ResLayer of 3 Bottleneck with dilation=2, multi_grid
    layer = ResLayer(Bottleneck, 64, 16, 3, dilation=2, multi_grid=(1, 2, 4))
    assert layer[0].conv2.dilation == (1, 1)
    assert layer[1].conv2.dilation == (2, 2)
    assert layer[2].conv2.dilation == (4, 4)
    x = torch.randn(1, 64, 56, 56)
    x_out = layer(x)
    assert x_out.shape == torch.Size([1, 64, 56, 56])


def test_resnet_backbone():
    """Test resnet backbone."""
    with pytest.raises(KeyError):
        # ResNet depth should be in [18, 34, 50, 101, 152]
        ResNet(20)

    with pytest.raises(AssertionError):
        # In ResNet: 1 <= num_stages <= 4
        ResNet(50, num_stages=0)

    with pytest.raises(AssertionError):
        # len(stage_with_dcn) == num_stages
        dcn = dict(type='DCN', deform_groups=1, fallback_on_stride=False)
        ResNet(50, dcn=dcn, stage_with_dcn=(True, ))

    with pytest.raises(AssertionError):
        # len(stage_with_plugin) == num_stages
        plugins = [
            dict(
                cfg=dict(type='ContextBlock', ratio=1. / 16),
                stages=(False, True, True),
                position='after_conv3')
        ]
        ResNet(50, plugins=plugins)

    with pytest.raises(AssertionError):
        # In ResNet: 1 <= num_stages <= 4
        ResNet(18, num_stages=5)

    with pytest.raises(AssertionError):
        # len(strides) == len(dilations) == num_stages
        ResNet(18, strides=(1, ), dilations=(1, 1), num_stages=3)

    with pytest.raises(TypeError):
        # pretrained must be a string path
        model = ResNet(18, pretrained=0)
        model.init_weights()

    with pytest.raises(AssertionError):
        # Style must be in ['pytorch', 'caffe']
        ResNet(50, style='tensorflow')

    # Test ResNet18 norm_eval=True
    model = ResNet(18, norm_eval=True)
    model.init_weights()
    model.train()
    assert check_norm_state(model.modules(), False)

    # Test ResNet18 with torchvision pretrained weight
    model = ResNet(
        depth=18, norm_eval=True, pretrained='torchvision://resnet18')
    model.init_weights()
    model.train()
    assert check_norm_state(model.modules(), False)

    # Test ResNet18 with first stage frozen
    frozen_stages = 1
    model = ResNet(18, frozen_stages=frozen_stages)
    model.init_weights()
    model.train()
    assert model.norm1.training is False
    for layer in [model.conv1, model.norm1]:
        for param in layer.parameters():
            assert param.requires_grad is False
    for i in range(1, frozen_stages + 1):
        layer = getattr(model, f'layer{i}')
        for mod in layer.modules():
            if isinstance(mod, _BatchNorm):
                assert mod.training is False
        for param in layer.parameters():
            assert param.requires_grad is False

    # Test ResNet18V1d with first stage frozen
    model = ResNetV1d(depth=18, frozen_stages=frozen_stages)
    assert len(model.stem) == 9
    model.init_weights()
    model.train()
    check_norm_state(model.stem, False)
    for param in model.stem.parameters():
        assert param.requires_grad is False
    for i in range(1, frozen_stages + 1):
        layer = getattr(model, f'layer{i}')
        for mod in layer.modules():
            if isinstance(mod, _BatchNorm):
                assert mod.training is False
        for param in layer.parameters():
            assert param.requires_grad is False

    # Test ResNet18 forward
    model = ResNet(18)
    model.init_weights()
    model.train()

    imgs = torch.randn(1, 3, 224, 224)
    feat = model(imgs)
    assert len(feat) == 4
    assert feat[0].shape == torch.Size([1, 64, 56, 56])
    assert feat[1].shape == torch.Size([1, 128, 28, 28])
    assert feat[2].shape == torch.Size([1, 256, 14, 14])
    assert feat[3].shape == torch.Size([1, 512, 7, 7])

    # Test ResNet18 with BatchNorm forward
    model = ResNet(18)
    for m in model.modules():
        if is_norm(m):
            assert isinstance(m, _BatchNorm)
    model.init_weights()
    model.train()

    imgs = torch.randn(1, 3, 224, 224)
    feat = model(imgs)
    assert len(feat) == 4
    assert feat[0].shape == torch.Size([1, 64, 56, 56])
    assert feat[1].shape == torch.Size([1, 128, 28, 28])
    assert feat[2].shape == torch.Size([1, 256, 14, 14])
    assert feat[3].shape == torch.Size([1, 512, 7, 7])

    # Test ResNet18 with layers 1, 2, 3 out forward
    model = ResNet(18, out_indices=(0, 1, 2))
    model.init_weights()
    model.train()

    imgs = torch.randn(1, 3, 112, 112)
    feat = model(imgs)
    assert len(feat) == 3
    assert feat[0].shape == torch.Size([1, 64, 28, 28])
    assert feat[1].shape == torch.Size([1, 128, 14, 14])
    assert feat[2].shape == torch.Size([1, 256, 7, 7])

    # Test ResNet18 with checkpoint forward
    model = ResNet(18, with_cp=True)
    for m in model.modules():
        if is_block(m):
            assert m.with_cp
    model.init_weights()
    model.train()

    imgs = torch.randn(1, 3, 224, 224)
    feat = model(imgs)
    assert len(feat) == 4
    assert feat[0].shape == torch.Size([1, 64, 56, 56])
    assert feat[1].shape == torch.Size([1, 128, 28, 28])
    assert feat[2].shape == torch.Size([1, 256, 14, 14])
    assert feat[3].shape == torch.Size([1, 512, 7, 7])

    # Test ResNet18 with checkpoint forward
    model = ResNet(18, with_cp=True)
    for m in model.modules():
        if is_block(m):
            assert m.with_cp
    model.init_weights()
    model.train()

    imgs = torch.randn(1, 3, 224, 224)
    feat = model(imgs)
    assert len(feat) == 4
    assert feat[0].shape == torch.Size([1, 64, 56, 56])
    assert feat[1].shape == torch.Size([1, 128, 28, 28])
    assert feat[2].shape == torch.Size([1, 256, 14, 14])
    assert feat[3].shape == torch.Size([1, 512, 7, 7])

    # Test ResNet18 with GroupNorm forward
    model = ResNet(
        18, norm_cfg=dict(type='GN', num_groups=32, requires_grad=True))
    for m in model.modules():
        if is_norm(m):
            assert isinstance(m, GroupNorm)
    model.init_weights()
    model.train()

    imgs = torch.randn(1, 3, 224, 224)
    feat = model(imgs)
    assert len(feat) == 4
    assert feat[0].shape == torch.Size([1, 64, 56, 56])
    assert feat[1].shape == torch.Size([1, 128, 28, 28])
    assert feat[2].shape == torch.Size([1, 256, 14, 14])
    assert feat[3].shape == torch.Size([1, 512, 7, 7])

    # Test ResNet50 with 1 GeneralizedAttention after conv2, 1 NonLocal2d
    # after conv2, 1 ContextBlock after conv3 in layers 2, 3, 4
    plugins = [
        dict(
            cfg=dict(
                type='GeneralizedAttention',
                spatial_range=-1,
                num_heads=8,
                attention_type='0010',
                kv_stride=2),
            stages=(False, True, True, True),
            position='after_conv2'),
        dict(cfg=dict(type='NonLocal2d'), position='after_conv2'),
        dict(
            cfg=dict(type='ContextBlock', ratio=1. / 16),
            stages=(False, True, True, False),
            position='after_conv3')
    ]
    model = ResNet(50, plugins=plugins)
    for m in model.layer1.modules():
        if is_block(m):
            assert not hasattr(m, 'context_block')
            assert not hasattr(m, 'gen_attention_block')
            assert m.nonlocal_block.in_channels == 64
    for m in model.layer2.modules():
        if is_block(m):
            assert m.nonlocal_block.in_channels == 128
            assert m.gen_attention_block.in_channels == 128
            assert m.context_block.in_channels == 512

    for m in model.layer3.modules():
        if is_block(m):
            assert m.nonlocal_block.in_channels == 256
            assert m.gen_attention_block.in_channels == 256
            assert m.context_block.in_channels == 1024

    for m in model.layer4.modules():
        if is_block(m):
            assert m.nonlocal_block.in_channels == 512
            assert m.gen_attention_block.in_channels == 512
            assert not hasattr(m, 'context_block')
    model.init_weights()
    model.train()

    imgs = torch.randn(1, 3, 224, 224)
    feat = model(imgs)
    assert len(feat) == 4
    assert feat[0].shape == torch.Size([1, 256, 56, 56])
    assert feat[1].shape == torch.Size([1, 512, 28, 28])
    assert feat[2].shape == torch.Size([1, 1024, 14, 14])
    assert feat[3].shape == torch.Size([1, 2048, 7, 7])

    # Test ResNet50 with 1 ContextBlock after conv2, 1 ContextBlock after
    # conv3 in layers 2, 3, 4
    plugins = [
        dict(
            cfg=dict(type='ContextBlock', ratio=1. / 16, postfix=1),
            stages=(False, True, True, False),
            position='after_conv3'),
        dict(
            cfg=dict(type='ContextBlock', ratio=1. / 16, postfix=2),
            stages=(False, True, True, False),
            position='after_conv3')
    ]

    model = ResNet(50, plugins=plugins)
    for m in model.layer1.modules():
        if is_block(m):
            assert not hasattr(m, 'context_block')
            assert not hasattr(m, 'context_block1')
            assert not hasattr(m, 'context_block2')
    for m in model.layer2.modules():
        if is_block(m):
            assert not hasattr(m, 'context_block')
            assert m.context_block1.in_channels == 512
            assert m.context_block2.in_channels == 512

    for m in model.layer3.modules():
        if is_block(m):
            assert not hasattr(m, 'context_block')
            assert m.context_block1.in_channels == 1024
            assert m.context_block2.in_channels == 1024

    for m in model.layer4.modules():
        if is_block(m):
            assert not hasattr(m, 'context_block')
            assert not hasattr(m, 'context_block1')
            assert not hasattr(m, 'context_block2')
    model.init_weights()
    model.train()

    imgs = torch.randn(1, 3, 224, 224)
    feat = model(imgs)
    assert len(feat) == 4
    assert feat[0].shape == torch.Size([1, 256, 56, 56])
    assert feat[1].shape == torch.Size([1, 512, 28, 28])
    assert feat[2].shape == torch.Size([1, 1024, 14, 14])
    assert feat[3].shape == torch.Size([1, 2048, 7, 7])

    # Test ResNet18 zero initialization of residual
    model = ResNet(18, zero_init_residual=True)
    model.init_weights()
    for m in model.modules():
        if isinstance(m, Bottleneck):
            assert all_zeros(m.norm3)
        elif isinstance(m, BasicBlock):
            assert all_zeros(m.norm2)
    model.train()

    imgs = torch.randn(1, 3, 224, 224)
    feat = model(imgs)
    assert len(feat) == 4
    assert feat[0].shape == torch.Size([1, 64, 56, 56])
    assert feat[1].shape == torch.Size([1, 128, 28, 28])
    assert feat[2].shape == torch.Size([1, 256, 14, 14])
    assert feat[3].shape == torch.Size([1, 512, 7, 7])

    # Test ResNetV1d forward
    model = ResNetV1d(depth=18)
    model.init_weights()
    model.train()

    imgs = torch.randn(1, 3, 224, 224)
    feat = model(imgs)
    assert len(feat) == 4
    assert feat[0].shape == torch.Size([1, 64, 56, 56])
    assert feat[1].shape == torch.Size([1, 128, 28, 28])
    assert feat[2].shape == torch.Size([1, 256, 14, 14])
    assert feat[3].shape == torch.Size([1, 512, 7, 7])
