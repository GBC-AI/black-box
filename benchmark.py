import subprocess
import os
import numpy as np
import pandas as pd
import uuid
import time
import re

"""
В чёрном ящике должен быть параметр, задающий время ожидания в секундах между запуском системы и началом benchmark-a.
Надо модифицировать ящик так, чтобы эта задержка осталась, но после первого бенчмарка мы без задержки запускали второй.
И только после отработки второго тушили машины. На выходе ящика будет два результата -- первого и второго бенчмарка.

Хочется провести такой эксперимент. Для дефолтных параметров конфигурации и для задержек от 0 сек до 90 сек с шагом в 10 сек производим по 10 пусков чёрного ящика.
В результате получится 200 значений tps.

На полученных данных посчитаем перестановочные тесты и поймём, с какой задержкой будем работать дальше.
"""

current_env = os.environ.copy()
current_dir = os.path.dirname(os.path.realpath(__file__))


# parse saved logs to get Average TPS and Drop Rate
def parse_logs(file_name):
    with open(file_name) as f:
        contents = f.readlines()
    results = {}
    for line in contents:
        if "Average TPS:" in line:
            tmp = line.split(" ")
            results["average_tps"] = float(tmp[-1].rstrip())
        if "drop rate:" in line:
            tmp = line.split(" ")
            results["drop_rate"] = float(tmp[-1].rstrip())
        for type_time, match_obj in {type_time: re.search(f"{type_time}\s+(.*)", line) for type_time in ["real", "user", "sys"]}.items():
            if match_obj:
                time_str = match_obj.group(1)  # 1m30.734s is 90743ms
                time_split = time_str.split("m")
                results[f"{type_time}_time_rate"] = int((float(time_split[0]) * 60 + float(time_split[1].strip("s"))) * 1000)
    return results


# gets UID of chain and calls stop_chain.py
def chain_stop(chain_uid: str, factory_path: str):
    chain_stop = subprocess.run("python3 stop_chain.py -u " + chain_uid, shell=True, cwd=factory_path)
    if not chain_stop.returncode:
        print("Chain %s successfully stopped" % chain_uid)
    else:
        print(chain_stop.stderr)


def blackbox(delays: list, delay_iters: int, factory_path: str, results_path: str):
    """
    Blackbox experiment:
    - loads and saves config
    - stop chains in chains folder
    repeat 10 times for each delay in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]:
    - starts blockchain
    - launchs transactions with docker after T seconds, records results in file
    - launchs transations with docker immediately, records results in file
    - stops blockchain
    """
    # check that config.toml exists
    config_path = os.path.join(factory_path, "config.toml")
    assert (os.path.isfile(config_path), f"{config_path} does not exist")

    # create dir for experiment outputs
    output_dir = os.path.join(current_dir, "output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # create Dataframe with experiments results
    column_names = [
        "DELAY",
        "ITER",
        "AVERAGE_TPS_BENCH1",
        "AVERAGE_DROPRATE_BENCH1",
        "AVERAGE_TPS_BENCH2",
        "AVERAGE_DROPRATE_BENCH2",
        "REAL_TIME_RATE_BENCH1",
        "USER_TIME_RATE_BENCH1",
        "SYS_TIME_RATE_BENCH1",
        "REAL_TIME_RATE_BENCH2",
        "USER_TIME_RATE_BENCH2",
        "SYS_TIME_RATE_BENCH2"
    ]
    df = pd.DataFrame(columns=column_names)
    df["DELAY"] = pd.Series(np.repeat(delays, delay_iters))
    df["ITER"] = pd.Series(np.tile(range(delay_iters), len(delays)))

    for num_delay, delay in enumerate(delays):
        for k in range(delay_iters):
            # index to save results at in Dataframe
            idx = delay_iters * num_delay + k

            print("Starting blockchain...")
            chain_uid = uuid.uuid4().hex
            subprocess.run(
                f"python3 start_chain.py -v=3 -i=t2.2xlarge -e=test_blockchain -c=config.toml -r=us-east-1 -u {chain_uid}",
                shell=True,
                env=current_env,
                cwd=factory_path,
            )
            get_chain_ip = subprocess.run(
                f"python3 get_public_ip.py -u {chain_uid}",
                capture_output=True,
                shell=True,
                text=True,
                env=current_env,
                cwd=factory_path,
            )
            public_ip = get_chain_ip.stdout.split(" ")[-1][:-1]
            output_file = os.path.join(output_dir, f"{chain_uid}.txt")

            print(f"Time delay of {delay} sec...")
            time.sleep(delay)

            # benchmark 1
            print(f"Starting benchmark 1 after delay {delay} sec...")
            with open(output_file, "w") as out_file:
                out_file.write(f"BENCHMARK 1, delay {delay} sec \n")
                subprocess.run(
                    'docker run -it --rm --net=host -e NDEBUG=1 timofeykulakov/solana_simulations:1.0 bash -c "time ./multinode-demo/bench-tps.sh --entrypoint '
                    + public_ip
                    + ":8001 --faucet "
                    + public_ip
                    + ':9900 --duration 5 --tx_count 50 "',
                    shell=True,
                    text=True,
                    stdout=out_file,
                    stderr=out_file
                )
            # get results from logs
            results = parse_logs(output_file)
            print(results)
            # add them to dataframe
            df.at[idx, "AVERAGE_TPS_BENCH1"] = results["average_tps"]
            df.at[idx, "AVERAGE_DROPRATE_BENCH1"] = results["drop_rate"]
            df.at[idx, "REAL_TIME_RATE_BENCH1"] = results["real_time_rate"]
            df.at[idx, "USER_TIME_RATE_BENCH1"] = results["user_time_rate"]
            df.at[idx, "SYS_TIME_RATE_BENCH1"] = results["sys_time_rate"]

            # benchmark 2
            print("Starting benchmark 2 without delay...")
            with open(output_file, "a") as out_file:
                out_file.write("BENCHMARK 2, no delay \n")
                subprocess.run(
                    'docker run -it --rm --net=host -e NDEBUG=1 timofeykulakov/solana_simulations:1.0 bash -c "time ./multinode-demo/bench-tps.sh --entrypoint '
                    + public_ip
                    + ":8001 --faucet "
                    + public_ip
                    + ':9900 --duration 5 --tx_count 50 "',
                    shell=True,
                    text=True,
                    stdout=out_file,
                    stderr=out_file
                )
            # get results from logs
            results = parse_logs(output_file)
            print(results)
            # add them to dataframe
            df.at[idx, "AVERAGE_TPS_BENCH2"] = results["average_tps"]
            df.at[idx, "AVERAGE_DROPRATE_BENCH2"] = results["drop_rate"]
            df.at[idx, "REAL_TIME_RATE_BENCH2"] = results["real_time_rate"]
            df.at[idx, "USER_TIME_RATE_BENCH2"] = results["user_time_rate"]
            df.at[idx, "SYS_TIME_RATE_BENCH2"] = results["sys_time_rate"]

            print("End transactions")
            chain_stop(chain_uid, factory_path)

            # save current state to csv
            df.to_csv(results_path, index=False)


blackbox(
    delays=np.linspace(0, 90, 10),
    delay_iters=10,
    factory_path="/Users/19846310/personal/GBC-AI/factory/",
    results_path="/Users/19846310/personal/GBC-AI/black-box/out.csv",
)
