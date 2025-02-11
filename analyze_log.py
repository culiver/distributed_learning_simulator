import os
import re

import torch

from config import global_config as config
from config import load_config


def compute_acc(paths):
    final_test_acc = []
    worker_acc: dict = {}
    for path in paths:
        assert os.path.isfile(path)
        lines = None
        with open(path, "rt", encoding="utf8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            if config.distributed_algorithm == "sign_SGD":
                if "test loss" in line:
                    res = re.findall("[0-9.]+%", line)
                    assert len(res) == 1
                    acc = float(res[0].replace("%", ""))
                    final_test_acc.append(acc)
                    break
            elif config.distributed_algorithm in (
                "fed_obd_first_stage",
                "fed_obd_layer",
            ):
                if "test accuracy is" in line and "round " + str(config.round) in line:
                    res = re.findall("[0-9.]+%", line)
                    assert len(res) == 1
                    acc = float(res[0].replace("%", ""))
                    print(line)
                    final_test_acc.append(acc)
                    break
            else:
                if "test accuracy is" in line:
                    res = re.findall("[0-9.]+%", line)
                    assert len(res) == 1
                    acc = float(res[0].replace("%", ""))
                    print(line)
                    final_test_acc.append(acc)
                    break
        for worker_id in range(config.worker_number):
            for line in reversed(lines):
                res = re.findall(f"worker {worker_id}.*train.*accuracy", line)
                if res:
                    res = re.findall("[0-9.]+%", line)
                    assert len(res) == 1
                    acc = float(res[0].replace("%", ""))
                    if worker_id not in worker_acc:
                        worker_acc[worker_id] = []
                    worker_acc[worker_id].append(acc)
                    break
    assert len(final_test_acc) == len(paths)
    std, mean = torch.std_mean(torch.tensor(final_test_acc))
    print("test acc", mean, std)


if __name__ == "__main__":
    load_config()
    paths = os.getenv("logfiles").split(" ")
    assert paths
    compute_acc(paths)

    if config.distributed_algorithm.lower() == "fed_obd":
        total_msg = (
            config.round * config.algorithm_kwargs["random_client_number"] * 2
            + config.algorithm_kwargs["second_phase_epoch"] * config.worker_number * 2
            + config.worker_number
        )
        print("total_msg is", total_msg)

        avg_compression = []
        for path in paths:
            remain_msg = total_msg
            lines = None
            compressed_part = 0
            rnd_cnt = 0
            with open(path, "rt", encoding="utf8") as f:
                lines = f.readlines()
            stage_one = True
            for line in lines:
                if "broadcast NNABQ compression ratio" in line:
                    res = re.findall("[0-9.]+$", line)
                    assert len(res) == 1
                    broadcast_ratio = float(res[0].replace("(", "").replace(",", ""))
                    rnd_cnt += 1
                    if rnd_cnt <= config.round:
                        compressed_part += (
                            broadcast_ratio
                            * config.algorithm_kwargs["random_client_number"]
                        )
                        remain_msg -= config.algorithm_kwargs["random_client_number"]
                    else:
                        stage_one = False
                        compressed_part += broadcast_ratio * config.worker_number
                        remain_msg -= config.worker_number
                if "worker NNABQ compression ratio" in line:
                    res = re.findall("[0-9.]+$", line)
                    assert len(res) == 1
                    worker_ratio = float(res[0].replace("(", "").replace(",", ""))
                    if stage_one:
                        worker_ratio *= 1 - config.algorithm_kwargs["dropout_rate"]
                    compressed_part += worker_ratio
                    remain_msg -= 1
            print("remain_msg is", remain_msg, "path is", path)
            assert remain_msg == config.worker_number
            compressed_part += remain_msg
            avg_compression.append(compressed_part / total_msg)
        assert len(avg_compression) == len(paths)
        std, mean = torch.std_mean(torch.tensor(avg_compression))
        print("compression", mean, std)
        print("communication overhead", total_msg * mean, total_msg * std)
    elif config.distributed_algorithm.lower() == "fed_obd_sq":
        total_msg = (
            config.round * config.algorithm_kwargs["random_client_number"] * 2
            + config.algorithm_kwargs["second_phase_epoch"] * config.worker_number * 2
            + config.worker_number
        )
        print("total_msg is", total_msg)

        compression = (
            config.round
            * config.algorithm_kwargs["random_client_number"]
            * (1 - config.algorithm_kwargs["dropout_rate"])
            / 4
            + config.round * config.algorithm_kwargs["random_client_number"] / 4
            + config.algorithm_kwargs["second_phase_epoch"]
            * config.worker_number
            * 2
            / 4
            + config.worker_number
        ) / total_msg

        print("compression", compression)
        print("co", total_msg * compression)
    if config.distributed_algorithm.lower() == "fed_dropout_avg":
        total_msg = (
            config.round * config.algorithm_kwargs["random_client_number"] * 2
            + config.worker_number
        )
        print("total_msg is", total_msg)

        total_number = 0
        transfer_number: float = 0
        parameter_number = None
        avg_compression = []
        for path in paths:
            lines = None
            with open(path, "rt", encoding="utf8") as f:
                lines = f.readlines()
            for line in lines:
                if "send_num" in line:
                    res = re.findall("[0-9.]+$", line)
                    assert len(res) == 1
                    transfer_number += float(res[0])
                if "total_num" in line:
                    res = re.findall("[0-9.]+$", line)
                    assert len(res) == 1
                    parameter_number = float(res[0])
                    total_number += float(res[0])
            avg_compression.append(
                (transfer_number + config.worker_number * parameter_number)
                / (total_number + config.worker_number * parameter_number)
            )
        std, mean = torch.std_mean(torch.tensor(avg_compression))
        print("compression", mean, std)
    if config.distributed_algorithm.lower() == "afd":
        total_msg = (
            config.round * config.algorithm_kwargs["random_client_number"] * 2
            + config.worker_number
        )
        print("total_msg is", total_msg)

        total_number = 0
        transfer_number = 0
        parameter_number = None
        avg_compression = []
        for path in paths:
            lines = None
            with open(path, "rt", encoding="utf8") as f:
                lines = f.readlines()
            for line in lines:
                if "send_num" in line:
                    res = re.findall("[0-9.]+$", line)
                    assert len(res) == 1
                    transfer_number += float(res[0])
                    assert parameter_number is not None
                    total_number += parameter_number
                if "parameter number is" in line:
                    res = re.findall("[0-9.]+$", line)
                    assert len(res) == 1
                    parameter_number = float(res[0])
            avg_compression.append(
                (transfer_number + config.worker_number * parameter_number)
                / (total_number + config.worker_number * parameter_number)
            )
        std, mean = torch.std_mean(torch.tensor(avg_compression))
        print("compression", mean, std)

    if config.distributed_algorithm.lower() == "fed_obd_first_stage":
        assert config.algorithm_kwargs["random_client_number"] is not None
        total_msg = (
            config.round * config.algorithm_kwargs["random_client_number"] * 2
            + config.worker_number
        )
        print("total_msg is", total_msg)

        avg_compression = []
        for path in paths:
            remain_msg = total_msg
            lines = None
            compressed_part = 0
            rnd_cnt = 0
            with open(path, "rt", encoding="utf8") as f:
                lines = f.readlines()
            for line in lines:
                if "switch" in line:
                    break
                if "broadcast NNABQ compression ratio" in line:
                    res = re.findall("[0-9.]+$", line)
                    assert len(res) == 1
                    broadcast_ratio = float(res[0].replace("(", "").replace(",", ""))
                    rnd_cnt += 1
                    if rnd_cnt <= config.round:
                        compressed_part += (
                            broadcast_ratio
                            * config.algorithm_kwargs["random_client_number"]
                        )
                        remain_msg -= config.algorithm_kwargs["random_client_number"]
                if "worker NNABQ compression ratio" in line:
                    res = re.findall("[0-9.]+$", line)
                    assert len(res) == 1
                    worker_ratio = float(res[0].replace("(", "").replace(",", ""))
                    worker_ratio *= 1 - config.algorithm_kwargs["dropout_rate"]
                    compressed_part += worker_ratio
                    remain_msg -= 1
            assert remain_msg == config.worker_number
            # print("remain_msg is", remain_msg, "path is", path)
            compressed_part += remain_msg
            avg_compression.append(compressed_part / total_msg)
        assert len(avg_compression) == len(paths)
        std, mean = torch.std_mean(torch.tensor(avg_compression))
        print("compression", mean, std)
        print("co", mean * total_msg, std * total_msg)
