# Copyright (c) OpenMMLab. All rights reserved.
import pytest
import torch
import torch_sdaa

from mmagic.models.editors.stylegan1.stylegan1_modules import (
    AdaptiveInstanceNorm, StyleConv)


class TestAdaptiveInstanceNorm:

    @classmethod
    def setup_class(cls):
        cls.in_channel = 512
        cls.style_dim = 512

    @pytest.mark.skipif(not torch.sdaa.is_available(), reason='requires sdaa')
    def test_adain_cuda(self):
        adain = AdaptiveInstanceNorm(self.in_channel, self.style_dim).sdaa()
        x = torch.randn((2, 512, 8, 8)).sdaa()
        style = torch.randn((2, 512)).sdaa()
        res = adain(x, style)

        assert res.shape == (2, 512, 8, 8)


class TestStyleConv:

    @classmethod
    def setup_class(cls):
        cls.default_cfg = dict(
            in_channels=512,
            out_channels=256,
            kernel_size=3,
            style_channels=512,
            padding=1,
            initial=False,
            blur_kernel=[1, 2, 1],
            upsample=True,
            fused=False)

    @pytest.mark.skipif(not torch.sdaa.is_available(), reason='requires sdaa')
    def test_styleconv_cuda(self):
        conv = StyleConv(**self.default_cfg).sdaa()
        input_x = torch.randn((2, 512, 32, 32)).sdaa()
        input_style1 = torch.randn((2, 512)).sdaa()
        input_style2 = torch.randn((2, 512)).sdaa()

        res = conv(input_x, input_style1, input_style2)
        assert res.shape == (2, 256, 64, 64)


def teardown_module():
    import gc
    gc.collect()
    globals().clear()
    locals().clear()
