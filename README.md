# Black-Box for Blockchain Parameters Adjustment

The repository contains code for the [Link to paper]. The `docker` folder contains code for creation docker images of solana-genesis and solana-validator nodes.

For reproduction of experiments two steps are needed:
- Deployment of solana cluster with given parameters
- Transaction execution

## 1. Deployment of solana cluster
### 1.1 Building from docker images
The easiest way is to use pre-built images from our repository - public.ecr.aws/q9l7c5c2 :
- public.ecr.aws/q9l7c5c2/solana-genesis - genesis node
- public.ecr.aws/q9l7c5c2/solana-validator - validator node 

To run cluster do:
- Run genesis node - `docker run --name genesis -e GOSSIP=<genesis_ip> -v <config_folder_path>:/solana/config -e TOML_CONFIG='/solana/config/config.toml' -e RUST_LOG='info' --net=host -d public.ecr.aws/q9l7c5c2/solana-genesis` 
- Run several validators - `docker run --name validator -e ENTRYPOINT=<genesis_ip> -v <config_folder_path>:/solana/config -e TOML_CONFIG='/solana/config/config.toml' -e RUST_LOG='info' --net=host -d public.ecr.aws/q9l7c5c2/solana-validator`

Config example is in current repository - `config.toml`

### 1.2 Building from source
For building latest version use Dockerfile from `./docker`:
- Download forked solana - `git submodule init`
- Build image - `DOCKER_BUILDKIT=1 docker build -t solana-genesis .`
- Run containers by execution commands from previous step

## 2. Experiments execution
Experiments can be done by execution standard RPC commands to deployed solana cluster, an example can be found at `exp.py`
