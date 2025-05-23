# Copyright (c) OpenMMLab. All rights reserved.
from copy import deepcopy

import numpy as np
import torch
import torch_sdaa

from mmagic.evaluation.metrics import MSE


class TestPixelMetrics:

    @classmethod
    def setup_class(cls):

        mask = np.ones((32, 32, 3)) * 2
        mask[:16] *= 0
        gt = np.ones((32, 32, 3)) * 2
        data_sample = dict(gt_img=gt, mask=mask, gt_channel_order='bgr')
        cls.data_batch = [dict(data_samples=data_sample)]
        cls.predictions = [dict(pred_img=np.ones((32, 32, 3)))]

        cls.data_batch.append(
            dict(
                data_samples=dict(
                    gt_img=torch.from_numpy(gt),
                    mask=torch.from_numpy(mask),
                    img_channel_order='bgr')))
        cls.predictions.append({
            k: torch.from_numpy(deepcopy(v))
            for (k, v) in cls.predictions[0].items()
        })

        for d, p in zip(cls.data_batch, cls.predictions):
            d['output'] = p
        cls.predictions = cls.data_batch

    def test_mse(self):

        # Single MSE
        mae = MSE()
        mae.process(self.data_batch, self.predictions)
        result = mae.compute_metrics(mae.results)
        assert 'MSE' in result
        np.testing.assert_almost_equal(result['MSE'], 0.000015378700496)

        # Masked MSE
        mae = MSE(mask_key='mask', prefix='MSE')
        mae.process(self.data_batch, self.predictions)
        result = mae.compute_metrics(mae.results)
        assert 'MSE' in result
        np.testing.assert_almost_equal(result['MSE'], 0.000015378700496)


def teardown_module():
    import gc
    gc.collect()
    globals().clear()
    locals().clear()
