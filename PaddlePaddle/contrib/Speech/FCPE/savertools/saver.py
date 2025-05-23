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
import os
import time
import yaml
import datetime
import paddle
import matplotlib.pyplot as plt
plt.switch_backend('agg')
from . import utils
import numpy as np
from visualdl import LogWriter as SummaryWriter


class Saver(object):
    def __init__(
            self,
            args,
            initial_global_step=-1):

        self.expdir = args.env.expdir
        self.sample_rate = args.mel.sampling_rate

        # cold start
        self.global_step = initial_global_step
        self.init_time = time.time()
        self.last_time = time.time()

        # makedirs
        os.makedirs(self.expdir, exist_ok=True)

        # path
        self.path_log_info = os.path.join(self.expdir, 'log_info.txt')

        # ckpt
        os.makedirs(self.expdir, exist_ok=True)

        # writer
        self.writer = SummaryWriter(os.path.join(self.expdir, 'logs'))

        # save config
        path_config = os.path.join(self.expdir, 'config.yaml')
        with open(path_config, "w") as out_config:
            yaml.dump(dict(args), out_config)

        # save spk_emb_dict
        if args.model.use_speaker_encoder:
            import numpy as np
            path_from_spk_emb_dict = os.path.join(args.data.train_path, 'spk_emb_dict.npy')
            path_save_spk_emb_dict = os.path.join(self.expdir, 'spk_emb_dict.npy')
            temp_spk_emb_dict = np.load(path_from_spk_emb_dict, allow_pickle=True).item()
            np.save(path_save_spk_emb_dict, temp_spk_emb_dict)

    def log_info(self, msg):
        '''log method'''
        if isinstance(msg, dict):
            msg_list = []
            for k, v in msg.items():
                tmp_str = ''
                if isinstance(v, int):
                    tmp_str = '{}: {:,}'.format(k, v)
                else:
                    tmp_str = '{}: {}'.format(k, v)

                msg_list.append(tmp_str)
            msg_str = '\n'.join(msg_list)
        else:
            msg_str = msg

        # dsplay
        print(msg_str)

        # save
        with open(self.path_log_info, 'a') as fp:
            fp.write(msg_str + '\n')

    def log_value(self, dict):
        for k, v in dict.items():
            self.writer.add_scalar(k, v, self.global_step)

    def log_spec(self, name, spec, spec_out, vmin=-14, vmax=3.5):
        spec_cat = paddle.concat([(spec_out - spec).abs() + vmin, spec, spec_out], -1)
        spec = spec_cat[0]
        if isinstance(spec, paddle.Tensor):
            spec = spec.cpu().numpy()
        fig = plt.figure(figsize=(12, 9))
        plt.pcolor(spec.T, vmin=vmin, vmax=vmax)
        plt.tight_layout()
        self.writer.add_figure(name, fig, self.global_step)

    def log_audio(self, dict):
        for k, v in dict.items():
            self.writer.add_audio(k, v, global_step=self.global_step, sample_rate=self.sample_rate)

    def log_f0(self, name, f0_pr, f0_gt, inuv=False):
        #f0_gt = (1 + f0_gt / 700).log()
        name = (name + '_f0_inuv') if inuv else (name + '_f0')
        f0_pr = f0_pr.squeeze().cpu().numpy()
        f0_gt = f0_gt.squeeze().cpu().numpy()
        if inuv:
            uv = f0_pr == 0
            if len(f0_pr[~uv]) > 0:
                f0_pr[uv] = np.interp(np.where(uv)[0], np.where(~uv)[0], f0_pr[~uv])
            uv = f0_gt == 0
            if len(f0_gt[~uv]) > 0:
                f0_gt[uv] = np.interp(np.where(uv)[0], np.where(~uv)[0], f0_gt[~uv])
        fig = plt.figure()
        plt.plot(f0_gt, color='b', linestyle='-')
        plt.plot(f0_pr, color='r', linestyle='-')
        self.writer.add_figure(name, fig, self.global_step)

    def get_interval_time(self, update=True):
        cur_time = time.time()
        time_interval = cur_time - self.last_time
        if update:
            self.last_time = cur_time
        return time_interval

    def get_total_time(self, to_str=True):
        total_time = time.time() - self.init_time
        if to_str:
            total_time = str(datetime.timedelta(
                seconds=total_time))[:-5]
        return total_time

    def save_model(
            self,
            model,
            optimizer,
            name='model',
            postfix='',
            to_json=False,
            config_dict=None):
        # path
        if postfix:
            postfix = '_' + postfix
        path_pt = os.path.join(
            self.expdir, name + postfix + '.pdparams')

        # check
        print(' [*] model checkpoint saved: {}'.format(path_pt))

        # save
        if optimizer is not None:
            paddle.save({
                'global_step': self.global_step,
                'model': model.state_dict(),
                'optimizer': optimizer.state_dict(),
                'config_dict': config_dict
            }, path_pt)
        else:
            paddle.save({
                'global_step': self.global_step,
                'model': model.state_dict(),
                'config_dict': config_dict
            }, path_pt)

        # to json
        if to_json:
            path_json = os.path.join(
                self.expdir, name + '.json')
            utils.to_json(path_pt, path_json)

    def delete_model(self, name='model', postfix=''):
        # path
        if postfix:
            postfix = '_' + postfix
        path_pt = os.path.join(
            self.expdir, name + postfix + '.pdparams')

        # delete
        if os.path.exists(path_pt):
            os.remove(path_pt)
            print(' [*] model checkpoint deleted: {}'.format(path_pt))

    def global_step_increment(self):
        self.global_step += 1
