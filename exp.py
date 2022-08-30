import subprocess
import os
import numpy as np
import pandas as pd
from pathlib import Path
import time
import toml


# location of config file for starting
config_path = '/home/ubuntu/factory/'

def get(config):
    # set blockchain params to change
    params = ['NUM_THREADS',
              'DEFAULT_TICKS_PER_SLOT',
              'ITER_BATCH_SIZE',
              'RECV_BATCH_MAX_CPU',
              'DEFAULT_HASHES_PER_SECOND',
              'DEFAULT_TICKS_PER_SECOND']
    out_in_keys = {}
    # gettin outter keys to get access to inner dicts
    for outter in config.keys():
        inner = list(config[outter].keys())
        # print(config[outter].items())
        for p in params:
            if p in inner:
                out_in_keys[p] = outter
    return out_in_keys

def weighted_Y(Y, weights={'TPS': -0.8, 'Droprate': +0.2}):
    return Y[0] * weights['TPS'] + Y[1] * weights['Droprate']

def parse_logs(file_name):
    with open(file_name) as f:
        contents = f.readlines()
    results = []
    tmp_res = [None] * 2
    for line in contents:
        if "Average TPS:" in line:
            tmp = line.split(" ")
            tmp_res[0] = (float(tmp[-1].rstrip()))
        if "drop rate:" in line:
            tmp = line.split(" ")
            tmp_res[1] = (float(tmp[-1].rstrip()))
        if tmp_res[0] != None and tmp_res[1] != None:
            results.append(tmp_res)
            tmp_res = [None] * 2
    return results

def blackbox(X, path):
    """ #load the last parameters from config.toml;
        Stop chains in chains folder, start blockchain, get chain UID,
        get public ip of a node,launch transaction with docker,
        record results in file, stop blockchain, parse logs \n
        output Y = (TPS, DROPRATE)
    """
    global df
    global filepath
    x = X.astype(int)
    df = df.append({"NUM_THREADS": x[0],
                    "DEFAULT_TICKS_PER_SLOT": x[1],
                    "ITER_BATCH_SIZE": x[2],
                    "RECV_BATCH_MAX_CPU": x[3],
                    "DEFAULT_HASHES_PER_SECOND": x[4],
                    "DEFAULT_TICKS_PER_SECOND": x[5],
                    "AVERAGE_TPS":np.NaN ,
                    "AVERAGE_DROPRATE":np.NaN },
                    ignore_index=True)
    # get the latest parameters
    config = toml.load(path + 'config.toml')
    # config copy to be changed
    config_new = toml.load(path + 'config.toml')
    with open('config.toml', 'w') as cfile:
        # config.toml update with new parameters
        for i, (inn, out) in enumerate(get(config).items()):
            config_new[out][inn] = int(X[i])
        print('new params: %s' % [int(x) for x in X])
        # save updated version
        toml.dump(config_new, cfile)
        cfile.close()
    print('Checking for started chains ...')
    os.chdir(path + 'chains')
    init_chain_id = subprocess.run('ls', capture_output=True, text=True, shell=True).stdout.split('\n')[:-1]
    os.chdir(path)
    if init_chain_id != []:
        for chain in init_chain_id:
            chain_stop(chain)
    else:
        print('Chain folder is empty')
    print('Starting blockchain...')
    #
    #
    # этот файлик вроде как был в репе. но не точно
    #
    #
    #
    subprocess.run('python3 start_chain.py -v 3 -c config.toml', shell=True)
    os.chdir(path + 'chains')
    chain_id = subprocess.run('ls', capture_output=True, text=True, shell=True).stdout
    os.chdir(path)
    get_chain_ip = subprocess.run('python3 get_public_ip.py -u ' + chain_id, capture_output=True, shell=True,
                                  text=True)
    public_ip = get_chain_ip.stdout.split(' ')[-1][:-1]
    print('Time delay of 80 sec...')
    time.sleep(80)
    print('Starting transactions...')

    # file_to_parse = open("current.txt", "w")


    #
    #
    # тут у нас докер для запуска. наверное, убрать но я не уверен. он тоже вроде есть в репе
    #
    #
    #
    with open('output.txt', 'w') as out_file:
        subprocess.run(
            "sudo docker run -it --rm --net=host -e NDEBUG=1 timofeykulakov/solana_simulations:1.0 bash -c \"./multinode-demo/bench-tps.sh --entrypoint " + public_ip + ":8001 --faucet " + public_ip + ":9900 --duration 5 --tx_count 50 \"",
            shell=True, text=True, stdout=out_file)
        subprocess.run('printf \'\n NEW TRANSACTION \n \'', shell=True, text=True, stdout=out_file)
        subprocess.run('printf \'\n  \'', shell=True, text=True, stdout=out_file)
    print('End transactions')
    chain_stop(chain_id)

    # get results from logs
    current_results = parse_logs('output.txt')
    Y = current_results[0]
    
    df.at[len(df) - 1, 'AVERAGE_TPS'] = current_results[0][0]
    df.at[len(df) - 1, 'AVERAGE_DROPRATE'] = current_results[0][1]
    # save current state to scv
    with open(filepath, 'a') as f:
      df.to_csv(f, header=f.tell()==0, index=False) 

    return Y

        
try:
    # set you point in form 
    #                [NUM_THREADS,
    #                 DEFAULT_TICKS_PER_SLOT,
    #                 ITER_BATCH_SIZE,
    #                 RECV_BATCH_MAX_CPU,
    #                 DEFAULT_HASHES_PER_SECOND,
    #                 DEFAULT_TICKS_PER_SECOND]
    X = [4, 1000, 1000, 63, 2000000, 160]
    Y = blackbox(X, config_path)

except Exception as e:
    print ('Error:', e)
    with open('config.toml', 'w') as f:
        toml.dump(config, f)
        f.close()
