import subprocess
import os
import numpy as np
import shutil
import toml
import pandas as pd
import uuid
import time

from surrogate_optimization import BayesianOptimizer

"""
провести эксперимент с 4мя AF функциями: UCB, EI, TS, DYCORS
параметры X:
- NUM_THREADS
- DEFAULT_TICKS_PER_SLOT
- RECV_BATCH_MAX_CPU
- ITER_BATCH_SIZE
- DEFAULT_HASHES_PER_SECOND
- DEFAULT_TICKS_PER_SECOND
y:
AVERAGE_TPS_BENCH1
начальный датасет: data/af_train_100.csv (копия data/out_slhc_design_train_100.csv)
цикл из 100 точек, каждая новая точка добавляется в датасет af_train_<af_name>.csv (копия data/af_train.csv)
результат: 4 файла на 200 точек af_train_<af_name>.csv
"""

SOLANA_PARAMS = [
    "NUM_THREADS",
    "DEFAULT_TICKS_PER_SLOT",
    "RECV_BATCH_MAX_CPU",
    "ITER_BATCH_SIZE",
    "DEFAULT_HASHES_PER_SECOND",
    "DEFAULT_TICKS_PER_SECOND"
]

FACTORY_PATH = "/Users/19846310/personal/GBC-AI/factory/"
AF_TYPE = os.getenv("AF_TYPE", "EI")

current_env = os.environ.copy()
current_dir = os.path.dirname(os.path.realpath(__file__))



def find_outter_keys(config):
    out_in_keys = {}
    # find outter keys to get access to inner dicts
    for outter in config.keys():
        inner = list(config[outter].keys())
        for p in SOLANA_PARAMS:
            if p in inner:
                out_in_keys[p] = outter
    return out_in_keys

# parse saved logs to get Average TPS and Drop Rate
def parse_logs(file_name: str):
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
    return results


# gets UID of chain and calls stop_chain.py
def chain_stop(chain_uid: str, factory_path: str):
    chain_stop = subprocess.run("python3 destroy_chain.py -u " + chain_uid, shell=True, cwd=factory_path)
    if not chain_stop.returncode:
        print("Chain %s successfully stopped" % chain_uid)
    else:
        print(chain_stop.stderr)


def blackbox(X: pd.Series, factory_path: str, delay: int = 80) -> pd.Series:
    """
    Blackbox experiment:
    - loads and saves config
    - stop chains in chains folder
    - starts blockchain
    - launchs transactions with docker after T seconds, records results in file
    - stops blockchain
    """
    # check that config.toml exists
    config_path = os.path.join(factory_path, "config.toml")
    assert (os.path.isfile(config_path), f"{config_path} does not exist")
    config = toml.load(config_path)
    outer_keys = find_outter_keys(config)  # to set SOLANA_PARAMS for experiments

    # backup config
    backup_config_path = config_path + ".backup"
    shutil.copyfile(config_path, backup_config_path)

    # create dir for experiment outputs
    output_dir = os.path.join(current_dir, "output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # create Series with experiments results
    index_names = SOLANA_PARAMS + [
        "AVERAGE_TPS_BENCH1",
        "AVERAGE_DROPRATE_BENCH1",
    ]
    result_series = pd.Series(index=index_names)

    # set SOLANA_PARAMS
    with open(config_path, "w") as config_file:
        for inn, out in outer_keys.items():
            config[out][inn] = int(X[inn])
        print(f"new params: {X}")
        # save updated version
        toml.dump(config, config_file)

    result_series.loc[SOLANA_PARAMS] = X

    print(f"Starting blockchain...")
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

    # add them to Series
    result_series["AVERAGE_TPS_BENCH1"] = results["average_tps"]
    result_series["AVERAGE_DROPRATE_BENCH1"] = results["drop_rate"]

    print("End transactions")
    chain_stop(chain_uid, factory_path)

    return result_series

if __name__ == "__main__":
    feature_cols = ['NUM_THREADS', 'DEFAULT_TICKS_PER_SLOT', 'RECV_BATCH_MAX_CPU',
                    'ITER_BATCH_SIZE', 'DEFAULT_HASHES_PER_SECOND', 'DEFAULT_TICKS_PER_SECOND']
    target_col = ["AVERAGE_TPS_BENCH1"]

    # lower and upper bound for X candidates search
    lb = np.array([3, 850, 850, 53, 1700000, 136])
    ub = np.array([5, 1150, 1150, 73, 2300000, 184])

    # required length of dataset
    N = 100 + 100

    # AF optimization
    af_type = AF_TYPE

    data_path = f"af_train_{af_type}.csv"

    # dataset for training: af_train_<af_type>.csv if exists, default starting dataset if not
    if os.path.isfile(data_path):
        af_train = pd.read_csv(data_path)
    else:
        af_train = pd.read_csv(os.path.join("data", "af_train_100.csv"))

    n = len(af_train)
    if n >= N:
        print(f"{af_type} training complete, exiting...")
        exit(0)

    for i in range(n, N):
        print(f"Generating {i+1} candidate...")
        # X, y for trainig
        X = af_train[feature_cols].values
        y = af_train[target_col].values

        botorch_optim = BayesianOptimizer(lower_bound=lb, upper_bound=ub,is_scaler=True)
        if af_type == "EI":
            candidate = botorch_optim.optimize_EI(X, y)
        elif af_type == "TS":
            candidate = botorch_optim.optimize_TS(X, y)
        elif af_type == "UCB":
            candidate = botorch_optim.optimize_UCB(X, y)
        elif af_type == "DYCORS":
            candidate = botorch_optim.optimize_DYCORS(X, y)
        else:
            print(f"{af_type} optimization not implemented.")
            exit(1)
        print(f"{af_type} candidate {candidate}")
        candidate_series = pd.Series(data=candidate, index=feature_cols)

        print(f"Calculating blackbox for candidate {i+1}...")
        result_series = blackbox(candidate_series, FACTORY_PATH)
        print(f"Resulting {target_col}: {result_series[target_col]}")

        print(f"Saving results to {data_path}...")
        af_train.loc[i] = result_series
        af_train.to_csv(data_path, index=False)
