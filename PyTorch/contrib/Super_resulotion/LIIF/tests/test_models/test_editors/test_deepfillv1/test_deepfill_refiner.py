# Copyright (c) OpenMMLab. All rights reserved.
import torch
import torch_sdaa

from mmagic.models.editors import (ContextualAttentionNeck, DeepFillDecoder,
                                   DeepFillEncoder, DeepFillRefiner,
                                   GLDilationNeck)


def test_deepfill_refiner():
    refiner = DeepFillRefiner()

    x = torch.rand((2, 5, 256, 256))
    mask = x.new_ones((2, 1, 256, 256))
    mask[..., 30:100, 40:100] = 0.
    res, offset = refiner(x, mask)
    assert res.shape == (2, 3, 256, 256)
    assert offset.shape == (2, 32, 32, 32, 32)

    # check model architecture
    assert isinstance(refiner.encoder_attention, DeepFillEncoder)
    assert isinstance(refiner.encoder_conv, DeepFillEncoder)
    assert isinstance(refiner.contextual_attention_neck,
                      ContextualAttentionNeck)
    assert isinstance(refiner.decoder, DeepFillDecoder)
    assert isinstance(refiner.dilation_neck, GLDilationNeck)

    if torch.sdaa.is_available():
        refiner = DeepFillRefiner().sdaa()

        x = torch.rand((2, 5, 256, 256)).sdaa()
        res, offset = refiner(x, mask.sdaa())
        assert res.shape == (2, 3, 256, 256)
        assert offset.shape == (2, 32, 32, 32, 32)

        # check model architecture
        assert isinstance(refiner.encoder_attention, DeepFillEncoder)
        assert isinstance(refiner.encoder_conv, DeepFillEncoder)
        assert isinstance(refiner.contextual_attention_neck,
                          ContextualAttentionNeck)
        assert isinstance(refiner.decoder, DeepFillDecoder)
        assert isinstance(refiner.dilation_neck, GLDilationNeck)


def teardown_module():
    import gc
    gc.collect()
    globals().clear()
    locals().clear()
