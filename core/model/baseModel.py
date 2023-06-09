#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/4/25 20:22
# @Author  : Fuhx
# @File    : baseModel.py
# @Brief   :
# @Version : 0.1


import torch
import torch.nn as nn


class ConcatLayer(nn.Module):
    """docstring for Concat_Layer"""

    def __init__(self, layer_name, config):
        super().__init__()
        self.layer_name = layer_name
        self.mode = config['mode']
        self.layers = config['layers']

    def forward(self, feats):
        feat = [feats[i] for i in self.layers]
        if self.mode == 'cat':
            feats.update({self.layer_name: torch.cat(feat, dim=1)})
        elif self.mode == 'avg':
            feats.update({self.layer_name: torch.mean(torch.cat(feat, dim=1), dim=1, keepdim=True)})
        elif self.mode == 'batch':
            feats.update({self.layer_name: torch.cat(feat, dim=0)})
        return feats


class ConvBlock(nn.Module):
    """docstring for Conv_Block"""

    def __init__(self, layer_name, config):
        super().__init__()
        self.layer_name = layer_name
        self.reuse_times = config['reuse_times']
        self.use_residual = config['use_residual']
        self.use_bn = config['use_bn']
        self.use_activation = config['use_activation']
        self.parameters = config['parameters']
        self.out_channels = self.parameters['out_channels']
        self.conv = nn.Conv2d(**self.parameters)
        if self.use_bn:
            self.bn = nn.BatchNorm2d(self.out_channels)
        if self.use_activation is not None:
            self.activation = eval('nn.' + self.use_activation)()

    def forward(self, feats):
        x = feats[[i for i in feats][-1]]  # 取最后一个，feats会保存每一层的输出
        feat = self.conv(x)

        if self.use_bn:
            feat = self.bn(feat)

        if self.use_activation is not None:
            feat = self.activation(feat + x) if self.use_residual else self.activation(feat)
        elif self.use_activation is None and self.use_residual:
            feat = feat + x
        elif self.use_activation is None and not self.use_residual:
            feat = feat

        if self.use_activation == 'Tanh':
            feat = feat / 2 + 0.5
            feat = 0.999 * feat

        feats.update({self.layer_name: feat})
        return feats


class LinearBlock(nn.Module):
    def __init__(self, layer_name, config):
        super().__init__()
        self.layer_name = layer_name
        self.pre_flatten = config['pre_flatten']
        self.use_activation = config['use_activation']
        self.parameters = config['parameters']
        self.flatten = nn.Flatten()
        self.linear = nn.Linear(**self.parameters)

        if self.use_activation is not None:
            self.activation = eval('nn.' + self.use_activation)()

    def forward(self, feats):
        x = feats[[i for i in feats][-1]]  # 取最后一个，feats会保存每一层的输出
        feat = self.flatten(x) if self.pre_flatten else x
        feat = self.linear(feat)
        if self.use_activation is not None:
            feat = self.activation(feat)
            if self.use_activation == 'Tanh':
                feat = feat / 2 + 0.5
                feat = 0.999 * feat
        feats.update({self.layer_name: feat})
        return feats


class Model(nn.Module):
    """docstring for Model"""

    def __init__(self, config):
        super(Model, self).__init__()
        self.model_names = {i: {} for i in config}
        self.models = nn.ModuleDict({})
        model_dict = nn.ModuleDict({})
        for model_name in self.model_names:
            self.layer_names = {i: {} for i in config[model_name]}
            for layer_name in self.layer_names:
                layer_type = config[model_name][layer_name]['type']
                layer_config = config[model_name][layer_name]
                if layer_type == 'conv':
                    if layer_config['same_weight']:
                        block = ConvBlock(layer_name, layer_config)
                        layer = {'block_' + str(i): block for i in range(layer_config['reuse_times'])}
                    else:
                        layer = {'block_' + str(i): ConvBlock(layer_name, layer_config)
                                 for i in range(layer_config['reuse_times'])}
                if layer_type == 'concat':
                    layer = {layer_name: ConcatLayer(layer_name, layer_config)}
                if layer_type == 'linear':
                    layer = {layer_name: LinearBlock(layer_name, layer_config)}

                self.layer_names.update({layer_name: [i for i in layer]})
                model_dict.update({layer_name: nn.ModuleDict(layer)})
            self.model_names.update({model_name: self.layer_names})
            # {'Generator_1': {'concat_1': ['concat_1'],
            # 'layer_1': ['block_0'], 'concat_2': ['concat_2'], 'layer_2': ['block_0'], 'concat_3': ['concat_3'],
            # 'layer_3': ['block_0']}}
            self.models.update({model_name: nn.ModuleDict(model_dict)})

    def forward(self, feats):
        for model_name in self.model_names:
            for layer_name in self.model_names[model_name]:
                for block_name in self.model_names[model_name][layer_name]:
                    feats = self.models[model_name][layer_name][block_name](feats)
        return feats
