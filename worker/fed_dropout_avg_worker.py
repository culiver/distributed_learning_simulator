""" FedDropoutAvg: Generalizable federated learning for histopathology image classification (https://arxiv.org/pdf/2111.13230.pdf) """
import torch
from cyy_naive_lib.log import get_logger

from .fed_avg_worker import FedAVGWorker


class FedDropoutAvgWorker(FedAVGWorker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__dropout_rate: float = self.config.algorithm_kwargs["dropout_rate"]
        get_logger().error("use dropout_rate %s", self.__dropout_rate)

    def _get_sent_data(self) -> dict:
        self._send_parameter_diff = False
        sent_data = super()._get_sent_data()
        parameter = sent_data["parameter"]
        total_num = 0
        send_num = 0
        for k, v in parameter.items():
            weight = torch.bernoulli(torch.full_like(v, 1 - self.__dropout_rate))
            parameter[k] = v * weight
            total_num += parameter[k].numel()
            send_num += torch.count_nonzero(parameter[k]).item()
        get_logger().error("send_num %s", send_num)
        get_logger().error("total_num %s", total_num)
        return sent_data
